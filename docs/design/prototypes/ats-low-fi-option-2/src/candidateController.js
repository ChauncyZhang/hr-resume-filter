import { apiClient } from "./apiClient.js";

const API_TO_UI_STAGE = {
  new: "新简历",
  review: "待复核",
  contact: "待沟通",
  interview_pending: "待安排",
  interviewing: "面试中",
  decision: "待决策",
  passed: "已通过",
  hired: "已录用",
  rejected: "已淘汰",
  withdrawn: "已撤回",
};

const UI_TO_API_STAGE = Object.fromEntries(Object.entries(API_TO_UI_STAGE).map(([api, ui]) => [ui, api]));
const CONCLUSIONS = new Set(["建议推进", "需要补充", "暂不合适"]);

function safeString(value, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function codedError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function signalOption(signal) {
  return signal ? { signal } : {};
}

function parseConclusion(value) {
  const text = safeString(value).trim();
  if (!text) return { conclusion: "", reason: "" };
  const separator = text.indexOf("：");
  const conclusion = separator < 0 ? text : text.slice(0, separator);
  return CONCLUSIONS.has(conclusion)
    ? { conclusion, reason: separator < 0 ? "" : text.slice(separator + 1) }
    : { conclusion: "", reason: text };
}

function contactValue(contacts, kind) {
  return safeString(safeArray(contacts).find((item) => item?.kind === kind)?.value, "未提供");
}

function displayDateTime(value) {
  const raw = safeString(value);
  if (!raw) return "未记录";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return "未记录";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function normalizeTimelineEvent(item, actor) {
  const labels = {
    "candidate.created": "创建候选人档案",
    "candidate.corrected": "更新候选人档案",
    "candidate.note_added": "添加招聘备注",
    "application.created": "创建职位申请",
    "application.updated": "更新职位申请",
    "application.stage_changed": "更新职位申请阶段",
  };
  const summary = safeString(item?.summary);
  const transition = summary.match(/^Application stage changed from ([a-z_]+) to ([a-z_]+)(?:: (.+))?$/);
  const action = transition
    ? `${API_TO_UI_STAGE[transition[1]] || "未知阶段"} → ${API_TO_UI_STAGE[transition[2]] || "未知阶段"}${transition[3] ? `；原因：${transition[3]}` : ""}`
    : labels[item?.event_type] || "更新候选人记录";
  return {
    id: safeString(item?.id),
    action,
    time: displayDateTime(item?.created_at),
    actor: safeString(item?.actor_id) === actor?.id ? safeString(actor?.name, "当前用户") : "招聘团队成员",
  };
}

function normalizeCandidateListItem(candidate) {
  const application = candidate?.application || null;
  const ruleScore = Number.isInteger(application?.rule_score) ? application.rule_score : null;
  const recommendation = safeString(application?.recommendation, "待人工复核");
  const candidateId = safeString(candidate?.id);
  const applicationId = safeString(application?.id);
  return {
    id: applicationId || candidateId,
    serverBacked: true,
    candidateId,
    applicationId,
    jobId: safeString(application?.job_id),
    ownerId: safeString(application?.owner_id),
    name: safeString(candidate?.display_name, "未命名候选人"),
    role: safeString(candidate?.current_title, "当前职称未填写"),
    company: "",
    position: safeString(application?.job_title, "无当前申请"),
    stage: application ? (API_TO_UI_STAGE[application.stage] || "未知阶段") : "无当前申请",
    score: ruleScore ?? "-",
    ruleScore,
    recommendation,
    source: safeString(application?.source, "未记录"),
    owner: safeString(application?.owner_name, "未分配"),
    city: safeString(candidate?.location, "地点未填写"),
    phone: contactValue(candidate?.contacts, "phone"),
    email: contactValue(candidate?.contacts, "email"),
    lastActivity: displayDateTime(application?.updated_at || candidate?.updated_at),
    evidence: { ruleScore, recommendation },
  };
}

export function mergeCandidateRecords(current, incoming) {
  const seen = new Set(safeArray(current).map((item) => item?.applicationId || item?.candidateId).filter(Boolean));
  return [...safeArray(current), ...safeArray(incoming).filter((item) => {
    const key = item?.applicationId || item?.candidateId;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  })];
}

function normalizeOwnerFacets(owners) {
  return safeArray(owners).map((item) => ({ id: safeString(item?.id), name: safeString(item?.name) })).filter((item) => item.id && item.name);
}

function selectApplication(applications, candidateId, context) {
  return safeArray(applications).find((item) => (
    item?.candidate_id === candidateId
    && item?.job_id === context.jobId
    && (!context.applicationId || item?.id === context.applicationId)
  )) || null;
}

export function normalizeCandidateReview({ candidate, applications, resumes, notes, timeline, context }) {
  const candidateId = safeString(candidate?.id);
  const application = selectApplication(applications, candidateId, context);
  const resume = application
    ? safeArray(resumes).find((item) => item?.id === application.resume_id) || null
    : null;
  const evidence = context.evidence || {};
  const parsedConclusion = parseConclusion(application?.human_conclusion);
  const actorOwnsApplication = application?.owner_id && application.owner_id === context.actor?.id;
  const matched = safeString(evidence.matched);

  return {
    id: candidateId,
    serverBacked: true,
    name: safeString(candidate?.display_name, "未命名候选人"),
    role: safeString(candidate?.current_title, "当前职称未填写"),
    company: "",
    city: safeString(candidate?.location, "地点未填写"),
    phone: contactValue(candidate?.contacts, "phone"),
    email: contactValue(candidate?.contacts, "email"),
    position: safeString(context.position, "当前职位"),
    stage: application ? (API_TO_UI_STAGE[application.stage] || "未知阶段") : "无当前申请",
    source: safeString(application?.source, "未记录"),
    owner: actorOwnsApplication ? safeString(context.actor?.name, "当前 HR") : "招聘负责人",
    lastActivity: displayDateTime(application?.updated_at || candidate?.updated_at),
    recommendation: safeString(evidence.recommendation, "待人工复核"),
    score: Number.isInteger(evidence.ruleScore) ? evidence.ruleScore : null,
    ruleScore: Number.isInteger(evidence.ruleScore) ? evidence.ruleScore : null,
    llmScore: Number.isInteger(evidence.llmScore) ? evidence.llmScore : null,
    matched: matched || "暂无命中项",
    missing: safeString(evidence.missing, "暂无缺失项"),
    risk: safeString(evidence.risk, "暂无已记录风险"),
    llmReason: safeString(evidence.llmReason, "本次筛选未返回 LLM 摘要。"),
    summary: safeString(evidence.llmReason, "候选人结构化摘要将在后续解析能力中补充。"),
    skills: matched ? matched.split("、").filter(Boolean) : [],
    education: "结构化教育经历待补充",
    experience: "结构化工作经历待补充",
    tags: [],
    notes: safeArray(notes).map((item) => ({ id: safeString(item?.id), body: safeString(item?.body), authorId: safeString(item?.author_id), createdAt: safeString(item?.created_at) })).filter((item) => item.id && item.body),
    timeline: safeArray(timeline).map((item) => normalizeTimelineEvent(item, context.actor)).filter((item) => item.id),
    applications: application ? [{
      id: application.id,
      position: safeString(context.position, "当前职位"),
      state: API_TO_UI_STAGE[application.stage] || "未知阶段",
      created: displayDateTime(application.updated_at),
      source: safeString(application.source, "未记录"),
    }] : [],
    interviews: [],
    application,
    resume,
    humanConclusion: parsedConclusion.conclusion,
    humanConclusionReason: parsedConclusion.reason,
    version: application?.version ?? candidate?.version ?? 0,
  };
}

export function createCandidateController({ client = apiClient, idempotencyKey = () => globalThis.crypto.randomUUID() } = {}) {
  async function listCandidates(filters = {}, { signal } = {}) {
    const params = new URLSearchParams();
    const query = safeString(filters.q).trim();
    const jobId = safeString(filters.jobId).trim();
    const stage = safeString(filters.stage).trim();
    const ownerId = safeString(filters.ownerId).trim();
    const cursor = safeString(filters.cursor).trim();
    const minScoreRaw = filters.minScore == null ? "" : String(filters.minScore).trim();
    const minScore = minScoreRaw ? Number(minScoreRaw) : Number.NaN;
    const limit = Number(filters.limit);
    if (query) params.set("q", query);
    if (jobId && jobId !== "全部职位") params.set("job_id", jobId);
    if (stage && stage !== "全部阶段") params.set("stage", UI_TO_API_STAGE[stage] || stage);
    if (ownerId && ownerId !== "全部负责人") params.set("owner_id", ownerId);
    if (Number.isFinite(minScore) && minScore >= 0 && minScore <= 100) params.set("min_score", String(minScore));
    if (cursor) params.set("cursor", cursor);
    if (Number.isInteger(limit) && limit > 0) params.set("limit", String(limit));
    const result = await client.request(`/api/v1/candidates?${params.toString()}`, signalOption(signal));
    return {
      records: safeArray(result?.data).map(normalizeCandidateListItem),
      nextCursor: safeString(result?.meta?.next_cursor) || null,
      ownerOptions: normalizeOwnerFacets(result?.meta?.owners),
    };
  }

  async function listJobs({ signal } = {}) {
    const jobs = [];
    let cursor = "";
    do {
      const params = new URLSearchParams({ limit: "100" });
      if (cursor) params.set("cursor", cursor);
      const result = await client.request(`/api/v1/jobs?${params.toString()}`, signalOption(signal));
      jobs.push(...safeArray(result?.data).map((item) => ({ id: safeString(item?.id), title: safeString(item?.title) })).filter((item) => item.id && item.title));
      cursor = safeString(result?.meta?.next_cursor);
    } while (cursor);
    return jobs;
  }

  async function loadReview(context, { signal } = {}) {
    if (!safeString(context?.candidateId)) throw codedError("CANDIDATE_ID_REQUIRED", "candidate id required");
    const root = `/api/v1/candidates/${context.candidateId}`;
    const options = signalOption(signal);
    const [candidate, applications, resumes, timeline] = await Promise.all([
      client.request(root, options),
      client.request(`${root}/applications`, options),
      client.request(`${root}/resumes`, options),
      client.request(`${root}/timeline`, options),
    ]);
    const candidateData = candidate?.data;
    if (safeString(candidateData?.id) !== context.candidateId) throw codedError("CANDIDATE_MISMATCH", "candidate mismatch");
    const application = selectApplication(applications?.data, context.candidateId, context);
    if (context.applicationId && !application) throw codedError("APPLICATION_MISMATCH", "application mismatch");
    const notes = application
      ? await client.request(`${root}/notes?application_id=${encodeURIComponent(application.id)}`, options)
      : { data: [] };
    return normalizeCandidateReview({
      candidate: candidateData,
      applications: applications?.data,
      resumes: resumes?.data,
      notes: notes?.data,
      timeline: timeline?.data,
      context,
    });
  }

  async function saveConclusion(application, conclusion, reason = "", { signal } = {}) {
    if (!application?.id || !Number.isInteger(application.version)) throw codedError("APPLICATION_REQUIRED", "application required");
    if (!CONCLUSIONS.has(conclusion)) throw codedError("CONCLUSION_REQUIRED", "conclusion required");
    const detail = safeString(reason).trim();
    const humanConclusion = detail ? `${conclusion}：${detail}` : conclusion;
    const result = await client.request(`/api/v1/applications/${application.id}`, {
      method: "PATCH", ifMatch: `"${application.version}"`, body: { human_conclusion: humanConclusion }, ...signalOption(signal),
    });
    return result?.data;
  }

  async function transition(application, target, reason = "", { signal } = {}) {
    const apiTarget = UI_TO_API_STAGE[target];
    const detail = safeString(reason).trim();
    if (!application?.id || !Number.isInteger(application.version) || !apiTarget) throw codedError("TRANSITION_INVALID", "transition invalid");
    if (apiTarget === "rejected" && !detail) throw codedError("REJECTION_REASON_REQUIRED", "rejection reason required");
    const body = { target: apiTarget };
    if (detail) body.reason_text = detail;
    const result = await client.request(`/api/v1/applications/${application.id}/transitions`, {
      method: "POST", ifMatch: `"${application.version}"`, idempotencyKey: idempotencyKey(), body, ...signalOption(signal),
    });
    return result?.data;
  }

  async function addNote(candidateId, applicationId, body, { signal } = {}) {
    const value = safeString(body).trim();
    if (!safeString(applicationId)) throw codedError("APPLICATION_REQUIRED", "application required");
    if (!value) throw codedError("NOTE_REQUIRED", "note required");
    const result = await client.request(`/api/v1/candidates/${candidateId}/notes`, { method: "POST", body: { application_id: applicationId, body: value }, ...signalOption(signal) });
    return result?.data;
  }

  async function previewResume(resumeId, { signal } = {}) {
    const result = await client.request(`/api/v1/resumes/${resumeId}/preview`, signalOption(signal));
    return result?.data;
  }

  async function downloadResume(resumeId, { signal } = {}) {
    const ticket = await client.request(`/api/v1/resumes/${resumeId}/download-tickets`, { method: "POST", ...signalOption(signal) });
    return client.download("/api/v1/download-tickets/consume", { method: "POST", body: { token: ticket?.data?.token }, ...signalOption(signal) });
  }

  return { listCandidates, listJobs, loadReview, saveConclusion, transition, addNote, previewResume, downloadResume };
}

export const candidateController = createCandidateController();
