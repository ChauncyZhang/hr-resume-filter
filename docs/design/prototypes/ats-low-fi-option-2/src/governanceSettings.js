import { apiClient } from "./apiClient.js";

const ERROR_MESSAGES = {
  authentication_required: "登录状态已失效，请重新登录。",
  csrf_validation_failed: "当前会话已失效，请刷新页面后重试。",
  resource_not_found: "当前账号无权访问此治理设置。",
  precondition_required: "策略版本已失效，请重新加载后重试。",
  resource_version_conflict: "策略已被其他管理员更新，请检查最新设置。",
  idempotency_conflict: "保存请求与先前内容冲突，请检查后重试。",
  retention_confirmation_required: "缩短保留周期前必须重新预览并确认影响。",
  retention_preview_required: "缩短保留周期前必须重新预览并确认影响。",
  retention_preview_stale: "影响范围已变化，请重新预览后确认。",
  retention_preview_stale_impact: "影响范围已变化，请重新预览后确认。",
  retention_preview_expired: "影响预览已过期，请重新预览后确认。",
  retention_preview_invalid: "影响预览已失效，请重新预览后确认。",
  validation_failed: "设置内容无效，请检查后重试。",
  service_unavailable: "服务暂时不可用，请稍后重试。",
};

const PREVIEW_FAILURE_CODES = new Set([
  "retention_confirmation_required",
  "retention_preview_required",
  "retention_preview_stale",
  "retention_preview_stale_impact",
  "retention_preview_expired",
  "retention_preview_invalid",
]);

const AUDIT_FILTERS = [
  ["from", "from"],
  ["to", "to"],
  ["actorId", "actor_id"],
  ["eventType", "event_type"],
  ["resourceType", "resource_type"],
  ["resourceId", "resource_id"],
  ["outcome", "outcome"],
];

let fallbackKeySequence = 0;

function createUniqueIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  fallbackKeySequence += 1;
  return `governance-${Date.now()}-${fallbackKeySequence}`;
}

function safeString(value, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function safeNullableString(value) {
  return typeof value === "string" ? value : null;
}

function safeInteger(value, fallback = 0) {
  return Number.isInteger(value) ? value : fallback;
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

function isAmbiguousFailure(error) {
  return error?.kind === "unavailable" || error?.status === 0 || error?.code === "service_unavailable";
}

function isDenied(error) {
  return error?.status === 404 && error?.code === "resource_not_found";
}

export function getGovernanceErrorMessage(error) {
  return ERROR_MESSAGES[error?.code] || "操作未完成，请稍后重试。";
}

export function buildAuditLogsPath(filters = {}, { cursor = "", limit = 50 } = {}) {
  const params = new URLSearchParams();
  for (const [clientKey, serverKey] of AUDIT_FILTERS) {
    const value = safeString(filters?.[clientKey]);
    if (value) params.set(serverKey, value);
  }
  if (safeString(cursor)) params.set("cursor", cursor);
  const normalizedLimit = Number.isInteger(limit) && limit >= 1 && limit <= 100 ? limit : 50;
  params.set("limit", String(normalizedLimit));
  return `/api/v1/audit-logs?${params}`;
}

export function normalizeAuditRecord(value) {
  const id = safeString(value?.id);
  if (!id) return null;
  const actor = value?.actor && typeof value.actor === "object" ? value.actor : {};
  const resourceValue = value?.resource && typeof value.resource === "object" ? value.resource : null;
  const resource = resourceValue && safeString(resourceValue.type) && safeString(resourceValue.id)
    ? {
        type: safeString(resourceValue.type),
        id: safeString(resourceValue.id),
        label: safeNullableString(resourceValue.label),
      }
    : null;
  return {
    id,
    createdAt: safeString(value?.created_at),
    actor: {
      id: safeNullableString(actor.id),
      displayName: safeString(actor.display_name),
    },
    category: safeString(value?.category),
    eventType: safeString(value?.event_type),
    resource,
    outcome: safeString(value?.outcome),
    networkRef: safeNullableString(value?.network_ref),
    traceId: safeNullableString(value?.trace_id),
    summary: safeString(value?.summary),
  };
}

export function normalizeRetentionPolicy(value) {
  const id = safeString(value?.id);
  const version = safeInteger(value?.version);
  const terminalDays = safeInteger(value?.terminal_days);
  const talentPoolDays = safeInteger(value?.talent_pool_days);
  const backupWindowDays = safeInteger(value?.backup_window_days);
  if (!id || version < 1 || [terminalDays, talentPoolDays, backupWindowDays].some((days) => days < 30 || days > 3650)) return null;
  const updatedBy = value?.updated_by && typeof value.updated_by === "object" ? value.updated_by : {};
  return {
    id,
    version,
    terminalDays,
    talentPoolDays,
    backupWindowDays,
    updatedAt: safeString(value?.updated_at),
    updatedBy: {
      id: safeNullableString(updatedBy.id),
      displayName: safeString(updatedBy.display_name),
    },
  };
}

function draftFromPolicy(policy) {
  return policy ? {
    terminalDays: policy.terminalDays,
    talentPoolDays: policy.talentPoolDays,
    backupWindowDays: policy.backupWindowDays,
  } : null;
}

function draftBody(draft, impactToken = "") {
  const body = {
    terminal_days: draft.terminalDays,
    talent_pool_days: draft.talentPoolDays,
    backup_window_days: draft.backupWindowDays,
  };
  if (impactToken) body.impact_token = impactToken;
  return body;
}

function validDraft(draft) {
  return draft && [draft.terminalDays, draft.talentPoolDays, draft.backupWindowDays]
    .every((days) => Number.isInteger(days) && days >= 30 && days <= 3650);
}

function draftChanged(draft, policy) {
  if (!draft || !policy) return false;
  return draft.terminalDays !== policy.terminalDays
    || draft.talentPoolDays !== policy.talentPoolDays
    || draft.backupWindowDays !== policy.backupWindowDays;
}

function shortensPolicy(draft, policy) {
  return draft.terminalDays < policy.terminalDays
    || draft.talentPoolDays < policy.talentPoolDays
    || draft.backupWindowDays < policy.backupWindowDays;
}

function normalizedAuditRows(values) {
  return (Array.isArray(values) ? values : []).map(normalizeAuditRecord).filter(Boolean);
}

export function releaseGovernanceSettingsSubscription(controller, unsubscribe) {
  unsubscribe();
  controller.releaseRequests();
}

export function createGovernanceSettingsController({
  client = apiClient,
  createIdempotencyKey = createUniqueIdempotencyKey,
  createAbortController = () => new AbortController(),
} = {}) {
  let disposed = false;
  let auditGeneration = 0;
  let retentionGeneration = 0;
  let auditRequest = null;
  let retentionRequest = null;
  let previewToken = "";
  let saveIntent = null;
  const listeners = new Set();
  let state = {
    audit: {
      status: "idle",
      rows: [],
      filters: {},
      nextCursor: null,
      loadingMore: false,
      error: "",
    },
    retention: {
      status: "idle",
      policy: null,
      draft: null,
      dirty: false,
      preview: null,
      error: "",
      message: "",
    },
  };

  function publish(section, patch) {
    if (disposed) return;
    state = { ...state, [section]: { ...state[section], ...patch } };
    listeners.forEach((listener) => listener(state));
  }

  function startAuditRequest() {
    auditRequest?.abort();
    auditRequest = createAbortController();
    return { generation: ++auditGeneration, request: auditRequest };
  }

  function startRetentionRequest() {
    retentionRequest?.abort();
    retentionRequest = createAbortController();
    return { generation: ++retentionGeneration, request: retentionRequest };
  }

  function isCurrentAudit(generation) {
    return !disposed && generation === auditGeneration;
  }

  function isCurrentRetention(generation) {
    return !disposed && generation === retentionGeneration;
  }

  function clearPreview() {
    previewToken = "";
  }

  async function loadAudit(filters = {}) {
    const safeFilters = Object.fromEntries(AUDIT_FILTERS
      .map(([key]) => [key, safeString(filters?.[key])])
      .filter(([, value]) => value));
    const { generation, request } = startAuditRequest();
    publish("audit", {
      status: "loading",
      rows: [],
      filters: safeFilters,
      nextCursor: null,
      loadingMore: false,
      error: "",
    });
    try {
      const response = await client.request(buildAuditLogsPath(safeFilters), { signal: request.signal });
      if (!isCurrentAudit(generation)) return false;
      const rows = normalizedAuditRows(response?.data);
      publish("audit", {
        status: rows.length ? "ready" : "empty",
        rows,
        nextCursor: safeNullableString(response?.meta?.next_cursor),
        loadingMore: false,
        error: "",
      });
      return true;
    } catch (error) {
      if (isAbortError(error) || !isCurrentAudit(generation)) return false;
      publish("audit", {
        status: isDenied(error) ? "denied" : "error",
        rows: [],
        nextCursor: null,
        loadingMore: false,
        error: getGovernanceErrorMessage(error),
      });
      return false;
    }
  }

  async function loadMoreAudit() {
    const cursor = state.audit.nextCursor;
    if (!cursor || state.audit.loadingMore) return false;
    const { generation, request } = startAuditRequest();
    publish("audit", { loadingMore: true, error: "" });
    try {
      const response = await client.request(buildAuditLogsPath(state.audit.filters, { cursor }), { signal: request.signal });
      if (!isCurrentAudit(generation)) return false;
      const seen = new Set(state.audit.rows.map((row) => row.id));
      const appended = normalizedAuditRows(response?.data).filter((row) => {
        if (seen.has(row.id)) return false;
        seen.add(row.id);
        return true;
      });
      const rows = [...state.audit.rows, ...appended];
      publish("audit", {
        status: rows.length ? "ready" : "empty",
        rows,
        nextCursor: safeNullableString(response?.meta?.next_cursor),
        loadingMore: false,
      });
      return true;
    } catch (error) {
      if (isAbortError(error) || !isCurrentAudit(generation)) return false;
      publish("audit", { loadingMore: false, error: getGovernanceErrorMessage(error) });
      return false;
    }
  }

  async function loadRetention({ reviewMessage = "" } = {}) {
    const { generation, request } = startRetentionRequest();
    clearPreview();
    saveIntent = null;
    publish("retention", { status: "loading", preview: null, error: "", message: "" });
    try {
      const response = await client.request("/api/v1/settings/retention-policy", { signal: request.signal });
      if (!isCurrentRetention(generation)) return false;
      const normalized = normalizeRetentionPolicy(response?.data);
      if (!normalized) throw new Error("invalid retention projection");
      publish("retention", {
        status: "ready",
        policy: normalized,
        draft: draftFromPolicy(normalized),
        dirty: false,
        preview: null,
        error: "",
        message: reviewMessage,
      });
      return true;
    } catch (error) {
      if (isAbortError(error) || !isCurrentRetention(generation)) return false;
      publish("retention", {
        status: isDenied(error) ? "denied" : "error",
        policy: null,
        draft: null,
        dirty: false,
        preview: null,
        error: getGovernanceErrorMessage(error),
        message: "",
      });
      return false;
    }
  }

  function updateRetentionDraft(patch) {
    if (disposed || !state.retention.draft || state.retention.status === "saving" || state.retention.status === "previewing") return;
    const allowed = {};
    for (const key of ["terminalDays", "talentPoolDays", "backupWindowDays"]) {
      if (Object.prototype.hasOwnProperty.call(patch || {}, key)) allowed[key] = patch[key];
    }
    const draft = { ...state.retention.draft, ...allowed };
    clearPreview();
    saveIntent = null;
    publish("retention", {
      status: "ready",
      draft,
      dirty: draftChanged(draft, state.retention.policy),
      preview: null,
      error: "",
      message: "",
    });
  }

  async function createPreview() {
    const body = draftBody(state.retention.draft);
    const { generation, request } = startRetentionRequest();
    clearPreview();
    saveIntent = null;
    publish("retention", { status: "previewing", preview: null, error: "", message: "" });
    try {
      const response = await client.request("/api/v1/settings/retention-policy/previews", {
        method: "POST",
        body,
        signal: request.signal,
      });
      if (!isCurrentRetention(generation)) return false;
      const token = safeString(response?.data?.impact_token);
      if (!token) throw new Error("invalid retention preview");
      previewToken = token;
      publish("retention", {
        status: "ready",
        preview: {
          affectedCandidateCount: Math.max(0, safeInteger(response?.data?.affected_candidate_count)),
          expiresAt: safeString(response?.data?.expires_at),
        },
        error: "",
      });
      return false;
    } catch (error) {
      if (isAbortError(error) || !isCurrentRetention(generation)) return false;
      publish("retention", {
        status: isDenied(error) ? "denied" : "error",
        preview: null,
        error: getGovernanceErrorMessage(error),
      });
      return false;
    }
  }

  function ensureSaveIntent(body, version) {
    const signature = JSON.stringify({ body, version });
    if (!saveIntent || saveIntent.signature !== signature) {
      saveIntent = { signature, key: createIdempotencyKey(), body: { ...body }, version };
    }
    return saveIntent;
  }

  async function patchRetention(impactToken = "") {
    const body = draftBody(state.retention.draft, impactToken);
    const version = state.retention.policy.version;
    const intent = ensureSaveIntent(body, version);
    const { generation, request } = startRetentionRequest();
    publish("retention", { status: "saving", error: "", message: "" });
    try {
      const response = await client.request("/api/v1/settings/retention-policy", {
        method: "PATCH",
        body: { ...intent.body },
        ifMatch: `"${intent.version}"`,
        idempotencyKey: intent.key,
        signal: request.signal,
      });
      if (!isCurrentRetention(generation)) return false;
      const normalized = normalizeRetentionPolicy(response?.data);
      if (!normalized) throw new Error("invalid retention projection");
      clearPreview();
      saveIntent = null;
      publish("retention", {
        status: "ready",
        policy: normalized,
        draft: draftFromPolicy(normalized),
        dirty: false,
        preview: null,
        error: "",
        message: "保留策略已保存。",
      });
      return true;
    } catch (error) {
      if (isAbortError(error) || !isCurrentRetention(generation)) return false;
      if (error?.code === "resource_version_conflict") {
        clearPreview();
        saveIntent = null;
        await loadRetention({ reviewMessage: "策略已被其他管理员更新。已加载最新设置，请检查后重试。" });
        return false;
      }
      if (!isAmbiguousFailure(error)) saveIntent = null;
      if (PREVIEW_FAILURE_CODES.has(error?.code)) clearPreview();
      publish("retention", {
        status: isDenied(error) ? "denied" : "error",
        preview: PREVIEW_FAILURE_CODES.has(error?.code) ? null : state.retention.preview,
        error: getGovernanceErrorMessage(error),
      });
      return false;
    }
  }

  async function saveRetention() {
    const { policy, draft } = state.retention;
    if (!policy || !validDraft(draft) || state.retention.status === "saving" || state.retention.status === "previewing") {
      if (draft && !validDraft(draft)) publish("retention", { status: "error", error: ERROR_MESSAGES.validation_failed });
      return false;
    }
    if (shortensPolicy(draft, policy)) {
      if (previewToken && state.retention.preview) return false;
      return createPreview();
    }
    return patchRetention();
  }

  async function confirmRetentionSave() {
    if (state.retention.status === "saving" || !previewToken || !state.retention.preview || !state.retention.policy || !validDraft(state.retention.draft)) return false;
    return patchRetention(previewToken);
  }

  function cancelRetentionPreview() {
    clearPreview();
    saveIntent = null;
    publish("retention", { preview: null, error: "" });
  }

  function releaseRequests() {
    auditRequest?.abort();
    retentionRequest?.abort();
    auditRequest = null;
    retentionRequest = null;
    auditGeneration += 1;
    retentionGeneration += 1;
    clearPreview();
    saveIntent = null;
    if (state.retention.preview) publish("retention", { preview: null });
  }

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    loadAudit,
    loadMoreAudit,
    loadRetention,
    updateRetentionDraft,
    saveRetention,
    confirmRetentionSave,
    cancelRetentionPreview,
    releaseRequests,
    dispose() {
      if (disposed) return;
      releaseRequests();
      disposed = true;
      listeners.clear();
    },
  };
}
