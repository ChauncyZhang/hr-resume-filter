import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  CalendarPlus,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  ClipboardCopy,
  Clock3,
  Download,
  FileText,
  List,
  RefreshCw,
  Search,
  Send,
  UserRound,
  Users,
} from "lucide-react";

/* feedback-draft-helpers:start */
export const INTERVIEW_FEEDBACK_DRAFT_PREFIX = "ats.interview-feedback-draft.v1:";

export function getInterviewFeedbackDraftKey(interviewId) {
  return `${INTERVIEW_FEEDBACK_DRAFT_PREFIX}${interviewId}`;
}

function defaultDraftStorage() {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function loadInterviewFeedbackDraft(record, storage = defaultDraftStorage()) {
  if (!record?.id || record.feedback || !storage) return null;
  try {
    const value = storage.getItem(getInterviewFeedbackDraftKey(record.id));
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

export function saveInterviewFeedbackDraft(interviewId, draft, storage = defaultDraftStorage()) {
  if (!interviewId || !storage) return false;
  try {
    storage.setItem(getInterviewFeedbackDraftKey(interviewId), JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

export function clearInterviewFeedbackDraft(interviewId, storage = defaultDraftStorage()) {
  if (!interviewId || !storage) return false;
  try {
    storage.removeItem(getInterviewFeedbackDraftKey(interviewId));
    return true;
  } catch {
    return false;
  }
}
/* feedback-draft-helpers:end */

export const initialInterviewRecords = [
  { id: "INT-001", candidateId: "CAN-003", candidate: "赵宁", role: "大模型应用工程师", position: "AI 工程师", round: "一面", date: "2026-07-11", dateLabel: "07-11 今天", time: "15:00", duration: 60, method: "视频面试", timezone: "Asia/Shanghai", interviewers: ["张小北", "王磊"], location: "https://meeting.example.com/ai-001", status: "已安排", notification: "已发送", feedbackStatus: "未开始", owner: "张小北", jdPriorities: ["RAG 生产经验", "Agent 工程能力", "系统设计"], suggestedQuestions: ["如何评估 RAG 召回质量？", "Agent 工具调用失败如何降级？"], summary: "6 年 NLP 与大模型应用经验，负责过百万级知识库问答系统。", history: [] },
  { id: "INT-002", candidateId: "CAN-005", candidate: "孙悦", role: "AI 产品经理", position: "产品经理", round: "一面", date: "2026-07-11", dateLabel: "07-11 今天", time: "14:00", duration: 45, method: "视频面试", timezone: "Asia/Shanghai", interviewers: ["张小北", "王磊"], location: "https://meeting.example.com/pm-002", status: "已完成", notification: "已发送", feedbackStatus: "待反馈", owner: "张小北", jdPriorities: ["B 端产品方法", "AI 产品理解", "跨团队协作"], suggestedQuestions: ["如何定义 AI 功能的成功指标？", "如何处理模型能力与用户预期差距？"], summary: "5 年企业服务产品经验，熟悉 AI 产品从需求到商业化的完整过程。", history: [] },
  { id: "INT-003", candidateId: "CAN-006", candidate: "刘洋", role: "前端工程师", position: "前端工程师", round: "技术面", date: "2026-07-12", dateLabel: "07-12 明天", time: "10:00", duration: 60, method: "现场面试", timezone: "Asia/Shanghai", interviewers: ["赵强"], location: "北京办公室 3F-海棠", status: "已安排", notification: "已发送", feedbackStatus: "未开始", owner: "刘思远", jdPriorities: ["React 工程能力", "复杂后台经验", "设计系统"], suggestedQuestions: ["如何治理大型前端项目的状态？"], summary: "5 年前端工程经验，有复杂后台和设计系统建设经验。", history: [] },
  { id: "INT-004", candidateId: "CAN-002", candidate: "王晨", role: "算法工程师", position: "AI 工程师", round: "一面", date: "2026-07-13", dateLabel: "07-13 周一", time: "11:00", duration: 45, method: "电话面试", timezone: "Asia/Shanghai", interviewers: ["陈雨"], location: "HR 外呼", status: "待确认", notification: "待发送", feedbackStatus: "未开始", owner: "张小北", jdPriorities: ["机器学习基础", "LLM 应用经验"], suggestedQuestions: ["大模型项目中承担了哪些职责？"], summary: "4 年推荐算法经验，大模型生产经验需要进一步确认。", history: [] },
  { id: "INT-005", candidateId: "CAN-004", candidate: "陈浩", role: "Java 开发工程师", position: "Java 后端工程师", round: "二面", date: "2026-07-14", dateLabel: "07-14 周二", time: "16:00", duration: 60, method: "视频面试", timezone: "Asia/Shanghai", interviewers: ["陈雨", "李明"], location: "https://meeting.example.com/java-005", status: "已安排", notification: "发送失败", feedbackStatus: "未开始", owner: "陈雨", jdPriorities: ["高并发系统", "微服务治理", "数据库设计"], suggestedQuestions: ["如何定位线上接口延迟抖动？"], summary: "7 年 Java 后端经验，具备高并发交易系统和微服务治理经验。", history: [] },
  { id: "INT-006", candidateId: "CAN-006", candidate: "刘洋", role: "前端工程师", position: "前端工程师", round: "一面", date: "2026-07-10", dateLabel: "07-10 昨天", time: "10:00", duration: 60, method: "视频面试", timezone: "Asia/Shanghai", interviewers: ["赵强"], location: "https://meeting.example.com/fe-006", status: "已完成", notification: "已发送", feedbackStatus: "已提交", owner: "刘思远", jdPriorities: ["React", "TypeScript", "工程质量"], suggestedQuestions: ["如何建设可维护的组件库？"], summary: "工程能力扎实，复杂后台经验匹配。", history: [], feedback: { ratings: { professional: "优秀", problem: "优秀", communication: "良好", fit: "良好" }, strengths: "工程基础扎实，问题拆解清楚。", risks: "管理经验较少。", conclusion: "推荐", notes: "建议进入下一轮。", submittedBy: "赵强", submittedAt: "2026-07-10 11:20", canEdit: false } },
];

const dayColumns = [
  ["2026-07-11", "07-11", "今天"],
  ["2026-07-12", "07-12", "明天"],
  ["2026-07-13", "07-13", "周一"],
  ["2026-07-14", "07-14", "周二"],
  ["2026-07-15", "07-15", "周三"],
];
const interviewHours = Array.from({ length: 14 }, (_, index) => String(index + 8).padStart(2, "0"));
const interviewMinutes = ["00", "15", "30", "45"];

function StatusTag({ status }) {
  const tone = status === "已完成" || status === "已提交" || status === "已发送" ? "success" : status === "发送失败" || status === "已取消" ? "danger" : status === "待反馈" || status === "待确认" ? "warning" : "info";
  return <span className={`interview-status ${tone}`}>{status}</span>;
}

function InterviewList({ records, onSchedule, onFeedback, onUpdate, onNotify, canSchedule = true, interviewerName = "张小北" }) {
  const [view, setView] = useState("list");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("全部状态");
  const [date, setDate] = useState("本周");
  const [mineOnly, setMineOnly] = useState(!canSchedule);

  const filtered = useMemo(() => records.filter((item) => {
    const text = `${item.candidate}${item.position}${item.round}${item.interviewers.join("")}`.toLowerCase();
    return (!query || text.includes(query.toLowerCase())) && (status === "全部状态" || item.status === status || item.feedbackStatus === status) && (!(mineOnly || !canSchedule) || item.interviewers.includes(interviewerName)) && (date === "全部日期" || item.date >= "2026-07-11");
  }), [canSchedule, date, interviewerName, mineOnly, query, records, status]);

  function retryNotification(record) {
    onUpdate({ ...record, notification: "已发送", history: [{ time: "刚刚", action: "重试候选人通知成功" }, ...record.history] });
    onNotify("候选人和面试官通知已重新发送");
  }

  return <div className="interview-page interview-list-page">
    <div className="interview-page-heading"><div><h2>面试</h2><p>{canSchedule ? "统一查看排期、冲突、通知状态和待反馈任务。" : "仅展示你参与的面试和待反馈任务。"}</p></div>{canSchedule && <button className="button primary" type="button" onClick={() => onSchedule(null)}><CalendarPlus size={17} />安排面试</button>}</div>
    <section className="interview-list-panel">
      <div className="interview-toolbar"><div className="segmented-control" aria-label="面试视图"><button type="button" className={view === "list" ? "active" : ""} onClick={() => setView("list")}><List size={15} />列表</button><button type="button" className={view === "calendar" ? "active" : ""} onClick={() => setView("calendar")}><CalendarDays size={15} />周日历</button></div><label className="interview-search"><Search size={16} /><input aria-label="搜索面试" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索候选人、职位或面试官" /></label><label className="interview-select"><select aria-label="日期筛选" value={date} onChange={(event) => setDate(event.target.value)}><option>本周</option><option>全部日期</option></select><ChevronDown size={14} /></label><label className="interview-select"><select aria-label="状态筛选" value={status} onChange={(event) => setStatus(event.target.value)}><option>全部状态</option><option>已安排</option><option>待确认</option><option>已完成</option><option>待反馈</option><option>已提交</option></select><ChevronDown size={14} /></label>{canSchedule && <label className="mine-toggle"><input type="checkbox" checked={mineOnly} onChange={(event) => setMineOnly(event.target.checked)} />仅看我的面试</label>}</div>
      {view === "list" ? <div className="interview-table"><div className="interview-table-head"><span>候选人</span><span>职位与轮次</span><span>时间与方式</span><span>面试官</span><span>面试状态</span><span>通知/反馈</span><span>下一步</span></div>{filtered.map((record) => <div className="interview-table-row" key={record.id}><span className="interview-person"><span>{record.candidate.slice(-1)}</span><span><strong>{record.candidate}</strong><small>{record.role}</small></span></span><span><strong>{record.position}</strong><small>{record.round}</small></span><span><strong>{record.dateLabel} {record.time}</strong><small>{record.method} · {record.duration} 分钟</small></span><span><strong>{record.interviewers.join("、")}</strong><small>{record.location}</small></span><span><StatusTag status={record.status} /></span><span className="interview-state-stack"><StatusTag status={record.notification} /><StatusTag status={record.feedbackStatus} /></span><span className="interview-row-actions">{record.notification === "发送失败" && <button type="button" onClick={() => retryNotification(record)}><RefreshCw size={14} />重试</button>}{record.feedbackStatus === "待反馈" || record.feedbackStatus === "已提交" ? <button type="button" onClick={() => onFeedback(record)}>{record.feedbackStatus === "已提交" ? "查看反馈" : "填写反馈"}<ChevronRight size={14} /></button> : record.status !== "已完成" && <button type="button" onClick={() => onSchedule(record)}>改期<ChevronRight size={14} /></button>}</span></div>)}{filtered.length === 0 && <div className="interview-empty"><CalendarDays size={24} /><strong>没有符合条件的面试</strong><span>调整筛选条件或安排新的面试。</span></div>}</div> : <div className="week-calendar">{dayColumns.map(([value, label, weekday]) => { const items = filtered.filter((item) => item.date === value); return <section key={value}><header><strong>{label}</strong><span>{weekday} · {items.length} 场</span></header><div>{items.map((item) => <button type="button" className={`calendar-interview ${item.status === "已完成" ? "complete" : item.notification === "发送失败" ? "failed" : ""}`} key={item.id} onClick={() => item.feedbackStatus === "待反馈" || item.feedbackStatus === "已提交" ? onFeedback(item) : onSchedule(item)}><span><Clock3 size={13} />{item.time} · {item.duration} 分钟</span><strong>{item.candidate}</strong><small>{item.position} · {item.round}</small><small><Users size={12} />{item.interviewers.join("、")}</small><StatusTag status={item.feedbackStatus === "待反馈" ? "待反馈" : item.status} /></button>)}{items.length === 0 && <div className="calendar-empty-slot">暂无面试</div>}</div></section>; })}</div>}
    </section>
  </div>;
}

function ScheduleInterview({ record, candidateId, candidates, records, onBack, onSave, onNotify }) {
  const fallback = candidates.find((item) => item.id === candidateId) || candidates.find((item) => item.stage === "待安排") || candidates[0];
  const [step, setStep] = useState(1);
  const [errors, setErrors] = useState({});
  const [conflict, setConflict] = useState(null);
  const [overrideSoft, setOverrideSoft] = useState(false);
  const [form, setForm] = useState(() => ({ candidateId: record?.candidateId || fallback?.id || "", position: record?.position || fallback?.position || "AI 工程师", round: record?.round || "一面", method: record?.method || "视频面试", timezone: record?.timezone || "Asia/Shanghai", date: record?.date || "2026-07-12", time: record?.time || "10:00", duration: record?.duration || 60, interviewers: record?.interviewers || ["张小北"], location: record?.location || "", candidateMessage: "您好，诚邀您参加本次面试，请提前 5 分钟进入会议。", interviewerMessage: "您有一场新的面试任务，请提前查看候选人材料与职位重点。" }));
  const candidate = candidates.find((item) => item.id === form.candidateId) || fallback;

  function update(field, value) { setForm((current) => ({ ...current, [field]: value })); setErrors((current) => ({ ...current, [field]: "" })); setConflict(null); }
  function toggleInterviewer(name) { update("interviewers", form.interviewers.includes(name) ? form.interviewers.filter((item) => item !== name) : [...form.interviewers, name]); }

  function validateStepOne() {
    const next = {};
    if (!form.candidateId) next.candidateId = "请选择候选人";
    if (!form.position.trim()) next.position = "请确认应聘职位";
    if (!form.date) next.date = "请选择日期";
    if (!form.time) next.time = "请选择开始时间";
    setErrors(next); if (Object.keys(next).length) return;
    setStep(2);
  }

  function checkConflict() {
    const next = {};
    if (!form.interviewers.length) next.interviewers = "至少选择一位面试官";
    if (!form.location.trim()) next.location = form.method === "视频面试" ? "请填写会议链接" : "请填写地点或联系说明";
    setErrors(next); if (Object.keys(next).length) return;
    const exact = records.find((item) => item.id !== record?.id && item.date === form.date && item.time === form.time && item.interviewers.some((name) => form.interviewers.includes(name)) && item.status !== "已取消");
    if (exact) { setConflict({ type: "hard", message: `${exact.interviewers.join("、")} 在 ${exact.dateLabel} ${exact.time} 已有 ${exact.candidate} 的面试。` }); return; }
    if (form.date === "2026-07-11" && form.time === "16:00" && form.interviewers.includes("张小北") && !overrideSoft) { setConflict({ type: "soft", message: "张小北上一场面试 16:00 结束，两个安排之间没有缓冲时间。" }); return; }
    setStep(3);
  }

  function save() {
    const dateMeta = dayColumns.find(([value]) => value === form.date);
    const nextRecord = { ...(record || {}), id: record?.id || `INT-${String(records.length + 1).padStart(3, "0")}`, candidateId: candidate.id, candidate: candidate.name, role: candidate.role, position: form.position, round: form.round, date: form.date, dateLabel: dateMeta ? `${dateMeta[1]} ${dateMeta[2]}` : form.date, time: form.time, duration: Number(form.duration), method: form.method, timezone: form.timezone, interviewers: form.interviewers, location: form.location, status: "已安排", notification: "已发送", feedbackStatus: "未开始", owner: candidate.owner, jdPriorities: record?.jdPriorities || ["专业能力", "问题解决", "岗位匹配"], suggestedQuestions: record?.suggestedQuestions || ["请介绍最有代表性的项目与个人贡献。", "遇到关键问题时如何定位和推动解决？"], summary: candidate.summary, history: [{ time: "刚刚", action: record ? `面试已改期，旧日历版本失效：${record.dateLabel} ${record.time}` : "创建面试并生成日历邀请" }, ...(record?.history || [])] };
    onSave(nextRecord); onNotify(record ? "面试已改期并生成新的邀请" : "面试已安排，候选人与面试官通知已发送");
  }

  return <div className="interview-page schedule-page"><button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />返回面试列表</button><div className="schedule-heading"><div><h2>{record ? "改期面试" : "安排面试"}</h2><p>{candidate?.name || "选择候选人"} · {form.position}</p></div><div className="schedule-steps">{["基础安排", "面试协同", "确认邀请"].map((label, index) => <span key={label} className={step >= index + 1 ? "active" : ""}><i>{step > index + 1 ? <Check size={13} /> : index + 1}</i>{label}</span>)}</div></div>
    <div className="schedule-layout"><main className="schedule-main">
      {step === 1 && <section className="schedule-section"><header><CalendarDays size={19} /><div><h3>基础安排</h3><p>确认候选人、面试轮次和时间。</p></div></header><div className="schedule-grid"><label>候选人<select value={form.candidateId} onChange={(event) => { const selected = candidates.find((item) => item.id === event.target.value); setForm((current) => ({ ...current, candidateId: event.target.value, position: selected?.position || current.position })); }}><option value="">请选择候选人</option>{candidates.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.position}</option>)}</select>{errors.candidateId && <small className="field-error">{errors.candidateId}</small>}</label><label>应聘职位<input value={form.position} onChange={(event) => update("position", event.target.value)} />{errors.position && <small className="field-error">{errors.position}</small>}</label><label>面试轮次<select value={form.round} onChange={(event) => update("round", event.target.value)}><option>电话沟通</option><option>一面</option><option>二面</option><option>终面</option><option>技术面</option></select></label><label>面试方式<select value={form.method} onChange={(event) => update("method", event.target.value)}><option>视频面试</option><option>现场面试</option><option>电话面试</option></select></label><label>时区<select value={form.timezone} onChange={(event) => update("timezone", event.target.value)}><option value="Asia/Shanghai">北京时间 GMT+8</option><option value="Asia/Singapore">新加坡 GMT+8</option></select></label><label>日期<input type="date" value={form.date} onChange={(event) => update("date", event.target.value)} />{errors.date && <small className="field-error">{errors.date}</small>}</label><label>开始时间<div className="time-select-group"><select aria-label="开始时间（小时）" value={form.time.split(":")[0]} onChange={(event) => update("time", `${event.target.value}:${form.time.split(":")[1] || "00"}`)}>{interviewHours.map((hour) => <option value={hour} key={hour}>{hour} 时</option>)}</select><span>:</span><select aria-label="开始时间（分钟）" value={form.time.split(":")[1] || "00"} onChange={(event) => update("time", `${form.time.split(":")[0] || "09"}:${event.target.value}`)}>{interviewMinutes.map((minute) => <option value={minute} key={minute}>{minute} 分</option>)}</select></div>{errors.time && <small className="field-error">{errors.time}</small>}</label><label>时长<select value={form.duration} onChange={(event) => update("duration", event.target.value)}><option value="30">30 分钟</option><option value="45">45 分钟</option><option value="60">60 分钟</option><option value="90">90 分钟</option></select></label></div><footer><button className="button primary" type="button" onClick={validateStepOne}>下一步：面试协同<ChevronRight size={16} /></button></footer></section>}
      {step === 2 && <section className="schedule-section"><header><Users size={19} /><div><h3>面试协同</h3><p>选择面试官，并检查系统内已知冲突。</p></div></header><div className="interviewer-picker"><strong>面试官</strong><div>{["张小北", "王磊", "陈雨", "赵强", "李明"].map((name) => <label key={name} className={form.interviewers.includes(name) ? "selected" : ""}><input type="checkbox" checked={form.interviewers.includes(name)} onChange={() => toggleInterviewer(name)} /><span><UserRound size={16} /></span><strong>{name}</strong><small>{name === "张小北" ? "HR 招聘专员" : "业务面试官"}</small></label>)}</div>{errors.interviewers && <p className="field-error"><CircleAlert size={14} />{errors.interviewers}</p>}</div><label className="schedule-full-field">{form.method === "视频面试" ? "会议链接" : form.method === "现场面试" ? "面试地点" : "联系说明"}<input value={form.location} onChange={(event) => update("location", event.target.value)} placeholder={form.method === "视频面试" ? "https://meeting.example.com/..." : "填写地点或联系说明"} />{errors.location && <small className="field-error">{errors.location}</small>}</label>{conflict && <div className={`schedule-conflict ${conflict.type}`}><AlertTriangle size={20} /><div><strong>{conflict.type === "hard" ? "发现时间冲突" : "安排过于紧凑"}</strong><p>{conflict.message}</p>{conflict.type === "soft" && <label><input type="checkbox" checked={overrideSoft} onChange={(event) => setOverrideSoft(event.target.checked)} />确认保留该时间并继续</label>}</div></div>}<footer><button className="button secondary" type="button" onClick={() => setStep(1)}>上一步</button><button className="button primary" type="button" onClick={checkConflict}>{conflict?.type === "soft" && overrideSoft ? "确认覆盖并继续" : "检查时间并继续"}<ChevronRight size={16} /></button></footer></section>}
      {step === 3 && <section className="schedule-section"><header><Send size={19} /><div><h3>确认邀请</h3><p>保存后生成面试官待办、邀请文本和日历文件。</p></div></header><div className="schedule-summary"><div><span>候选人</span><strong>{candidate.name} · {form.position}</strong></div><div><span>时间</span><strong>{form.date} {form.time} · {form.duration} 分钟</strong></div><div><span>方式</span><strong>{form.method} · {form.timezone}</strong></div><div><span>面试官</span><strong>{form.interviewers.join("、")}</strong></div><div><span>地点/链接</span><strong>{form.location}</strong></div></div><div className="invitation-preview"><section><header><strong>候选人邀请文本</strong><button type="button" onClick={() => onNotify("候选人邀请文本已复制")}><ClipboardCopy size={14} />复制</button></header><textarea rows="4" value={form.candidateMessage} onChange={(event) => update("candidateMessage", event.target.value)} /></section><section><header><strong>面试官任务文本</strong><button type="button" onClick={() => onNotify("面试官任务文本已复制")}><ClipboardCopy size={14} />复制</button></header><textarea rows="4" value={form.interviewerMessage} onChange={(event) => update("interviewerMessage", event.target.value)} /></section></div><div className="calendar-output"><CalendarDays size={18} /><div><strong>日历文件已就绪</strong><span>保存后生成新的 `.ics` 文件；改期时旧版本将失效。</span></div><button type="button" onClick={() => onNotify("日历文件已生成") }><Download size={15} />下载预览</button></div><footer><button className="button secondary" type="button" onClick={() => setStep(2)}>上一步</button><button className="button primary" type="button" onClick={save}><CheckCircle2 size={16} />确认并保存</button></footer></section>}
    </main><aside className="schedule-aside"><section><h3>候选人摘要</h3><strong>{candidate.name}</strong><p>{candidate.role} · {candidate.company}</p><p>{candidate.summary}</p></section><section><h3>本次安排</h3><dl><div><dt>轮次</dt><dd>{form.round}</dd></div><div><dt>时间</dt><dd>{form.date} {form.time}</dd></div><div><dt>方式</dt><dd>{form.method}</dd></div><div><dt>面试官</dt><dd>{form.interviewers.join("、") || "待选择"}</dd></div></dl></section></aside></div></div>;
}

const ratingOptions = ["待评价", "需提升", "一般", "良好", "优秀"];

function FeedbackForm({ record, onBack, onSubmit, onNotify, actorName = "张小北" }) {
  const existing = record.feedback;
  const ownsFeedback = record.interviewers.includes(actorName) && (!existing || existing.submittedBy === actorName);
  const [editing, setEditing] = useState(!existing && ownsFeedback);
  const [editReason, setEditReason] = useState("");
  const [draftState, setDraftState] = useState(existing ? "已提交" : "草稿已保存");
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [failOnce, setFailOnce] = useState(record.id === "INT-002");
  const [form, setForm] = useState(() => existing || loadInterviewFeedbackDraft(record) || { ratings: { professional: "待评价", problem: "待评价", communication: "待评价", fit: "待评价" }, strengths: "", risks: "", conclusion: "", notes: "" });

  useEffect(() => {
    if (!editing) return undefined;
    setDraftState("保存中...");
    const timer = window.setTimeout(() => {
      saveInterviewFeedbackDraft(record.id, form);
      setDraftState("草稿已保存");
    }, 450);
    return () => {
      window.clearTimeout(timer);
      saveInterviewFeedbackDraft(record.id, form);
    };
  }, [editing, form, record.id]);

  function update(field, value) { setForm((current) => ({ ...current, [field]: value })); setErrors((current) => ({ ...current, [field]: "" })); setSubmitError(""); }
  function rate(field, value) { setForm((current) => ({ ...current, ratings: { ...current.ratings, [field]: value } })); setErrors((current) => ({ ...current, [field]: "" })); }
  function submit() {
    const next = {};
    Object.entries(form.ratings).forEach(([key, value]) => { if (value === "待评价") next[key] = "请选择评价"; });
    if (!form.strengths.trim()) next.strengths = "请填写候选人优点";
    if (!form.risks.trim()) next.risks = "请填写风险或待确认项";
    if (!form.conclusion) next.conclusion = "请选择面试结论";
    if (existing && !editReason.trim()) next.editReason = "修改已提交反馈必须填写原因";
    setErrors(next); if (Object.keys(next).length) return;
    if (failOnce) { saveInterviewFeedbackDraft(record.id, form); setFailOnce(false); setSubmitError("网络连接中断，草稿仍保存在本机。请重试提交。"); return; }
    setSubmitError("");
    clearInterviewFeedbackDraft(record.id);
    onSubmit({ ...record, status: "已完成", feedbackStatus: "已提交", feedback: { ...form, submittedBy: actorName, submittedAt: "刚刚", canEdit: true }, history: [{ time: "刚刚", action: existing ? `修改面试反馈；原因：${editReason}` : "提交结构化面试反馈" }, ...record.history] });
    setEditing(false); setDraftState("已提交"); onNotify("面试反馈已提交，下一步由 HR 张小北处理");
  }

  const dimensions = [["professional", "专业能力"], ["problem", "问题解决"], ["communication", "沟通协作"], ["fit", "岗位匹配"]];
  return <div className="interview-page feedback-page"><button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />返回面试列表</button><header className="feedback-header"><div className="feedback-candidate"><span>{record.candidate.slice(-1)}</span><div><div><h2>{record.candidate}</h2><StatusTag status={draftState} /></div><p>{record.position} · {record.round} · {record.dateLabel} {record.time}</p></div></div><div className="feedback-header-actions"><span><CheckCircle2 size={14} />{draftState}</span>{existing && !editing && ownsFeedback && <button className="button secondary" type="button" onClick={() => setEditing(true)}>修改反馈</button>}</div></header>
    <div className="feedback-layout"><main className="feedback-main"><section className="feedback-material"><header><h3>本次面试重点</h3><button type="button" onClick={() => onNotify("候选人简历已打开") }><FileText size={14} />查看脱敏简历</button></header><div className="feedback-priorities">{record.jdPriorities.map((item) => <span key={item}>{item}</span>)}</div><p>{record.summary}</p><details><summary>建议问题（{record.suggestedQuestions.length}）</summary>{record.suggestedQuestions.map((item) => <p key={item}>· {item}</p>)}</details></section>
      <section className="feedback-form-section"><header><h3>结构化评价</h3><p>仅当前面试官可编辑自己的草稿和反馈。</p></header>{dimensions.map(([key, label]) => <div className="rating-row" key={key}><strong>{label}<span>*</span></strong><div>{ratingOptions.slice(1).map((option) => <button type="button" disabled={!editing} className={form.ratings[key] === option ? "active" : ""} key={option} onClick={() => rate(key, option)}>{option}</button>)}</div>{errors[key] && <small className="field-error">{errors[key]}</small>}</div>)}<label>候选人优点 <span>*</span><textarea disabled={!editing} rows="4" value={form.strengths} onChange={(event) => update("strengths", event.target.value)} placeholder="记录与岗位相关的优势和证据" />{errors.strengths && <small className="field-error">{errors.strengths}</small>}</label><label>风险与待确认项 <span>*</span><textarea disabled={!editing} rows="4" value={form.risks} onChange={(event) => update("risks", event.target.value)} placeholder="记录风险、信息缺口或后续建议" />{errors.risks && <small className="field-error">{errors.risks}</small>}</label><div className="feedback-conclusion"><strong>面试结论 <span>*</span></strong><div>{["强烈推荐", "推荐", "保留", "不推荐"].map((option) => <button type="button" disabled={!editing} className={form.conclusion === option ? "active" : ""} key={option} onClick={() => update("conclusion", option)}>{option}</button>)}</div>{errors.conclusion && <small className="field-error">{errors.conclusion}</small>}</div><label>补充说明<textarea disabled={!editing} rows="3" value={form.notes} onChange={(event) => update("notes", event.target.value)} placeholder="可选：给 HR 或下一轮面试官的建议" /></label>{existing && editing && <label className="edit-reason">修改原因 <span>*</span><input value={editReason} onChange={(event) => { setEditReason(event.target.value); setErrors((current) => ({ ...current, editReason: "" })); }} placeholder="说明为什么需要修改已提交反馈" />{errors.editReason && <small className="field-error">{errors.editReason}</small>}</label>}{submitError && <div className="feedback-submit-error"><CircleAlert size={18} /><div><strong>反馈提交失败</strong><p>{submitError}</p></div><button type="button" onClick={submit}><RefreshCw size={14} />重试提交</button></div>}{editing && <footer><span><Check size={14} />{draftState}</span><button className="button primary" type="button" onClick={submit}><Send size={16} />提交反馈</button></footer>}</section></main><aside className="feedback-aside"><section><h3>面试信息</h3><dl><div><dt>方式</dt><dd>{record.method}</dd></div><div><dt>时长</dt><dd>{record.duration} 分钟</dd></div><div><dt>面试官</dt><dd>{record.interviewers.join("、")}</dd></div><div><dt>负责人</dt><dd>{record.owner}</dd></div></dl></section><section><h3>提交后</h3><p>HR 将汇总本轮反馈，并决定推进、追加面试、淘汰或加入人才库。</p></section>{existing && !existing.canEdit && <section className="permission-note"><AlertTriangle size={17} /><div><strong>只读反馈</strong><p>该反馈由 {existing.submittedBy} 提交，你没有修改权限。</p></div></section>}</aside></div></div>;
}

export function InterviewsWorkspace({ mode, setMode, selectedInterview, setSelectedInterview, scheduleCandidateId, records, setRecords, candidates, onNotify, onBack, onRecordSaved, canSchedule = true, actorName = "张小北" }) {
  function updateRecord(updated) { if (!canSchedule && updated.feedbackStatus !== "已提交") { onNotify("当前角色无权修改面试安排"); return; } setRecords((current) => current.map((item) => item.id === updated.id ? updated : item)); setSelectedInterview(updated); }
  function openSchedule(record) { if (!canSchedule) { onNotify("面试官不能创建或改期面试"); return; } setSelectedInterview(record); setMode("schedule"); }
  function openFeedback(record) { setSelectedInterview(record); setMode("feedback"); }
  function backToList() { setSelectedInterview(null); setMode("list"); if (onBack) onBack(); }
  if (mode === "schedule" && canSchedule) return <ScheduleInterview record={selectedInterview} candidateId={scheduleCandidateId} candidates={candidates} records={records} onBack={backToList} onSave={(saved) => { setRecords((current) => current.some((item) => item.id === saved.id) ? current.map((item) => item.id === saved.id ? saved : item) : [saved, ...current]); if (onRecordSaved) onRecordSaved(saved); setSelectedInterview(null); setMode("list"); }} onNotify={onNotify} />;
  if (mode === "feedback" && selectedInterview) return <FeedbackForm record={selectedInterview} onBack={backToList} onSubmit={(updated) => { updateRecord(updated); if (onRecordSaved) onRecordSaved(updated); }} onNotify={onNotify} actorName={actorName} />;
  return <InterviewList records={records} onSchedule={openSchedule} onFeedback={openFeedback} onUpdate={updateRecord} onNotify={onNotify} canSchedule={canSchedule} interviewerName={actorName} />;
}
