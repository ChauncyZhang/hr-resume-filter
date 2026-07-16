import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, CalendarDays, Check, CheckCircle2, ChevronLeft, ChevronRight, CircleAlert, ClipboardCopy, RefreshCw, Send, UserRound, Users } from "lucide-react";
import { buildWeekDays, localDateKey, moveWeek, parseLocalDate, weekLabel, weekRange } from "./interviewDateUtils.js";
import { isScheduleCandidateEligible, resolveScheduleCandidateId, shouldHydrateScheduleCandidate } from "./interviewViewState.js";

/* interview-schedule-helpers:start */
export function getScheduleConflictType(result, allowSoftConflict) {
  if (result?.hard?.length) return "hard";
  if (result?.soft?.length && !allowSoftConflict) return "soft";
  return null;
}

export function getScheduleSavedMessage(record) {
  return record ? "面试改期已保存；新的邀请文件可下载；通知待发送" : "面试安排已保存；邀请文件可下载；通知待发送";
}

export async function copyInterviewText(text, clipboard) {
  if (!clipboard || typeof clipboard.writeText !== "function") throw new Error("clipboard unavailable");
  await clipboard.writeText(text);
}
/* interview-schedule-helpers:end */

const timeSlots = Array.from({ length: 19 }, (_, index) => {
  const minutes = 9 * 60 + index * 30;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
});

function offsetFor(timezone) {
  return ["Asia/Shanghai", "Asia/Singapore"].includes(timezone) ? "+08:00" : "Z";
}

function slotWindow(date, time, duration, timezone) {
  const start = new Date(`${date}T${time}:00${offsetFor(timezone)}`).getTime();
  return { start, end: start + Number(duration) * 60000 };
}

export function getAvailabilitySlotState(availability, date, time, duration, timezone) {
  if (!availability || availability.status !== "ready") return "unknown";
  const selected = slotWindow(date, time, duration, timezone);
  const buffer = availability.data.bufferMinutes * 60000;
  for (const participant of availability.data.participants) {
    if (participant.status !== "confirmed") return "unknown";
    for (const busy of participant.busy) {
      const start = new Date(busy.startsAt).getTime();
      const end = new Date(busy.endsAt).getTime();
      if (selected.start < end && start < selected.end) return "conflict";
      if (selected.start < end + buffer && start - buffer < selected.end) return "buffer";
    }
  }
  return "available";
}

const slotLabels = { available: "可排", conflict: "冲突", buffer: "缓冲不足", unknown: "无法确认" };

export function ScheduleWorkspace({ record, candidateId, candidates, participantOptions, participantStatus, onBack, backLabel, onSave, onCheckConflicts, onGetAvailability, onNotify }) {
  const recordCandidate = record ? { id: record.candidateId, candidateId: record.candidateId, name: record.candidate, position: record.position, role: record.role } : null;
  const fallback = candidates.find((item) => item.id === candidateId || item.candidateId === candidateId) || recordCandidate || candidates.find((item) => item.stage === "待安排") || candidates[0];
  const [step, setStep] = useState(1);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const initialReference = parseLocalDate(record?.date) || new Date();
  const [weekReference, setWeekReference] = useState(initialReference);
  const [availability, setAvailability] = useState({ status: "idle", data: null });
  const [form, setForm] = useState(() => ({
    candidateId: resolveScheduleCandidateId(record, candidateId, fallback), position: record?.position || fallback?.position || "", round: record?.round || "一面",
    method: record?.method || "视频面试", timezone: record?.timezone || "Asia/Shanghai", date: record?.date || "", time: record?.time || "", duration: record?.duration || 60,
    interviewerIds: record?.interviewerIds || [], location: record?.location === "未填写" ? "" : record?.location || "",
    candidateMessage: "您好，诚邀您参加本次面试，请提前 5 分钟进入会议。", interviewerMessage: "您有一场新的面试任务，请提前查看候选人材料与职位重点。",
  }));
  useEffect(() => {
    if (record || !candidateId) return;
    const loadedCandidate = candidates.find((item) => item.id === candidateId || item.candidateId === candidateId);
    if (!loadedCandidate) return;
    setForm((current) => shouldHydrateScheduleCandidate(current.candidateId, candidateId) ? {
      ...current,
      candidateId: loadedCandidate.candidateId || loadedCandidate.id,
      position: current.position || loadedCandidate.position || "",
    } : current);
  }, [candidateId, candidates, record]);
  const candidate = candidates.find((item) => item.id === form.candidateId || item.candidateId === form.candidateId) || fallback;
  const candidateOptions = candidate && !candidates.some((item) => (item.candidateId || item.id) === (candidate.candidateId || candidate.id)) ? [candidate, ...candidates] : candidates;
  const selectedInterviewers = participantOptions.filter((item) => form.interviewerIds.includes(item.id));
  const weekDays = useMemo(() => buildWeekDays(weekReference), [weekReference]);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: "" }));
    setSubmitError("");
  }

  function toggleInterviewer(id) {
    update("interviewerIds", form.interviewerIds.includes(id) ? form.interviewerIds.filter((item) => item !== id) : [...form.interviewerIds, id]);
    setAvailability({ status: "idle", data: null });
  }

  function continueFromBasics() {
    const next = {};
    if (!form.candidateId) next.candidateId = "请选择候选人";
    else if (!record && candidate && !isScheduleCandidateEligible(candidate)) next.candidateId = `当前处于“${candidate.stage}”，该阶段不能安排新面试`;
    if (!form.position.trim()) next.position = "请确认应聘职位";
    setErrors(next);
    if (!Object.keys(next).length) setStep(2);
  }

  async function loadAvailability(reference = weekReference) {
    if (!form.interviewerIds.length) { setErrors((current) => ({ ...current, interviewers: "至少选择一位面试官" })); return; }
    const range = weekRange(reference);
    setAvailability({ status: "loading", data: null });
    try {
      const data = await onGetAvailability({ ...range, participantIds: form.interviewerIds, timezone: form.timezone, buffer: 15, exclude: record?.id || "" });
      setAvailability({ status: "ready", data });
    } catch (error) {
      if (error?.name !== "AbortError") setAvailability({ status: "error", data: null });
    }
  }

  function changeWeek(amount) {
    const reference = moveWeek(weekReference, amount);
    setWeekReference(reference);
    update("date", ""); update("time", "");
    void loadAvailability(reference);
  }

  function continueToTime() {
    if (availability.status !== "ready") return;
    setStep(3);
  }

  function chooseSlot(date, time) {
    if (getAvailabilitySlotState(availability, date, time, form.duration, form.timezone) !== "available") return;
    setForm((current) => ({ ...current, date, time }));
    setStep(4);
  }

  async function save() {
    const next = {};
    if (!form.location.trim()) next.location = form.method === "视频面试" ? "请填写会议链接" : "请填写地点或联系说明";
    setErrors(next); if (Object.keys(next).length) return;
    setSubmitting(true); setSubmitError("");
    try {
      const finalConflict = await onCheckConflicts(record, { ...form, applicationId: candidate?.applicationId || candidate?.application?.id || record?.applicationId || "", participantIds: form.interviewerIds });
      const conflictType = getScheduleConflictType(finalConflict, false);
      if (conflictType) { setSubmitError(conflictType === "hard" ? "保存前检查发现该时段已有冲突，请重新选择时间。" : "保存前检查发现缓冲不足，请重新选择时间。"); return; }
      await onSave(record, { ...form, applicationId: candidate?.applicationId || candidate?.application?.id || "", participants: selectedInterviewers.map((item) => ({ id: item.id, role: "interviewer", requiredFeedback: true })), allowSoftConflict: false });
      onNotify(getScheduleSavedMessage(record));
    } catch (error) {
      if (error?.name !== "AbortError") setSubmitError(error?.code === "schedule_hard_conflict" ? "该时段存在面试冲突，请调整后重试。" : "无法完成权威冲突检查或保存，当前内容已保留。请重试。");
    } finally { setSubmitting(false); }
  }

  async function copyInvitation(text, label) {
    try { await copyInterviewText(text, typeof navigator === "undefined" ? null : navigator.clipboard); onNotify(`${label}已复制`); }
    catch { onNotify(`${label}复制失败，请手动选择文本复制`); }
  }

  const steps = ["候选人与轮次", "选择面试官与忙闲", "选择日期时间", "确认邀请"];
  return <div className="interview-page schedule-page"><button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />{backLabel}</button>
    <div className="schedule-heading"><div><h2>{record ? "改期面试" : "安排面试"}</h2><p>{candidate?.name || "选择候选人"} · {form.position}</p></div><div className="schedule-steps">{steps.map((label, index) => <span key={label} className={step >= index + 1 ? "active" : ""}><i>{step > index + 1 ? <Check size={13} /> : index + 1}</i>{label}</span>)}</div></div>
    <div className="schedule-layout"><main className="schedule-main">
      {step === 1 && <section className="schedule-section"><header><CalendarDays size={19} /><div><h3>候选人与面试设置</h3><p>先确认对象、轮次和时长，不预设面试时间。</p></div></header><div className="schedule-grid"><label>候选人<select value={form.candidateId} disabled={Boolean(record)} onChange={(event) => { const selected = candidates.find((item) => item.id === event.target.value || item.candidateId === event.target.value); setForm((current) => ({ ...current, candidateId: event.target.value, position: selected?.position || current.position })); }}><option value="">请选择候选人</option>{candidateOptions.map((item) => <option value={item.candidateId || item.id} key={item.applicationId || item.id}>{item.name} · {item.position}</option>)}</select>{errors.candidateId && <small className="field-error">{errors.candidateId}</small>}</label><label>应聘职位<input value={form.position} onChange={(event) => update("position", event.target.value)} />{errors.position && <small className="field-error">{errors.position}</small>}</label><label>面试轮次<select value={form.round} onChange={(event) => update("round", event.target.value)}><option>电话沟通</option><option>一面</option><option>二面</option><option>终面</option><option>技术面</option></select></label><label>时长<select value={form.duration} onChange={(event) => update("duration", Number(event.target.value))}><option value="30">30 分钟</option><option value="45">45 分钟</option><option value="60">60 分钟</option><option value="90">90 分钟</option></select></label><label>面试方式<select value={form.method} onChange={(event) => update("method", event.target.value)}><option>视频面试</option><option>现场面试</option><option>电话面试</option></select></label><label>时区<select value={form.timezone} onChange={(event) => update("timezone", event.target.value)}><option value="Asia/Shanghai">北京时间 GMT+8</option><option value="Asia/Singapore">新加坡 GMT+8</option></select></label></div><footer><button className="button primary" type="button" onClick={continueFromBasics}>下一步：选择面试官<ChevronRight size={16} /></button></footer></section>}
      {step === 2 && <section className="schedule-section"><header><Users size={19} /><div><h3>选择面试官并查看忙闲</h3><p>忙碌内容仅显示为“已有安排”，不会暴露日历详情。</p></div></header><div className="interviewer-picker"><strong>面试官</strong><div>{participantOptions.map((person) => <label key={person.id} className={form.interviewerIds.includes(person.id) ? "selected" : ""}><input type="checkbox" checked={form.interviewerIds.includes(person.id)} onChange={() => toggleInterviewer(person.id)} /><span><UserRound size={16} /></span><strong>{person.name}</strong><small>面试参与人</small></label>)}</div>{participantStatus === "loading" && <p><RefreshCw size={14} />正在加载可选面试官</p>}{participantStatus === "error" && <p className="field-error"><CircleAlert size={14} />面试官目录加载失败</p>}{errors.interviewers && <p className="field-error">{errors.interviewers}</p>}</div><div className="availability-toolbar"><button type="button" aria-label="上一周" onClick={() => changeWeek(-1)}><ChevronLeft size={16} /></button><strong>{weekLabel(weekReference)}</strong><button type="button" aria-label="下一周" onClick={() => changeWeek(1)}><ChevronRight size={16} /></button><input aria-label="选择忙闲周" type="date" value={weekDays[0].key} onChange={(event) => { const reference = parseLocalDate(event.target.value); if (reference) { setWeekReference(reference); void loadAvailability(reference); } }} /><button className="button secondary" type="button" disabled={!form.interviewerIds.length || availability.status === "loading"} onClick={() => void loadAvailability()}>{availability.status === "loading" ? "正在查询" : "查看所选周忙闲"}</button></div><div className="availability-legend"><span className="available">可排</span><span className="conflict">冲突</span><span className="buffer">缓冲不足</span><span className="unknown">无法确认</span></div><div className="availability-timeline" aria-live="polite">{availability.status === "idle" && <p>选择面试官后查询所选周忙闲。</p>}{availability.status === "loading" && <p>正在确认忙闲，请稍候。</p>}{availability.status === "error" && <p role="alert"><AlertTriangle size={16} />忙闲无法确认，不会按空闲处理。请重试。</p>}{availability.status === "ready" && selectedInterviewers.map((person) => { const participant = availability.data.participants.find((item) => item.participantId === person.id); return <section key={person.id}><strong>{person.name}</strong>{participant?.status !== "confirmed" ? <span className="unknown">无法确认</span> : participant.busy.length ? participant.busy.map((busy) => <span className="busy" key={`${busy.startsAt}-${busy.endsAt}`}>{new Date(busy.startsAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}–{new Date(busy.endsAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })} · 已有安排</span>) : <span className="available">所选周无已有安排</span>}</section>; })}</div><footer><button className="button secondary" type="button" onClick={() => setStep(1)}>上一步</button><button className="button primary" type="button" disabled={availability.status !== "ready"} onClick={continueToTime}>下一步：选择日期时间<ChevronRight size={16} /></button></footer></section>}
      {step === 3 && <section className="schedule-section"><header><CalendarDays size={19} /><div><h3>选择可用日期时间</h3><p>仅“可排”时段可以选择；冲突、缓冲不足和无法确认均不可选。</p></div></header><div className="schedule-slot-grid">{weekDays.map((day) => <section key={day.key}><header><strong>{day.weekday}</strong><span>{day.label}</span></header><div>{timeSlots.map((time) => { const state = getAvailabilitySlotState(availability, day.key, time, form.duration, form.timezone); return <button type="button" key={time} className={state} disabled={state !== "available" || day.key < localDateKey(new Date())} onClick={() => chooseSlot(day.key, time)}><strong>{time}</strong><span>{slotLabels[state]}</span></button>; })}</div></section>)}</div><footer><button className="button secondary" type="button" onClick={() => setStep(2)}>上一步</button></footer></section>}
      {step === 4 && <section className="schedule-section"><header><Send size={19} /><div><h3>确认邀请</h3><p>保存前会再次执行服务端权威冲突检查。</p></div></header><div className="schedule-summary"><div><span>候选人</span><strong>{candidate?.name} · {form.position}</strong></div><div><span>时间</span><strong>{form.date} {form.time} · {form.duration} 分钟</strong></div><div><span>面试官</span><strong>{selectedInterviewers.map((item) => item.name).join("、")}</strong></div><div><span>方式</span><strong>{form.method}</strong></div></div><label className="schedule-full-field">{form.method === "视频面试" ? "会议链接" : form.method === "现场面试" ? "面试地点" : "联系说明"}<input value={form.location} onChange={(event) => update("location", event.target.value)} />{errors.location && <small className="field-error">{errors.location}</small>}</label><div className="invitation-preview"><section><header><strong>候选人邀请文本</strong><button type="button" onClick={() => void copyInvitation(form.candidateMessage, "候选人邀请文本")}><ClipboardCopy size={14} />复制</button></header><textarea rows="4" value={form.candidateMessage} onChange={(event) => update("candidateMessage", event.target.value)} /></section><section><header><strong>面试官任务文本</strong><button type="button" onClick={() => void copyInvitation(form.interviewerMessage, "面试官任务文本")}><ClipboardCopy size={14} />复制</button></header><textarea rows="4" value={form.interviewerMessage} onChange={(event) => update("interviewerMessage", event.target.value)} /></section></div>{submitError && <div className="feedback-submit-error" role="alert"><CircleAlert size={18} /><p>{submitError}</p></div>}<footer><button className="button secondary" type="button" disabled={submitting} onClick={() => setStep(3)}>上一步</button><button className="button primary" type="button" disabled={submitting} onClick={() => void save()}><CheckCircle2 size={16} />{submitting ? "正在检查并保存" : "确认并保存"}</button></footer></section>}
    </main><aside className="schedule-aside"><section><h3>候选人摘要</h3><strong>{candidate?.name || "待选择"}</strong><p>{candidate?.role || "当前职称未填写"}</p><p>{candidate?.summary || "候选人详情以服务端档案为准。"}</p></section><section><h3>本次安排</h3><dl><div><dt>轮次</dt><dd>{form.round}</dd></div><div><dt>时间</dt><dd>{form.date && form.time ? `${form.date} ${form.time}` : "待选时段"}</dd></div><div><dt>面试官</dt><dd>{selectedInterviewers.map((item) => item.name).join("、") || "待选择"}</dd></div></dl></section></aside></div>
  </div>;
}

export default ScheduleWorkspace;
