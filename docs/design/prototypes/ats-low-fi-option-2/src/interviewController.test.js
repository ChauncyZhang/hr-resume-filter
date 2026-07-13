import test from "node:test";
import assert from "node:assert/strict";
import { createInterviewController, deriveCandidateInterviews } from "./interviewController.js";

const INTERVIEW_ID = "11111111-1111-4111-8111-111111111111";
const APPLICATION_ID = "22222222-2222-4222-8222-222222222222";
const CANDIDATE_ID = "33333333-3333-4333-8333-333333333333";
const JOB_ID = "44444444-4444-4444-8444-444444444444";
const USER_ID = "55555555-5555-4555-8555-555555555555";
const FEEDBACK_ID = "66666666-6666-4666-8666-666666666666";

function apiInterview(overrides = {}) {
  return {
    id: INTERVIEW_ID,
    application_id: APPLICATION_ID,
    candidate: { id: CANDIDATE_ID, display_name: "赵宁", current_title: "大模型应用工程师" },
    job: { id: JOB_ID, title: "AI 工程师" },
    round_name: "一面",
    method: "video",
    timezone: "Asia/Shanghai",
    starts_at: "2026-07-15T10:00:00+08:00",
    ends_at: "2026-07-15T11:00:00+08:00",
    location: null,
    meeting_url: "https://meeting.example.com/one",
    status: "pending_feedback",
    notification_status: "sent",
    invitation_status: "artifact_ready",
    participants: [{ user_id: USER_ID, display_name: "张小北", role: "interviewer", required_feedback: true }],
    version: 7,
    calendar_sequence: 2,
    updated_at: "2026-07-14T09:00:00+08:00",
    ...overrides,
  };
}

function queuedClient(responses) {
  const calls = [];
  return {
    calls,
    client: {
      async request(path, options = {}) {
        calls.push({ kind: "request", path, options });
        const response = responses.shift();
        if (response instanceof Error) throw response;
        return response;
      },
      async download(path, options = {}) {
        calls.push({ kind: "download", path, options });
        return responses.shift();
      },
    },
  };
}

test("lists interviews from the server envelope and maps display fields", async () => {
  const { client, calls } = queuedClient([{ data: [apiInterview()], meta: { count: 1 } }]);
  const controller = createInterviewController({ client });
  const signal = new AbortController().signal;

  const result = await controller.list({ status: "pending_feedback", interviewerId: USER_ID }, { signal });

  assert.deepEqual(calls, [{
    kind: "request",
    path: `/api/v1/interviews?interviewer_id=${USER_ID}&status=pending_feedback`,
    options: { signal },
  }]);
  assert.equal(result.records.length, 1);
  assert.deepEqual(result.records[0], {
    id: INTERVIEW_ID,
    serverBacked: true,
    applicationId: APPLICATION_ID,
    candidateId: CANDIDATE_ID,
    candidate: "赵宁",
    role: "大模型应用工程师",
    jobId: JOB_ID,
    position: "AI 工程师",
    round: "一面",
    date: "2026-07-15",
    dateLabel: "07-15",
    time: "10:00",
    duration: 60,
    method: "视频面试",
    timezone: "Asia/Shanghai",
    interviewerIds: [USER_ID],
    interviewers: ["张小北"],
    participants: [{ id: USER_ID, name: "张小北", role: "interviewer", requiredFeedback: true }],
    location: "https://meeting.example.com/one",
    status: "已完成",
    notification: "已发送",
    feedbackStatus: "待反馈",
    owner: "张小北",
    version: 7,
    calendarSequence: 2,
    jdPriorities: [],
    suggestedQuestions: [],
    summary: "大模型应用工程师",
    history: [],
    feedback: null,
  });
  assert.equal(result.count, 1);
});

test("gets one interview and propagates abort errors unchanged", async () => {
  const abortError = new DOMException("aborted", "AbortError");
  const first = queuedClient([{ data: apiInterview({ status: "confirmed" }) }]);
  const signal = new AbortController().signal;

  const record = await createInterviewController({ client: first.client }).get(INTERVIEW_ID, { signal });
  assert.equal(record.status, "已确认");
  assert.deepEqual(first.calls[0], { kind: "request", path: `/api/v1/interviews/${INTERVIEW_ID}`, options: { signal } });

  await assert.rejects(
    () => createInterviewController({ client: queuedClient([abortError]).client }).get(INTERVIEW_ID),
    (error) => error === abortError,
  );
});

test("creates and reschedules interviews with idempotency and quoted versions", async () => {
  const { client, calls } = queuedClient([
    { data: apiInterview({ version: 1, status: "scheduled" }) },
    { data: apiInterview({ version: 8, status: "rescheduled" }) },
  ]);
  const keys = ["create-key", "patch-key"];
  const controller = createInterviewController({ client, idempotencyKey: () => keys.shift() });
  const signal = new AbortController().signal;
  const form = {
    applicationId: APPLICATION_ID,
    round: "一面",
    method: "视频面试",
    timezone: "Asia/Shanghai",
    date: "2026-07-15",
    time: "10:00",
    duration: 60,
    location: "https://meeting.example.com/one",
    participants: [{ id: USER_ID, role: "interviewer", requiredFeedback: true }],
    allowSoftConflict: true,
  };

  await controller.save(null, form, { signal });
  await controller.save({ id: INTERVIEW_ID, version: 7 }, form, { signal });

  const body = {
    application_id: APPLICATION_ID,
    round_name: "一面",
    method: "video",
    timezone: "Asia/Shanghai",
    starts_at: "2026-07-15T10:00:00+08:00",
    ends_at: "2026-07-15T11:00:00+08:00",
    location: null,
    meeting_url: "https://meeting.example.com/one",
    participants: [{ user_id: USER_ID, role: "interviewer", required_feedback: true }],
    allow_soft_conflict: true,
  };
  assert.deepEqual(calls, [
    { kind: "request", path: "/api/v1/interviews", options: { method: "POST", body, idempotencyKey: "create-key", signal } },
    { kind: "request", path: `/api/v1/interviews/${INTERVIEW_ID}`, options: { method: "PATCH", body: Object.fromEntries(Object.entries(body).filter(([key]) => key !== "application_id")), ifMatch: '"7"', idempotencyKey: "patch-key", signal } },
  ]);
});

test("checks conflicts, transitions, downloads calendar, and lists my tasks", async () => {
  const calendar = { blob: new Blob(["BEGIN:VCALENDAR"]), filename: "interview.ics" };
  const { client, calls } = queuedClient([
    { data: { hard: [INTERVIEW_ID], soft: [] } },
    { data: apiInterview({ status: "confirmed", version: 8 }) },
    calendar,
    { data: [{ id: `feedback:${INTERVIEW_ID}`, type: "interview_feedback", interview_id: INTERVIEW_ID }], meta: { count: 1 } },
  ]);
  const controller = createInterviewController({ client, idempotencyKey: () => "transition-key" });
  const signal = new AbortController().signal;

  const conflicts = await controller.checkConflicts(INTERVIEW_ID, {
    date: "2026-07-15", time: "10:00", duration: 60, timezone: "Asia/Shanghai", participantIds: [USER_ID],
  }, { signal });
  const transitioned = await controller.transition({ id: INTERVIEW_ID, version: 7 }, "confirmed", { reason: "候选人确认", signal });
  const downloaded = await controller.downloadCalendar(INTERVIEW_ID, { signal });
  const tasks = await controller.listMyTasks({ signal });

  assert.deepEqual(conflicts, { hard: [INTERVIEW_ID], soft: [] });
  assert.equal(transitioned.status, "已确认");
  assert.equal(downloaded, calendar);
  assert.equal(tasks[0].interviewId, INTERVIEW_ID);
  assert.deepEqual(calls, [
    { kind: "request", path: `/api/v1/interviews/${INTERVIEW_ID}/conflicts`, options: { method: "POST", body: { starts_at: "2026-07-15T10:00:00+08:00", ends_at: "2026-07-15T11:00:00+08:00", participant_ids: [USER_ID], buffer_minutes: 15 }, signal } },
    { kind: "request", path: `/api/v1/interviews/${INTERVIEW_ID}/transitions`, options: { method: "POST", body: { target: "confirmed", reason: "候选人确认" }, ifMatch: '"7"', idempotencyKey: "transition-key", signal } },
    { kind: "download", path: `/api/v1/interviews/${INTERVIEW_ID}/calendar-file`, options: { signal } },
    { kind: "request", path: "/api/v1/me/tasks", options: { signal } },
  ]);
});

test("loads, creates, updates, submits, and amends the current user's feedback", async () => {
  const draft = { id: FEEDBACK_ID, interview_id: INTERVIEW_ID, author_id: USER_ID, status: "draft", ratings: {}, strengths: null, risks: null, conclusion: null, notes: null, version: 1, submitted_at: null };
  const submitted = { ...draft, status: "submitted", version: 3, submitted_at: "2026-07-15T12:00:00+08:00" };
  const { client, calls } = queuedClient([
    { data: { status: "draft", version: 0 } },
    { data: draft },
    { data: submitted },
    { data: { ...submitted, status: "amended", conclusion: "strong_recommend", version: 4 } },
  ]);
  const keys = ["submit-key"];
  const controller = createInterviewController({ client, idempotencyKey: () => keys.shift() });
  const form = {
    ratings: { professional: "优秀", problem: "良好", communication: "良好", fit: "优秀" },
    strengths: "技术基础扎实",
    risks: "管理经验待确认",
    conclusion: "推荐",
    notes: "进入下一轮",
  };

  const empty = await controller.getMyFeedback(INTERVIEW_ID);
  const saved = await controller.saveMyFeedback(INTERVIEW_ID, form, 0);
  const completed = await controller.submitMyFeedback(INTERVIEW_ID);
  const amended = await controller.amendFeedback(saved, { ...form, conclusion: "强烈推荐" }, "补充技术证据");

  const body = { ratings: { professional_ability: 4, problem_solving: 3, communication: 3, role_fit: 4 }, strengths: "技术基础扎实", risks: "管理经验待确认", conclusion: "recommend", notes: "进入下一轮" };
  assert.equal(empty.version, 0);
  assert.equal(saved.id, FEEDBACK_ID);
  assert.equal(completed.status, "submitted");
  assert.equal(amended.conclusion, "强烈推荐");
  assert.deepEqual(calls, [
    { kind: "request", path: `/api/v1/interviews/${INTERVIEW_ID}/my-feedback`, options: {} },
    { kind: "request", path: `/api/v1/interviews/${INTERVIEW_ID}/my-feedback`, options: { method: "PUT", body, ifMatch: '"0"' } },
    { kind: "request", path: `/api/v1/interviews/${INTERVIEW_ID}/my-feedback/submit`, options: { method: "POST", idempotencyKey: "submit-key" } },
    { kind: "request", path: `/api/v1/interview-feedback/${FEEDBACK_ID}/amendments`, options: { method: "POST", body: { ...body, ratings: { professional_ability: 4, problem_solving: 3, communication: 3, role_fit: 4 }, conclusion: "strong_recommend", reason: "补充技术证据" }, ifMatch: '"1"' } },
  ]);
});

test("rejects missing resource identity and version before network I/O", async () => {
  const { client, calls } = queuedClient([]);
  const controller = createInterviewController({ client });

  await assert.rejects(() => controller.get(""), { code: "INTERVIEW_ID_REQUIRED" });
  await assert.rejects(() => controller.save({ id: INTERVIEW_ID }, {}), { code: "INTERVIEW_VERSION_REQUIRED" });
  await assert.rejects(() => controller.saveMyFeedback(INTERVIEW_ID, {}, null), { code: "FEEDBACK_VERSION_REQUIRED" });
  await assert.rejects(() => controller.amendFeedback({ id: FEEDBACK_ID }, {}, "reason"), { code: "FEEDBACK_VERSION_REQUIRED" });
  assert.equal(calls.length, 0);
});

test("candidate interview history is derived only from matching server records", () => {
  const records = [
    { id: INTERVIEW_ID, serverBacked: true, candidateId: CANDIDATE_ID, round: "一面", date: "2026-07-15", time: "10:00", interviewers: ["张小北"], status: "已完成", feedbackStatus: "已提交", feedback: { conclusion: "推荐", strengths: "技术基础扎实" } },
    { id: "other", serverBacked: true, candidateId: "other-candidate", round: "二面", date: "2026-07-16", time: "11:00", interviewers: ["王磊"], status: "已安排", feedbackStatus: "未开始", feedback: null },
    { id: "local", serverBacked: false, candidateId: CANDIDATE_ID, round: "本地夹具" },
  ];

  assert.deepEqual(deriveCandidateInterviews(CANDIDATE_ID, records), [{
    interviewId: INTERVIEW_ID,
    round: "一面",
    time: "2026-07-15 10:00",
    interviewer: "张小北",
    result: "推荐",
    feedback: "技术基础扎实",
  }]);
});
