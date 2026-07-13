import assert from "node:assert/strict";
import test from "node:test";
import { createCandidateController, normalizeCandidateReview } from "./candidateController.js";

const candidateId = "candidate-1";
const jobId = "job-1";
const response = (data) => ({ data });

test("candidate review loads only the selected server candidate and current job application", async () => {
  const calls = [];
  const client = {
    async request(path) {
      calls.push(path);
      if (path === `/api/v1/candidates/${candidateId}`) return response({
        id: candidateId, display_name: "李嘉明", current_title: "AI 算法工程师", location: "北京",
        owner_id: "user-1", version: 3, updated_at: "2026-07-13T09:00:00+00:00",
        contacts: [{ kind: "phone", value: "138****2468" }, { kind: "email", value: "lij***@mail.com" }],
      });
      if (path === `/api/v1/candidates/${candidateId}/applications`) return response([
        { id: "application-other", candidate_id: candidateId, job_id: "job-2", resume_id: "resume-2", owner_id: "user-2", stage: "rejected", source: "manual", human_conclusion: null, version: 4, updated_at: "2026-07-12T09:00:00+00:00" },
        { id: "application-1", candidate_id: candidateId, job_id: jobId, resume_id: "resume-1", owner_id: "user-1", stage: "review", source: "本地上传", human_conclusion: "需要补充：确认到岗时间", version: 2, updated_at: "2026-07-13T09:00:00+00:00" },
      ]);
      if (path === `/api/v1/candidates/${candidateId}/resumes`) return response([
        { id: "resume-1", candidate_id: candidateId, version_number: 1, created_at: "2026-07-13T08:00:00+00:00" },
      ]);
      if (path === `/api/v1/candidates/${candidateId}/notes?application_id=application-1`) return response([
        { id: "note-1", body: "优先确认到岗时间", author_id: "user-1", created_at: "2026-07-13T09:10:00+00:00" },
      ]);
      if (path === `/api/v1/candidates/${candidateId}/timeline`) return response([
        { id: "event-1", event_type: "application.stage_changed", summary: "Application stage changed from new to review: 筛选后人工复核", actor_id: "user-1", created_at: "2026-07-13T09:05:00+00:00" },
        { id: "event-2", event_type: "application.updated", summary: "Application updated", actor_id: "user-1", created_at: "2026-07-13T09:00:00+00:00" },
      ]);
      throw new Error(`unexpected request ${path}`);
    },
  };

  const review = await createCandidateController({ client }).loadReview({
    candidateId, jobId, position: "AI 工程师", actor: { id: "user-1", name: "张小北" },
    evidence: { ruleScore: 81, llmScore: 78, recommendation: "可沟通", matched: "Python、RAG", missing: "Kubernetes", risk: "项目规模待确认" },
  });

  assert.equal(calls.length, 5);
  assert.equal(review.id, candidateId);
  assert.equal(review.name, "李嘉明");
  assert.equal(review.position, "AI 工程师");
  assert.equal(review.stage, "待复核");
  assert.equal(review.application.id, "application-1");
  assert.equal(review.resume.id, "resume-1");
  assert.equal(review.owner, "张小北");
  assert.equal(review.humanConclusion, "需要补充");
  assert.equal(review.humanConclusionReason, "确认到岗时间");
  assert.deepEqual(review.notes.map((item) => item.body), ["优先确认到岗时间"]);
  assert.ok(calls.includes(`/api/v1/candidates/${candidateId}/notes?application_id=application-1`));
  assert.equal(review.timeline[0].action, "新简历 → 待复核；原因：筛选后人工复核");
  assert.equal(review.timeline[0].actor, "张小北");
  assert.equal(review.timeline[1].action, "更新职位申请");
  assert.equal(review.ruleScore, 81);
});

test("normalization refuses cross-job fallback and preserves masked contacts only", () => {
  const review = normalizeCandidateReview({
    candidate: { id: candidateId, display_name: "候选人", contacts: [{ kind: "phone", value: "139****0000" }] },
    applications: [{ id: "wrong", job_id: "job-2", stage: "review", source: "manual", version: 1 }],
    resumes: [], notes: [], timeline: [],
    context: { jobId, position: "AI 工程师", actor: { id: "user-1", name: "张小北" }, evidence: {} },
  });

  assert.equal(review.application, null);
  assert.equal(review.stage, "无当前申请");
  assert.equal(review.phone, "139****0000");
  assert.equal(review.email, "未提供");
});

test("saving a human conclusion is versioned and never transitions the application", async () => {
  const calls = [];
  const client = { async request(path, options) { calls.push({ path, options }); return response({ id: "application-1", stage: "review", version: 3, human_conclusion: options.body.human_conclusion }); } };
  const saved = await createCandidateController({ client }).saveConclusion({ id: "application-1", version: 2 }, "暂不合适", "缺少生产经验");

  assert.deepEqual(calls, [{ path: "/api/v1/applications/application-1", options: { method: "PATCH", ifMatch: '"2"', body: { human_conclusion: "暂不合适：缺少生产经验" } } }]);
  assert.equal(saved.stage, "review");
  assert.equal(saved.version, 3);
});

test("transition maps UI stages, requires a rejection reason, and sends idempotency plus version", async () => {
  const calls = [];
  const client = { async request(path, options) { calls.push({ path, options }); return response({ id: "application-1", stage: options.body.target, version: 3 }); } };
  const controller = createCandidateController({ client, idempotencyKey: () => "transition-key" });

  await assert.rejects(controller.transition({ id: "application-1", version: 2 }, "已淘汰", "   "), (error) => error?.code === "REJECTION_REASON_REQUIRED");
  const advanced = await controller.transition({ id: "application-1", version: 2 }, "待沟通", "经验匹配");

  assert.equal(advanced.stage, "contact");
  assert.deepEqual(calls, [{ path: "/api/v1/applications/application-1/transitions", options: {
    method: "POST", ifMatch: '"2"', idempotencyKey: "transition-key", body: { target: "contact", reason_text: "经验匹配" },
  } }]);
});

test("notes, preview, and ticket download use the authorized server APIs", async () => {
  const calls = [];
  const client = {
    async request(path, options = {}) {
      calls.push({ kind: "json", path, options });
      if (path.endsWith("/notes")) return response({ id: "note-2", body: options.body.body, author_id: "user-1" });
      if (path.endsWith("/preview")) return response({ resume_id: "resume-1", text: "private preview" });
      if (path.endsWith("/download-tickets")) return response({ token: "one-time-token", expires_in: 60 });
      throw new Error(`unexpected request ${path}`);
    },
    async download(path, options) { calls.push({ kind: "download", path, options }); return { blob: new Blob(["resume"]), filename: "candidate.pdf" }; },
  };
  const controller = createCandidateController({ client });

  assert.equal((await controller.addNote(candidateId, "application-1", "  电话沟通后更新  ")).body, "电话沟通后更新");
  assert.equal((await controller.previewResume("resume-1")).text, "private preview");
  const downloaded = await controller.downloadResume("resume-1");

  assert.equal(downloaded.filename, "candidate.pdf");
  assert.deepEqual(calls[0], { kind: "json", path: `/api/v1/candidates/${candidateId}/notes`, options: { method: "POST", body: { application_id: "application-1", body: "电话沟通后更新" } } });
  assert.deepEqual(calls.at(-1), { kind: "download", path: "/api/v1/download-tickets/consume", options: { method: "POST", body: { token: "one-time-token" } } });
});
