import { apiClient as defaultApiClient } from "./apiClient.js";

const TERMINAL_RUN_STATUSES = new Set(["complete", "partial", "failed", "cancelled"]);
const SUCCESSFUL_LLM_STATUSES = new Set(["succeeded", "skipped", "not_requested"]);

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function safeString(value) {
  return typeof value === "string" ? value : "";
}

function safeCount(value) {
  return Number.isInteger(value) && value >= 0 ? value : 0;
}

function safeScore(value) {
  return Number.isFinite(value) ? value : null;
}

function safeStrings(value) {
  return Array.isArray(value) ? value.filter((entry) => typeof entry === "string") : [];
}

function isFile(value) {
  return Object.prototype.toString.call(value) === "[object File]"
    && typeof value?.name === "string"
    && typeof value?.arrayBuffer === "function";
}

function normalizeRunStatus(status) {
  if (status === "completed") return "complete";
  if (["partial", "failed", "cancelled"].includes(status)) return status;
  return "running";
}

function sourceLabel(source) {
  return source === "upload" ? "本地上传" : source === "manual" ? "手动创建" : safeString(source);
}

export function normalizeScreeningRunSummary(run) {
  const safeRun = isRecord(run) ? run : {};
  return {
    id: safeString(safeRun.id),
    jobId: safeString(safeRun.job_id),
    position: safeString(safeRun.job_title) || "职位信息不可用",
    creator: safeString(safeRun.created_by_name) || "发起人不可用",
    source: sourceLabel(safeRun.source),
    status: normalizeRunStatus(safeRun.status),
    completed: safeCount(safeRun.processed_count),
    total: safeCount(safeRun.total_count),
    succeeded: safeCount(safeRun.succeeded_count),
    failed: safeCount(safeRun.failed_count),
    reviewTotal: safeCount(safeRun.review_total_count),
    reviewed: safeCount(safeRun.reviewed_count),
    reviewPending: safeCount(safeRun.review_pending_count),
    reviewApproved: safeCount(safeRun.review_approved_count),
    reviewRejected: safeCount(safeRun.review_rejected_count),
    reviewStatus: safeString(safeRun.review_status) || "not_applicable",
    createdAt: safeString(safeRun.created_at),
    serverBacked: true,
  };
}

function normalizeFile(item) {
  const ruleResult = isRecord(item?.rule_result) ? item.rule_result : null;
  const llmEvaluation = isRecord(item?.llm_evaluation) ? item.llm_evaluation : null;
  const hasFinalRuleResult = item?.status === "scored" && ruleResult !== null;
  let status = item?.status === "queued" ? "queued" : "running";

  if (item?.status === "failed") {
    status = "failed";
  } else if (item?.status === "cancelled") {
    status = "cancelled";
  } else if (hasFinalRuleResult && item?.llm_status === "failed") {
    status = "partial";
  } else if (hasFinalRuleResult && SUCCESSFUL_LLM_STATUSES.has(item?.llm_status)) {
    status = "success";
  }

  const matched = [
    ...safeStrings(ruleResult?.required_hits),
    ...safeStrings(ruleResult?.bonus_hits),
  ].join("、");
  const risks = [
    ...safeStrings(ruleResult?.risks),
    ...safeStrings(llmEvaluation?.risks),
  ].join("、");
  const error = status === "partial"
    ? safeString(item?.llm_error_code)
    : status === "failed" ? safeString(item?.error_code) : "";

  return {
    id: safeString(item?.id),
    name: safeString(item?.filename),
    candidateId: safeString(item?.candidate_id) || null,
    candidate: safeString(item?.candidate_name),
    status,
    ruleScore: safeScore(ruleResult?.score),
    llmScore: safeScore(llmEvaluation?.score),
    matched,
    missing: safeStrings(ruleResult?.required_missing).join("、"),
    recommendation: safeString(ruleResult?.recommendation),
    risk: risks,
    error,
    application_stage: safeString(item?.application_stage) || null,
    application_version: Number.isInteger(item?.application_version) ? item.application_version : null,
    humanReviewed: item?.human_reviewed === true,
    llmStatus: safeString(item?.llm_status),
    retryable: item?.retryable === true,
    llmRetryable: item?.llm_retryable === true,
  };
}

export function normalizeScreeningTask(run, items) {
  const safeRun = isRecord(run) ? run : {};
  const summary = normalizeScreeningRunSummary(safeRun);
  return {
    ...summary,
    files: Array.isArray(items) ? items.filter((item) => isRecord(item) && safeString(item.id)).map(normalizeFile) : [],
  };
}

function defaultIdempotencyKey() {
  return globalThis.crypto.randomUUID();
}

function abortError() {
  return new DOMException("Aborted", "AbortError");
}

function defaultWait(milliseconds, { signal } = {}) {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    function onAbort() {
      clearTimeout(timer);
      reject(abortError());
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function withSignal(signal) {
  return signal ? { signal } : {};
}

function resourceData(response) {
  return response?.data ?? null;
}

export function createScreeningController({
  client = defaultApiClient,
  createIdempotencyKey = defaultIdempotencyKey,
  wait = defaultWait,
} = {}) {
  const pollGenerations = new Map();

  async function listJobs({ signal } = {}) {
    const jobs = [];
    let cursor = "";
    do {
      const path = `/api/v1/jobs?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
      const response = await client.request(path, withSignal(signal));
      if (Array.isArray(response?.data)) jobs.push(...response.data);
      cursor = safeString(response?.meta?.next_cursor);
    } while (cursor);

    return jobs
        .filter(isRecord)
        .map((job) => ({ id: safeString(job.id), title: safeString(job.title) }))
        .filter((job) => job.id && job.title);
  }

  async function listRuns({ signal } = {}) {
    const runs = [];
    let cursor = "";
    do {
      const path = `/api/v1/screening-runs?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
      const response = await client.request(path, withSignal(signal));
      if (Array.isArray(response?.data)) runs.push(...response.data);
      cursor = safeString(response?.meta?.next_cursor);
    } while (cursor);
    return runs.filter((run) => isRecord(run) && safeString(run.id)).map(normalizeScreeningRunSummary);
  }

  async function createRun(jobId, { signal } = {}) {
    const response = await client.request(`/api/v1/jobs/${encodeURIComponent(jobId)}/screening-runs`, {
      method: "POST",
      body: { source: "upload" },
      idempotencyKey: createIdempotencyKey(),
      ...withSignal(signal),
    });
    return resourceData(response);
  }

  async function uploadFiles(runId, files, { signal } = {}) {
    const uploads = Array.from(files, (file) => {
      if (!isFile(file)) throw new TypeError("screening uploads require File objects");
      const body = new FormData();
      body.append("file", file);
      return client.request(`/api/v1/screening-runs/${encodeURIComponent(runId)}/items`, {
        method: "POST",
        body,
        idempotencyKey: createIdempotencyKey(),
        ...withSignal(signal),
      }).then(resourceData);
    });
    return Promise.all(uploads);
  }

  async function startRun(runId, { signal } = {}) {
    const response = await client.request(`/api/v1/screening-runs/${encodeURIComponent(runId)}/start`, {
      method: "POST",
      idempotencyKey: createIdempotencyKey(),
      ...withSignal(signal),
    });
    return resourceData(response);
  }

  async function getRun(runId, { signal } = {}) {
    return resourceData(await client.request(`/api/v1/screening-runs/${encodeURIComponent(runId)}`, withSignal(signal)));
  }

  async function getItems(runId, { signal } = {}) {
    const response = await client.request(`/api/v1/screening-runs/${encodeURIComponent(runId)}/items?limit=100`, withSignal(signal));
    return Array.isArray(response?.data) ? response.data : [];
  }

  async function retryItem(itemId, { signal } = {}) {
    const response = await client.request(`/api/v1/screening-items/${encodeURIComponent(itemId)}/retry`, {
      method: "POST",
      idempotencyKey: createIdempotencyKey(),
      ...withSignal(signal),
    });
    return resourceData(response);
  }

  async function bulkAction(runId, items, { signal } = {}) {
    const response = await client.request(`/api/v1/screening-runs/${encodeURIComponent(runId)}/bulk-actions`, {
      method: "POST",
      body: { command: "advance_to_review", items },
      idempotencyKey: createIdempotencyKey(),
      ...withSignal(signal),
    });
    const data = resourceData(response);
    return {
      applied: safeCount(data?.applied_count),
      already_applied: safeCount(data?.already_applied_count),
      undo_items: Array.isArray(data?.applications) ? data.applications
        .filter((application) => isRecord(application)
          && application.result === "applied"
          && safeString(application.item_id)
          && Number.isInteger(application.version)
          && application.version > 0)
        .map((application) => ({ item_id: application.item_id, expected_application_version: application.version })) : [],
    };
  }

  async function undoBulkAction(runId, items, { signal } = {}) {
    const response = await client.request(`/api/v1/screening-runs/${encodeURIComponent(runId)}/bulk-actions`, {
      method: "POST",
      body: { command: "undo_advance_to_new", items },
      idempotencyKey: createIdempotencyKey(),
      ...withSignal(signal),
    });
    const data = resourceData(response);
    return {
      applied: safeCount(data?.applied_count),
      already_applied: safeCount(data?.already_applied_count),
    };
  }

  async function pollRun(runId, { signal, intervalMs = 1000, onSnapshot } = {}) {
    const generation = (pollGenerations.get(runId) ?? 0) + 1;
    pollGenerations.set(runId, generation);
    const isCurrent = () => pollGenerations.get(runId) === generation;

    try {
      while (!signal?.aborted && isCurrent()) {
        const run = await getRun(runId, { signal });
        if (signal?.aborted || !isCurrent()) return null;
        const items = await getItems(runId, { signal });
        if (signal?.aborted || !isCurrent()) return null;
        const snapshot = normalizeScreeningTask(run, items);
        onSnapshot?.(snapshot);
        if (TERMINAL_RUN_STATUSES.has(snapshot.status)) return snapshot;
        await wait(intervalMs, { signal });
      }
      return null;
    } catch (error) {
      if (signal?.aborted || error?.name === "AbortError") return null;
      throw error;
    }
  }

  return { listJobs, listRuns, createRun, uploadFiles, startRun, getRun, getItems, retryItem, bulkAction, undoBulkAction, pollRun };
}

export const screeningController = createScreeningController();
