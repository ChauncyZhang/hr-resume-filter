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

export function getInterviewFeedbackDraftKey(userId, interviewId) {
  return `${INTERVIEW_FEEDBACK_DRAFT_PREFIX}${userId}:${interviewId}`;
}

function defaultDraftStorage() {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function loadInterviewFeedbackDraft(userId, record, storage = defaultDraftStorage()) {
  if (!userId || !record?.id || record.feedback || !storage) return null;
  try {
    const value = storage.getItem(getInterviewFeedbackDraftKey(userId, record.id));
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

export function saveInterviewFeedbackDraft(userId, interviewId, draft, storage = defaultDraftStorage()) {
  if (!userId || !interviewId || !storage) return false;
  try {
    storage.setItem(getInterviewFeedbackDraftKey(userId, interviewId), JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

export function clearInterviewFeedbackDraft(userId, interviewId, storage = defaultDraftStorage()) {
  if (!userId || !interviewId || !storage) return false;
  try {
    storage.removeItem(getInterviewFeedbackDraftKey(userId, interviewId));
    return true;
  } catch {
    return false;
  }
}
/* feedback-draft-helpers:end */

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

function InterviewList({ records, status: loadStatus, error, onRetry, onSchedule, onFeedback, onDownload, onTransition, canSchedule = true, interviewerName = "张小北" }) {
  const [view, setView] = useState("list");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("全部状态");
  const [date, setDate] = useState("本周");
  const [mineOnly, setMineOnly] = useState(!canSchedule);

  const filtered = useMemo(() => records.filter((item) => {
    const text = `${item.candidate}${item.position}${item.round}${item.interviewers.join("")}`.toLowerCase();
    return (!query || text.includes(query.toLowerCase())) && (status === "全部状态" || item.status === status || item.feedbackStatus === status) && (!(mineOnly || !canSchedule) || item.interviewers.includes(interviewerName)) && (date === "全部日期" || item.date >= "2026-07-11");
  }), [canSchedule, date, interviewerName, mineOnly, query, records, status]);

  return <div className="interview-page interview-list-page">
    <div className="interview-page-heading"><div><h2>面试</h2><p>{canSchedule ? "统一查看排期、冲突、通知状态和待反馈任务。" : "仅展示你参与的面试和待反馈任务。"}</p></div>{canSchedule && <button className="button primary" type="button" onClick={() => onSchedule(null)}><CalendarPlus size={17} />安排面试</button>}</div>
    {loadStatus === "loading" && records.length === 0 && <div className="workbench-status" role="status" aria-live="polite"><CalendarDays size={22} /><div><strong>正在加载面试</strong><p>正在读取服务端面试安排与反馈状态。</p></div></div>}
    {loadStatus === "error" && records.length === 0 && <div className="workbench-status error" role="alert"><CircleAlert size={22} /><div><strong>面试暂时无法加载</strong><p>{error}</p></div><button className="button secondary" type="button" onClick={onRetry}>重试</button></div>}
    {loadStatus === "ready" && records.length === 0 && <div className="workbench-status empty"><CalendarDays size={22} /><div><strong>暂无面试安排</strong><p>{canSchedule ? "可以从待安排候选人创建第一场面试。" : "当前没有分配给你的面试或反馈任务。"}</p></div></div>}
    {records.length > 0 && loadStatus === "error" && <div className="workbench-inline-error" role="alert"><CircleAlert size={17} /><span>{error}，当前展示上次成功数据。</span><button type="button" onClick={onRetry}>重新加载</button></div>}
    {records.length > 0 && <section className="interview-list-panel">
      <div className="interview-toolbar"><div className="segmented-control" aria-label="面试视图"><button type="button" className={view === "list" ? "active" : ""} onClick={() => setView("list")}><List size={15} />列表</button><button type="button" className={view === "calendar" ? "active" : ""} onClick={() => setView("calendar")}><CalendarDays size={15} />周日历</button></div><label className="interview-search"><Search size={16} /><input aria-label="搜索面试" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索候选人、职位或面试官" /></label><label className="interview-select"><select aria-label="日期筛选" value={date} onChange={(event) => setDate(event.target.value)}><option>本周</option><option>全部日期</option></select><ChevronDown size={14} /></label><label className="interview-select"><select aria-label="状态筛选" value={status} onChange={(event) => setStatus(event.target.value)}><option>全部状态</option><option>已安排</option><option>待确认</option><option>已完成</option><option>待反馈</option><option>已提交</option></select><ChevronDown size={14} /></label>{canSchedule && <label className="mine-toggle"><input type="checkbox" checked={mineOnly} onChange={(event) => setMineOnly(event.target.checked)} />仅看我的面试</label>}</div>
      {view === "list" ? <div className="interview-table"><div className="interview-table-head"><span>候选人</span><span>职位与轮次</span><span>时间与方式</span><span>面试官</span><span>面试状态</span><span>通知/反馈</span><span>下一步</span></div>{filtered.map((record) => <div className="interview-table-row" key={record.id}><span className="interview-person"><span>{record.candidate.slice(-1)}</span><span><strong>{record.candidate}</strong><small>{record.role}</small></span></span><span><strong>{record.position}</strong><small>{record.round}</small></span><span><strong>{record.dateLabel} {record.time}</strong><small>{record.method} · {record.duration} 分钟</small></span><span><strong>{record.interviewers.join("、")}</strong><small>{record.location}</small></span><span><StatusTag status={record.status} /></span><span className="interview-state-stack"><StatusTag status={record.notification} /><StatusTag status={record.feedbackStatus} /></span><span className="interview-row-actions"><button type="button" onClick={() => onDownload(record)}><Download size={14} />日历</button>{record.feedbackStatus === "待反馈" || record.feedbackStatus === "已提交" ? <button type="button" onClick={() => onFeedback(record)}>{record.feedbackStatus === "已提交" ? "查看反馈" : "填写反馈"}<ChevronRight size={14} /></button> : canSchedule && record.status === "已确认" ? <button type="button" onClick={() => onTransition(record, "completed")}>完成面试<ChevronRight size={14} /></button> : canSchedule && record.status === "已安排" ? <><button type="button" onClick={() => onSchedule(record)}>改期</button><button type="button" onClick={() => onTransition(record, "confirmed")}>确认<ChevronRight size={14} /></button></> : null}</span></div>)}{filtered.length === 0 && <div className="interview-empty"><CalendarDays size={24} /><strong>没有符合条件的面试</strong><span>调整筛选条件或安排新的面试。</span></div>}</div> : <div className="week-calendar">{dayColumns.map(([value, label, weekday]) => { const items = filtered.filter((item) => item.date === value); return <section key={value}><header><strong>{label}</strong><span>{weekday} · {items.length} 场</span></header><div>{items.map((item) => <button type="button" className={`calendar-interview ${item.status === "已完成" ? "complete" : item.notification === "发送失败" ? "failed" : ""}`} key={item.id} onClick={() => item.feedbackStatus === "待反馈" || item.feedbackStatus === "已提交" ? onFeedback(item) : canSchedule ? onSchedule(item) : undefined}><span><Clock3 size={13} />{item.time} · {item.duration} 分钟</span><strong>{item.candidate}</strong><small>{item.position} · {item.round}</small><small><Users size={12} />{item.interviewers.join("、")}</small><StatusTag status={item.feedbackStatus === "待反馈" ? "待反馈" : item.status} /></button>)}{items.length === 0 && <div className="calendar-empty-slot">暂无面试</div>}</div></section>; })}</div>}
    </section>}
  </div>;
}

function ScheduleInterview({ record, candidateId, candidates, participantOptions, onBack, onSave, onCheckConflicts, onNotify }) {
  const fallback = candidates.find((item) => item.id === candidateId || item.candidateId === candidateId) || candidates.find((item) => item.stage === "待安排") || candidates[0];
  const [step, setStep] = useState(1);
  const [errors, setErrors] = useState({});
  const [conflict, setConflict] = useState(null);
  const [overrideSoft, setOverrideSoft] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [form, setForm] = useState(() => ({ candidateId: record?.candidateId || fallback?.candidateId || fallback?.id || "", position: record?.position || fallback?.position || "", round: record?.round || "一面", method: record?.method || "视频面试", timezone: record?.timezone || "Asia/Shanghai", date: record?.date || "", time: record?.time || "10:00", duration: record?.duration || 60, interviewerIds: record?.interviewerIds || participantOptions.slice(0, 1).map((item) => item.id), location: record?.location === "未填写" ? "" : record?.location || "", candidateMessage: "您好，诚邀您参加本次面试，请提前 5 分钟进入会议。", interviewerMessage: "您有一场新的面试任务，请提前查看候选人材料与职位重点。" }));
  const candidate = candidates.find((item) => item.id === form.candidateId || item.candidateId === form.candidateId) || fallback;
  const selectedInterviewers = participantOptions.filter((item) => form.interviewerIds.includes(item.id));

  function update(field, value) { setForm((current) => ({ ...current, [field]: value })); setErrors((current) => ({ ...current, [field]: "" })); setConflict(null); }
  function toggleInterviewer(id) { update("interviewerIds", form.interviewerIds.includes(id) ? form.interviewerIds.filter((item) => item !== id) : [...form.interviewerIds, id]); }

  function validateStepOne() {
    const next = {};
    if (!form.candidateId) next.candidateId = "请选择候选人";
    if (!form.position.trim()) next.position = "请确认应聘职位";
    if (!form.date) next.date = "请选择日期";
    if (!form.time) next.time = "请选择开始时间";
    setErrors(next); if (Object.keys(next).length) return;
    setStep(2);
  }

  async function checkConflict() {
    const next = {};
    if (!form.interviewerIds.length) next.interviewers = "至少选择一位面试官";
    if (!form.location.trim()) next.location = form.method === "视频面试" ? "请填写会议链接" : "请填写地点或联系说明";
    setErrors(next); if (Object.keys(next).length) return;
    setSubmitError("");
    if (!record) { setStep(3); return; }
    try {
      const result = await onCheckConflicts(record, { ...form, participantIds: form.interviewerIds });
      if (result.hard.length) { setConflict({ type: "hard", message: "一位或多位面试官在该时段已有面试，请调整时间。" }); return; }
      if (result.soft.length && !overrideSoft) { setConflict({ type: "soft", message: "一位或多位面试官与相邻面试之间没有足够缓冲时间。" }); return; }
      setStep(3);
    } catch (error) {
      if (error?.name !== "AbortError") setSubmitError("冲突检查失败，当前安排仍保留。请检查网络后重试。");
    }
  }

  async function save() {
    setSubmitting(true); setSubmitError("");
    try {
      await onSave(record, {
        ...form,
        applicationId: candidate?.applicationId || candidate?.application?.id || "",
        participants: selectedInterviewers.map((item) => ({ id: item.id, role: "interviewer", requiredFeedback: true })),
        allowSoftConflict: overrideSoft,
      });
      onNotify(record ? "面试已改期并生成新的邀请" : "面试已安排，候选人与面试官通知已发送");
    } catch (error) {
      if (error?.name !== "AbortError") setSubmitError(error?.code === "schedule_hard_conflict" ? "该时段存在面试冲突，请调整后重试。" : "面试保存失败，表单内容已保留。请检查网络后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return <div className="interview-page schedule-page"><button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />返回面试列表</button><div className="schedule-heading"><div><h2>{record ? "改期面试" : "安排面试"}</h2><p>{candidate?.name || "选择候选人"} · {form.position}</p></div><div className="schedule-steps">{["基础安排", "面试协同", "确认邀请"].map((label, index) => <span key={label} className={step >= index + 1 ? "active" : ""}><i>{step > index + 1 ? <Check size={13} /> : index + 1}</i>{label}</span>)}</div></div>
    <div className="schedule-layout"><main className="schedule-main">
      {step === 1 && <section className="schedule-section"><header><CalendarDays size={19} /><div><h3>基础安排</h3><p>确认候选人、面试轮次和时间。</p></div></header><div className="schedule-grid"><label>候选人<select value={form.candidateId} onChange={(event) => { const selected = candidates.find((item) => item.id === event.target.value || item.candidateId === event.target.value); setForm((current) => ({ ...current, candidateId: event.target.value, position: selected?.position || current.position })); }}><option value="">请选择候选人</option>{candidates.map((item) => <option value={item.candidateId || item.id} key={item.applicationId || item.id}>{item.name} · {item.position}</option>)}</select>{errors.candidateId && <small className="field-error">{errors.candidateId}</small>}</label><label>应聘职位<input value={form.position} onChange={(event) => update("position", event.target.value)} />{errors.position && <small className="field-error">{errors.position}</small>}</label><label>面试轮次<select value={form.round} onChange={(event) => update("round", event.target.value)}><option>电话沟通</option><option>一面</option><option>二面</option><option>终面</option><option>技术面</option></select></label><label>面试方式<select value={form.method} onChange={(event) => update("method", event.target.value)}><option>视频面试</option><option>现场面试</option><option>电话面试</option></select></label><label>时区<select value={form.timezone} onChange={(event) => update("timezone", event.target.value)}><option value="Asia/Shanghai">北京时间 GMT+8</option><option value="Asia/Singapore">新加坡 GMT+8</option></select></label><label>日期<input type="date" value={form.date} onChange={(event) => update("date", event.target.value)} />{errors.date && <small className="field-error">{errors.date}</small>}</label><label>开始时间<div className="time-select-group"><select aria-label="开始时间（小时）" value={form.time.split(":")[0]} onChange={(event) => update("time", `${event.target.value}:${form.time.split(":")[1] || "00"}`)}>{interviewHours.map((hour) => <option value={hour} key={hour}>{hour} 时</option>)}</select><span>:</span><select aria-label="开始时间（分钟）" value={form.time.split(":")[1] || "00"} onChange={(event) => update("time", `${form.time.split(":")[0] || "09"}:${event.target.value}`)}>{interviewMinutes.map((minute) => <option value={minute} key={minute}>{minute} 分</option>)}</select></div>{errors.time && <small className="field-error">{errors.time}</small>}</label><label>时长<select value={form.duration} onChange={(event) => update("duration", event.target.value)}><option value="30">30 分钟</option><option value="45">45 分钟</option><option value="60">60 分钟</option><option value="90">90 分钟</option></select></label></div><footer><button className="button primary" type="button" onClick={validateStepOne}>下一步：面试协同<ChevronRight size={16} /></button></footer></section>}
      {step === 2 && <section className="schedule-section"><header><Users size={19} /><div><h3>面试协同</h3><p>选择面试官，并检查系统内已知冲突。</p></div></header><div className="interviewer-picker"><strong>面试官</strong><div>{participantOptions.map((person) => <label key={person.id} className={form.interviewerIds.includes(person.id) ? "selected" : ""}><input type="checkbox" checked={form.interviewerIds.includes(person.id)} onChange={() => toggleInterviewer(person.id)} /><span><UserRound size={16} /></span><strong>{person.name}</strong><small>面试参与人</small></label>)}</div>{participantOptions.length === 0 && <p className="field-error"><CircleAlert size={14} />暂无可用面试官身份，请刷新后重试</p>}{errors.interviewers && <p className="field-error"><CircleAlert size={14} />{errors.interviewers}</p>}</div><label className="schedule-full-field">{form.method === "视频面试" ? "会议链接" : form.method === "现场面试" ? "面试地点" : "联系说明"}<input value={form.location} onChange={(event) => update("location", event.target.value)} placeholder={form.method === "视频面试" ? "https://meeting.example.com/..." : "填写地点或联系说明"} />{errors.location && <small className="field-error">{errors.location}</small>}</label>{conflict && <div className={`schedule-conflict ${conflict.type}`}><AlertTriangle size={20} /><div><strong>{conflict.type === "hard" ? "发现时间冲突" : "安排过于紧凑"}</strong><p>{conflict.message}</p>{conflict.type === "soft" && <label><input type="checkbox" checked={overrideSoft} onChange={(event) => setOverrideSoft(event.target.checked)} />确认保留该时间并继续</label>}</div></div>}{submitError && <div className="feedback-submit-error" role="alert"><CircleAlert size={18} /><p>{submitError}</p></div>}<footer><button className="button secondary" type="button" onClick={() => setStep(1)}>上一步</button><button className="button primary" type="button" onClick={() => void checkConflict()}>{conflict?.type === "soft" && overrideSoft ? "确认覆盖并继续" : "检查时间并继续"}<ChevronRight size={16} /></button></footer></section>}
      {step === 3 && <section className="schedule-section"><header><Send size={19} /><div><h3>确认邀请</h3><p>保存后生成面试官待办、邀请文本和日历文件。</p></div></header><div className="schedule-summary"><div><span>候选人</span><strong>{candidate?.name || "未选择候选人"} · {form.position}</strong></div><div><span>时间</span><strong>{form.date} {form.time} · {form.duration} 分钟</strong></div><div><span>方式</span><strong>{form.method} · {form.timezone}</strong></div><div><span>面试官</span><strong>{selectedInterviewers.map((item) => item.name).join("、")}</strong></div><div><span>地点/链接</span><strong>{form.location}</strong></div></div><div className="invitation-preview"><section><header><strong>候选人邀请文本</strong><button type="button" onClick={() => onNotify("候选人邀请文本已复制")}><ClipboardCopy size={14} />复制</button></header><textarea rows="4" value={form.candidateMessage} onChange={(event) => update("candidateMessage", event.target.value)} /></section><section><header><strong>面试官任务文本</strong><button type="button" onClick={() => onNotify("面试官任务文本已复制")}><ClipboardCopy size={14} />复制</button></header><textarea rows="4" value={form.interviewerMessage} onChange={(event) => update("interviewerMessage", event.target.value)} /></section></div><div className="calendar-output"><CalendarDays size={18} /><div><strong>日历文件将在保存后生成</strong><span>保存成功后可从面试列表下载最新 `.ics` 文件。</span></div></div>{submitError && <div className="feedback-submit-error" role="alert"><CircleAlert size={18} /><p>{submitError}</p></div>}<footer><button className="button secondary" type="button" disabled={submitting} onClick={() => setStep(2)}>上一步</button><button className="button primary" type="button" disabled={submitting} onClick={() => void save()}><CheckCircle2 size={16} />{submitting ? "正在保存" : "确认并保存"}</button></footer></section>}
    </main><aside className="schedule-aside"><section><h3>候选人摘要</h3><strong>{candidate?.name || "待选择"}</strong><p>{candidate?.role || "当前职称未填写"} · {candidate?.company || ""}</p><p>{candidate?.summary || "候选人详情以服务端档案为准。"}</p></section><section><h3>本次安排</h3><dl><div><dt>轮次</dt><dd>{form.round}</dd></div><div><dt>时间</dt><dd>{form.date} {form.time}</dd></div><div><dt>方式</dt><dd>{form.method}</dd></div><div><dt>面试官</dt><dd>{selectedInterviewers.map((item) => item.name).join("、") || "待选择"}</dd></div></dl></section></aside></div></div>;
}

const ratingOptions = ["待评价", "需提升", "一般", "良好", "优秀"];

function FeedbackForm({ record, onBack, onSaved, onNotify, actorName = "张小北", userId, controller }) {
  const emptyForm = { ratings: { professional: "待评价", problem: "待评价", communication: "待评价", fit: "待评价" }, strengths: "", risks: "", conclusion: "", notes: "" };
  const ownsFeedback = record.interviewerIds.includes(userId) || record.interviewers.includes(actorName);
  const localDraft = useMemo(() => loadInterviewFeedbackDraft(userId, record), [record, userId]);
  const [existing, setExisting] = useState(null);
  const [feedbackVersion, setFeedbackVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(ownsFeedback);
  const [editReason, setEditReason] = useState("");
  const [draftState, setDraftState] = useState(localDraft ? "本机草稿" : "草稿未保存");
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState(() => localDraft || emptyForm);

  useEffect(() => {
    const abortController = new AbortController();
    setLoading(true);
    void controller.getMyFeedback(record.id, { signal: abortController.signal }).then((feedback) => {
      setFeedbackVersion(feedback.version);
      if (feedback.id && ["submitted", "amended"].includes(feedback.status)) {
        setExisting({ ...feedback, submittedBy: actorName, submittedAt: feedback.submittedAt || "已提交", canEdit: ownsFeedback });
        setForm(feedback);
        setEditing(false);
        setDraftState("已提交");
      } else if (!localDraft && feedback.id) {
        setForm(feedback);
        setDraftState("服务端草稿");
      }
      setSubmitError("");
    }).catch((error) => {
      if (error?.name !== "AbortError") setSubmitError("反馈加载失败；本机草稿仍可继续编辑，提交前请重试加载。");
    }).finally(() => setLoading(false));
    return () => abortController.abort();
  }, [actorName, controller, localDraft, ownsFeedback, record.id]);

  useEffect(() => {
    if (!editing) return undefined;
    setDraftState("保存中...");
    const timer = window.setTimeout(() => {
      saveInterviewFeedbackDraft(userId, record.id, form);
      setDraftState("草稿已保存");
    }, 450);
    return () => {
      window.clearTimeout(timer);
      saveInterviewFeedbackDraft(userId, record.id, form);
    };
  }, [editing, form, record.id, userId]);

  function update(field, value) { setForm((current) => ({ ...current, [field]: value })); setErrors((current) => ({ ...current, [field]: "" })); setSubmitError(""); }
  function rate(field, value) { setForm((current) => ({ ...current, ratings: { ...current.ratings, [field]: value } })); setErrors((current) => ({ ...current, [field]: "" })); }
  async function submit() {
    const next = {};
    Object.entries(form.ratings).forEach(([key, value]) => { if (value === "待评价") next[key] = "请选择评价"; });
    if (!form.strengths.trim()) next.strengths = "请填写候选人优点";
    if (!form.risks.trim()) next.risks = "请填写风险或待确认项";
    if (!form.conclusion) next.conclusion = "请选择面试结论";
    if (existing && !editReason.trim()) next.editReason = "修改已提交反馈必须填写原因";
    setErrors(next); if (Object.keys(next).length) return;
    setSubmitting(true); setSubmitError("");
    saveInterviewFeedbackDraft(userId, record.id, form);
    try {
      let feedback;
      if (existing) {
        feedback = await controller.amendFeedback(existing, form, editReason);
      } else {
        const saved = await controller.saveMyFeedback(record.id, form, feedbackVersion);
        setFeedbackVersion(saved.version);
        feedback = await controller.submitMyFeedback(record.id);
      }
      const submitted = { ...feedback, submittedBy: actorName, submittedAt: feedback.submittedAt || "刚刚", canEdit: true };
      setExisting(submitted);
      setForm(feedback);
      setFeedbackVersion(feedback.version);
      clearInterviewFeedbackDraft(userId, record.id);
      setEditing(false); setDraftState("已提交");
      await onSaved(record, submitted);
      onNotify(existing ? "面试反馈修改已保存" : "面试反馈已提交，下一步由 HR 处理");
    } catch (error) {
      if (error?.name !== "AbortError") setSubmitError("网络请求失败，表单和本机草稿均已保留。请重试提交。");
    } finally {
      setSubmitting(false);
    }
  }

  const dimensions = [["professional", "专业能力"], ["problem", "问题解决"], ["communication", "沟通协作"], ["fit", "岗位匹配"]];
  return <div className="interview-page feedback-page"><button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />返回面试列表</button><header className="feedback-header"><div className="feedback-candidate"><span>{record.candidate.slice(-1)}</span><div><div><h2>{record.candidate}</h2><StatusTag status={draftState} /></div><p>{record.position} · {record.round} · {record.dateLabel} {record.time}</p></div></div><div className="feedback-header-actions"><span><CheckCircle2 size={14} />{loading ? "正在加载反馈" : draftState}</span>{existing && !editing && ownsFeedback && <button className="button secondary" type="button" onClick={() => setEditing(true)}>修改反馈</button>}</div></header>
    <div className="feedback-layout"><main className="feedback-main"><section className="feedback-material"><header><h3>本次面试重点</h3><button type="button" onClick={() => onNotify("候选人简历已打开") }><FileText size={14} />查看脱敏简历</button></header><div className="feedback-priorities">{record.jdPriorities.map((item) => <span key={item}>{item}</span>)}</div><p>{record.summary}</p><details><summary>建议问题（{record.suggestedQuestions.length}）</summary>{record.suggestedQuestions.map((item) => <p key={item}>· {item}</p>)}</details></section>
      <section className="feedback-form-section"><header><h3>结构化评价</h3><p>仅当前面试官可编辑自己的草稿和反馈。</p></header>{dimensions.map(([key, label]) => <div className="rating-row" key={key}><strong>{label}<span>*</span></strong><div>{ratingOptions.slice(1).map((option) => <button type="button" disabled={!editing || submitting} className={form.ratings[key] === option ? "active" : ""} key={option} onClick={() => rate(key, option)}>{option}</button>)}</div>{errors[key] && <small className="field-error">{errors[key]}</small>}</div>)}<label>候选人优点 <span>*</span><textarea disabled={!editing || submitting} rows="4" value={form.strengths} onChange={(event) => update("strengths", event.target.value)} placeholder="记录与岗位相关的优势和证据" />{errors.strengths && <small className="field-error">{errors.strengths}</small>}</label><label>风险与待确认项 <span>*</span><textarea disabled={!editing || submitting} rows="4" value={form.risks} onChange={(event) => update("risks", event.target.value)} placeholder="记录风险、信息缺口或后续建议" />{errors.risks && <small className="field-error">{errors.risks}</small>}</label><div className="feedback-conclusion"><strong>面试结论 <span>*</span></strong><div>{["强烈推荐", "推荐", "保留", "不推荐"].map((option) => <button type="button" disabled={!editing || submitting} className={form.conclusion === option ? "active" : ""} key={option} onClick={() => update("conclusion", option)}>{option}</button>)}</div>{errors.conclusion && <small className="field-error">{errors.conclusion}</small>}</div><label>补充说明<textarea disabled={!editing || submitting} rows="3" value={form.notes} onChange={(event) => update("notes", event.target.value)} placeholder="可选：给 HR 或下一轮面试官的建议" /></label>{existing && editing && <label className="edit-reason">修改原因 <span>*</span><input disabled={submitting} value={editReason} onChange={(event) => { setEditReason(event.target.value); setErrors((current) => ({ ...current, editReason: "" })); }} placeholder="说明为什么需要修改已提交反馈" />{errors.editReason && <small className="field-error">{errors.editReason}</small>}</label>}{submitError && <div className="feedback-submit-error" role="alert"><CircleAlert size={18} /><div><strong>反馈请求失败</strong><p>{submitError}</p></div><button type="button" disabled={submitting || loading} onClick={() => void submit()}><RefreshCw size={14} />重试提交</button></div>}{editing && <footer><span><Check size={14} />{draftState}</span><button className="button primary" type="button" disabled={submitting || loading || !ownsFeedback} onClick={() => void submit()}><Send size={16} />{submitting ? "正在提交" : "提交反馈"}</button></footer>}</section></main><aside className="feedback-aside"><section><h3>面试信息</h3><dl><div><dt>方式</dt><dd>{record.method}</dd></div><div><dt>时长</dt><dd>{record.duration} 分钟</dd></div><div><dt>面试官</dt><dd>{record.interviewers.join("、")}</dd></div><div><dt>负责人</dt><dd>{record.owner}</dd></div></dl></section><section><h3>提交后</h3><p>HR 将汇总本轮反馈，并决定推进、追加面试、淘汰或加入人才库。</p></section>{!ownsFeedback && <section className="permission-note"><AlertTriangle size={17} /><div><strong>只读反馈</strong><p>你不是该面试的反馈参与人。</p></div></section>}</aside></div></div>;
}

export function InterviewsWorkspace({ mode, setMode, selectedInterviewId, setSelectedInterviewId, scheduleCandidateId, records, status, error, onRetry, candidates, onNotify, onBack, onRecordsChanged, canSchedule = true, actorName = "张小北", actorId, controller }) {
  const selectedInterview = records.find((item) => item.id === selectedInterviewId) || null;
  const participantOptions = useMemo(() => {
    const people = new Map();
    if (actorId) people.set(actorId, { id: actorId, name: actorName });
    records.flatMap((record) => record.participants || []).forEach((person) => people.set(person.id, { id: person.id, name: person.name }));
    return [...people.values()];
  }, [actorId, actorName, records]);

  function openSchedule(record) { if (!canSchedule) { onNotify("面试官不能创建或改期面试"); return; } setSelectedInterviewId(record?.id || null); setMode("schedule"); }
  function openFeedback(record) { setSelectedInterviewId(record.id); setMode("feedback"); }
  function backToList() { setSelectedInterviewId(null); setMode("list"); if (onBack) onBack(); }

  async function saveRecord(record, form) {
    const saved = await controller.save(record, form);
    await onRecordsChanged(saved);
    setSelectedInterviewId(null);
    setMode("list");
  }

  async function downloadCalendar(record) {
    try {
      const { blob, filename } = await controller.downloadCalendar(record.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      if (error?.name !== "AbortError") onNotify("日历文件下载失败，请检查网络后重试");
    }
  }

  async function transitionRecord(record, target) {
    try {
      const updated = await controller.transition(record, target);
      await onRecordsChanged(updated);
      onNotify(target === "confirmed" ? "面试已确认" : "面试已完成，反馈任务已生成");
    } catch (error) {
      if (error?.name !== "AbortError") onNotify("面试状态更新失败，请刷新后重试");
    }
  }

  if (mode === "schedule" && canSchedule) return <ScheduleInterview record={selectedInterview} candidateId={scheduleCandidateId} candidates={candidates} participantOptions={participantOptions} onBack={backToList} onSave={saveRecord} onCheckConflicts={(record, form) => controller.checkConflicts(record.id, form)} onNotify={onNotify} />;
  if (mode === "feedback" && selectedInterview) return <FeedbackForm record={selectedInterview} onBack={backToList} onSaved={async (_record, feedback) => { await onRecordsChanged({ ...selectedInterview, feedback, feedbackStatus: "已提交" }); }} onNotify={onNotify} actorName={actorName} userId={actorId} controller={controller} />;
  return <InterviewList records={records} status={status} error={error} onRetry={onRetry} onSchedule={openSchedule} onFeedback={openFeedback} onDownload={(record) => void downloadCalendar(record)} onTransition={(record, target) => void transitionRecord(record, target)} canSchedule={canSchedule} interviewerName={actorName} />;
}
