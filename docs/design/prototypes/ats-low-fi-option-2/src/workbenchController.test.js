import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import workbenchController, { createWorkbenchController } from "./workbenchController.js";

const JOB_ID = "11111111-1111-4111-8111-111111111111";
const CANDIDATE_ID = "22222222-2222-4222-8222-222222222222";
const APPLICATION_ID = "33333333-3333-4333-8333-333333333333";

function item(changes = {}) {
  return {
    application_id: APPLICATION_ID,
    candidate_id: CANDIDATE_ID,
    job_id: JOB_ID,
    display_name: "李嘉明",
    current_title: "AI 算法工程师",
    location: "北京",
    source: "upload",
    stage: "review",
    updated_at: "2026-07-13T03:05:00Z",
    ...changes,
  };
}

function response(changes = {}) {
  return {
    data: {
      generated_at: "2026-07-13T04:00:00Z",
      jobs: [{
        id: JOB_ID,
        title: "AI 工程师",
        department_name: "技术部",
        status: "open",
        updated_at: "2026-07-13T03:30:00Z",
        active_count: 8,
        stages: {
          new: { count: 0, items: [] },
          review: { count: 1, items: [item()] },
          contact: { count: 0, items: [] },
          interview_pending: { count: 7, items: [item({ stage: "interview_pending", application_id: "44444444-4444-4444-8444-444444444444" })] },
          interviewing: { count: 0, items: [] },
          decision: { count: 0, items: [] },
        },
      }],
      tasks: {
        contact: { count: 0, items: [] },
        interview_pending: { count: 7, items: [item({ stage: "interview_pending", application_id: "44444444-4444-4444-8444-444444444444" })] },
        decision: { count: 0, items: [] },
      },
      interviews: { available: false, upcoming: [], pending_feedback: [] },
      ...changes,
    },
  };
}

test("exports the workbench controller factory and default controller", () => {
  assert.equal(typeof createWorkbenchController, "function");
  assert.equal(typeof workbenchController.load, "function");
});

test("load requests the scoped workbench once and maps stages and candidate navigation context", async () => {
  const calls = [];
  const client = { async request(path, options) { calls.push({ path, options }); return response(); } };
  const signal = new AbortController().signal;

  const result = await createWorkbenchController({ client }).load({ signal });

  assert.deepEqual(calls, [{ path: "/api/v1/workbench", options: { signal } }]);
  assert.equal(result.generatedAt, "2026-07-13T04:00:00Z");
  assert.equal(result.jobs[0].name, "AI 工程师");
  assert.equal(result.jobs[0].department, "技术部");
  assert.equal(result.jobs[0].activeCount, 8);
  assert.equal(result.jobs[0].stages["待复核"].count, 1);
  assert.deepEqual(result.jobs[0].stages["待复核"].items[0], {
    id: APPLICATION_ID,
    applicationId: APPLICATION_ID,
    candidateId: CANDIDATE_ID,
    jobId: JOB_ID,
    serverBacked: true,
    name: "李嘉明",
    role: "AI 算法工程师",
    company: "",
    position: "AI 工程师",
    stage: "待复核",
    source: "upload",
    city: "北京",
    lastActivity: new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date("2026-07-13T03:05:00Z")),
    evidence: {},
  });
  assert.equal(result.tasks.interviewPending.count, 7);
  assert.equal(result.tasks.interviewPending.items[0].position, "AI 工程师");
  assert.deepEqual(result.interviews, { available: false, upcoming: [], pendingFeedback: [] });
});

test("load applies safe display fallbacks to valid nullable workbench fields", async () => {
  const client = { async request() {
    return response({
      jobs: [
        {
          id: JOB_ID,
          title: "AI 工程师",
          department_name: null,
          status: "open",
          updated_at: "2026-07-13T03:30:00Z",
          active_count: 1,
          stages: {
            new: { count: 0, items: [] },
            review: { count: 1, items: [item({ current_title: null, location: null })] },
            contact: { count: 0, items: [] },
            interview_pending: { count: 0, items: [] },
            interviewing: { count: 0, items: [] },
            decision: { count: 0, items: [] },
          },
        },
      ],
      tasks: {
        contact: { count: 0, items: [] },
        interview_pending: { count: 0, items: [] },
        decision: { count: 0, items: [] },
      },
      interviews: { available: false, upcoming: [], pending_feedback: [] },
    });
  } };

  const result = await createWorkbenchController({ client }).load();

  assert.equal(result.jobs.length, 1);
  assert.equal(result.jobs[0].department, "部门未设置");
  assert.equal(result.jobs[0].stages["待复核"].items[0].role, "当前职称未填写");
  assert.equal(result.jobs[0].stages["待复核"].items[0].city, "地点未填写");
  assert.deepEqual(result.tasks, {
    contact: { count: 0, items: [] },
    interviewPending: { count: 0, items: [] },
    decision: { count: 0, items: [] },
  });
  assert.deepEqual(result.interviews, { available: false, upcoming: [], pendingFeedback: [] });
});

test("load rejects a malformed successful response instead of presenting it as an empty workbench", async () => {
  for (const malformed of [
    {},
    { data: null },
    response({ jobs: null }),
    response({ generated_at: null }),
    response({ jobs: [{ id: JOB_ID, title: "AI 工程师", status: "draft", updated_at: "2026-07-13T03:30:00Z", active_count: 4, stages: {} }] }),
    response({ jobs: [{ id: JOB_ID, title: "AI 工程师", status: "open", updated_at: "invalid", active_count: 4, stages: {} }] }),
    response({ tasks: null }),
    response({ tasks: { contact: {}, interview_pending: {}, decision: null } }),
    response({ tasks: { contact: { count: 1, items: null }, interview_pending: { count: 0, items: [] }, decision: { count: 0, items: [] } } }),
    response({ jobs: [{ ...response().data.jobs[0], active_count: 1, stages: { ...response().data.jobs[0].stages, review: { count: 0, items: [item()] } } }] }),
    response({ jobs: [{ ...response().data.jobs[0], stages: { ...response().data.jobs[0].stages, review: { count: 1, items: [item({ job_id: "99999999-9999-4999-8999-999999999999" })] } } }] }),
    response({ tasks: { contact: { count: 1, items: [item({ stage: "contact", job_id: "99999999-9999-4999-8999-999999999999" })] }, interview_pending: { count: 1, items: [item({ stage: "interview_pending", application_id: "44444444-4444-4444-8444-444444444444" })] }, decision: { count: 0, items: [] } } }),
    response({ interviews: null }),
    response({ interviews: { available: true, upcoming: [], pending_feedback: [] } }),
    response({ interviews: { available: false, upcoming: [{ id: "fixture" }], pending_feedback: [] } }),
  ]) {
    const client = { async request() { return malformed; } };
    await assert.rejects(
      createWorkbenchController({ client }).load(),
      (error) => error?.code === "WORKBENCH_INVALID_RESPONSE",
    );
  }
});

test("unavailable interview data rejects unexpected rows", async () => {
  const client = { async request() {
    return response({ interviews: { available: false, upcoming: [{ id: "fake" }], pending_feedback: [{ id: "fake" }] } });
  } };
  await assert.rejects(
    createWorkbenchController({ client }).load(),
    (error) => error?.code === "WORKBENCH_INVALID_RESPONSE",
  );
});

test("load preserves abort errors", async () => {
  const expected = new DOMException("aborted", "AbortError");
  const client = { async request() { throw expected; } };
  await assert.rejects(createWorkbenchController({ client }).load(), (error) => error === expected);
});

test("workbench shell keeps real tasks accessible across loading and narrow layouts", () => {
  const appSource = readFileSync(new URL("./App.jsx", import.meta.url), "utf8");
  const stylesSource = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

  assert.match(appSource, /className="page-body workbench-skeleton" role="status" aria-live="polite"/);
  assert.match(appSource, /aria-pressed=\{activeWorkbenchJob\.id === job\.id\}/);
  assert.match(appSource, /navigate\(candidateListPath\(\{ jobId: activeWorkbenchJob\.id, stage: name \}\)\)/);
  assert.match(appSource, /candidateOrigin\?\.activeNav === "工作台" \? "返回工作台"/);
  assert.match(appSource, /role="alert"/);
  assert.doesNotMatch(appSource, /面试日历（未来 7 天）<\/h3><button/);
  assert.doesNotMatch(appSource, /key=\{candidate\.name\}/);
  assert.doesNotMatch(stylesSource, /\.page-body \{ grid-template-columns: minmax\(720px, 1fr\); \}\.right-rail \{ display: none; \}/);
  assert.match(stylesSource, /\.right-rail \{ grid-template-columns: minmax\(0,1fr\) minmax\(260px,/);
  assert.match(stylesSource, /@media \(max-width: 1180px\) \{[\s\S]*?\.pipeline-panel \{ overflow: hidden; \}\.kanban \{ overflow-x: auto; grid-template-columns: repeat\(6, 150px\); \}[\s\S]*?@media \(max-width: 900px\)/);
});
