import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BriefcaseBusiness,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  ClipboardCopy,
  Download,
  Eye,
  FileText,
  Filter,
  GraduationCap,
  Mail,
  MessageSquareText,
  Phone,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Tag,
  UserRound,
  UserRoundCheck,
  Users,
  X,
  LoaderCircle,
  RotateCcw,
} from "lucide-react";

const baseTimeline = [
  { time: "今天 10:30", actor: "系统", action: "完成规则评分与 LLM 辅助评估" },
  { time: "今天 10:28", actor: "张小北", action: "从 BOSS 直聘导入简历" },
];

export const initialCandidateRecords = [
  { id: "CAN-001", name: "李嘉明", role: "AI 算法工程师", company: "字节", position: "AI 工程师", stage: "新简历", score: 81, ruleScore: 81, llmScore: 78, recommendation: "可沟通", source: "BOSS 直聘", owner: "张小北", city: "北京", phone: "138****2468", email: "lij***@mail.com", lastActivity: "今天 10:30", tags: ["LLM", "RAG"], skills: ["Python", "PyTorch", "RAG", "Agent"], education: "北京邮电大学 · 计算机硕士", experience: "5 年算法与大模型应用经验", summary: "负责过企业级 RAG 和 Agent 项目，具备从方案设计到上线监控的完整经验。", matched: "Python、LLM、RAG", missing: "Kubernetes", risk: "项目规模和团队职责待确认", llmReason: "语义匹配度较高，项目经历覆盖岗位核心职责。", humanConclusion: null, notes: [], version: 1, timeline: baseTimeline, applications: [{ position: "AI 工程师", state: "新简历", created: "2026-07-11", source: "BOSS 直聘" }], interviews: [] },
  { id: "CAN-002", name: "王晨", role: "算法工程师", company: "腾讯", position: "AI 工程师", stage: "待复核", score: 74, ruleScore: 74, llmScore: 72, recommendation: "人工复核", source: "猎聘", owner: "张小北", city: "深圳", phone: "186****9052", email: "wan***@mail.com", lastActivity: "今天 09:45", tags: ["机器学习"], skills: ["Python", "TensorFlow", "机器学习"], education: "华中科技大学 · 软件工程本科", experience: "4 年推荐算法经验", summary: "算法基础扎实，但大模型项目主要集中在内部验证阶段。", matched: "Python、机器学习", missing: "Agent", risk: "大模型生产经验偏少", llmReason: "基础能力符合，LLM 应用深度需要人工确认。", humanConclusion: null, notes: [], version: 2, timeline: baseTimeline, applications: [{ position: "AI 工程师", state: "待复核", created: "2026-07-10", source: "猎聘" }], interviews: [] },
  { id: "CAN-003", name: "赵宁", role: "大模型应用工程师", company: "百度", position: "AI 工程师", stage: "待沟通", score: 88, ruleScore: 88, llmScore: 84, recommendation: "优先沟通", source: "智联招聘", owner: "陈雨", city: "北京", phone: "139****3306", email: "zha***@mail.com", lastActivity: "昨天 16:30", tags: ["LLM", "Agent", "高优先级"], skills: ["Python", "LangChain", "RAG", "Agent"], education: "浙江大学 · 人工智能硕士", experience: "6 年 NLP 和大模型应用经验", summary: "项目经验与岗位高度匹配，曾负责百万级知识库问答系统。", matched: "LLM、RAG、Agent", missing: "无明显缺失", risk: "到岗时间待确认", llmReason: "核心技能和业务场景均高度匹配。", humanConclusion: "建议推进", notes: ["优先电话沟通到岗时间"], version: 1, timeline: [{ time: "昨天 16:30", actor: "陈雨", action: "添加沟通备注" }, ...baseTimeline], applications: [{ position: "AI 工程师", state: "待沟通", created: "2026-07-09", source: "智联招聘" }], interviews: [] },
  { id: "CAN-004", name: "陈浩", role: "Java 开发工程师", company: "美团", position: "Java 后端工程师", stage: "待安排", score: 79, ruleScore: 82, llmScore: 76, recommendation: "可沟通", source: "员工内推", owner: "陈雨", city: "上海", phone: "137****5811", email: "che***@mail.com", lastActivity: "昨天 14:12", tags: ["Java", "高并发"], skills: ["Java", "Spring Boot", "MySQL", "Redis"], education: "同济大学 · 计算机本科", experience: "7 年 Java 后端经验", summary: "具备高并发交易系统和微服务治理经验。", matched: "Java、Spring Boot、MySQL", missing: "Kubernetes", risk: "薪资预期待确认", llmReason: "后端经验与岗位要求匹配，云原生经历较少。", humanConclusion: "建议推进", notes: [], version: 1, timeline: baseTimeline, applications: [{ position: "Java 后端工程师", state: "待安排", created: "2026-07-08", source: "员工内推" }], interviews: [] },
  { id: "CAN-005", name: "孙悦", role: "AI 产品经理", company: "阿里", position: "产品经理", stage: "面试中", score: 83, ruleScore: 80, llmScore: 83, recommendation: "建议推进", source: "人才库激活", owner: "张小北", city: "杭州", phone: "135****7720", email: "sun***@mail.com", lastActivity: "07-10 18:05", tags: ["AI 产品", "B 端"], skills: ["需求分析", "AI 产品", "项目管理"], education: "上海交通大学 · 管理学硕士", experience: "5 年企业服务产品经验", summary: "熟悉 AI 产品从需求到商业化的完整过程。", matched: "B 端产品、AI 产品、项目管理", missing: "招聘行业", risk: "行业迁移能力待评估", llmReason: "产品能力符合，行业背景需要面试确认。", humanConclusion: "建议推进", notes: [], version: 1, timeline: baseTimeline, applications: [{ position: "产品经理", state: "面试中", created: "2026-07-03", source: "人才库激活" }], interviews: [{ round: "一面", time: "2026-07-10 14:00", interviewer: "王磊", result: "推荐", feedback: "产品方法完整，AI 理解较深入。" }] },
  { id: "CAN-006", name: "刘洋", role: "前端工程师", company: "小米", position: "前端工程师", stage: "待决策", score: 77, ruleScore: 79, llmScore: 75, recommendation: "人工复核", source: "BOSS 直聘", owner: "刘思远", city: "北京", phone: "188****4090", email: "liu***@mail.com", lastActivity: "07-10 15:20", tags: ["React"], skills: ["React", "TypeScript", "CSS"], education: "北京工业大学 · 软件工程本科", experience: "5 年前端工程经验", summary: "有复杂后台和设计系统建设经验。", matched: "React、TypeScript、CSS", missing: "数据可视化", risk: "管理经验较少", llmReason: "技术能力符合，岗位级别需要综合面试反馈。", humanConclusion: "需要补充", notes: [], version: 1, timeline: baseTimeline, applications: [{ position: "前端工程师", state: "待决策", created: "2026-07-01", source: "BOSS 直聘" }], interviews: [{ round: "技术面", time: "2026-07-09 10:00", interviewer: "赵强", result: "推荐", feedback: "工程能力扎实。" }] },
];

const transitions = {
  新简历: ["待复核", "已淘汰"],
  待复核: ["待沟通", "已淘汰"],
  待沟通: ["待安排", "已淘汰", "已撤回"],
  待安排: ["面试中", "已淘汰", "已撤回"],
  面试中: ["待决策", "已淘汰", "已撤回"],
  待决策: ["已录用", "已淘汰"],
  已录用: [],
  已淘汰: [],
  已撤回: [],
};

const serverTransitions = {
  ...transitions,
  待决策: ["已通过", "已淘汰"],
  已通过: ["已录用", "已淘汰"],
};

export function candidateTransitionOptions(stage, serverBacked) {
  return (serverBacked ? serverTransitions : transitions)[stage] || [];
}

export function candidateDetailTabs(serverBacked) {
  return serverBacked
    ? ["档案与简历", "职位申请", "筛选证据", "时间线"]
    : ["档案与简历", "职位申请", "筛选证据", "面试与反馈", "时间线"];
}

export function candidateMutationError(error) {
  return error?.status === 409
    ? "记录已被其他成员更新。你的修改未保存，请刷新后重新确认。"
    : "操作未完成，请稍后重试。";
}

export function resumeDisplayName(resume) {
  if (!resume) return "暂无可用简历";
  return resume.original_filename || resume.filename || (resume.version_number ? `简历版本 ${resume.version_number}` : "候选人简历");
}

function StageTag({ stage }) {
  const terminal = ["已录用", "已淘汰", "已撤回"].includes(stage);
  return <span className={`candidate-stage ${terminal ? "terminal" : ""}`}>{stage}</span>;
}

function CandidateList({ records, onOpen, onUpdate, onNotify, onAddToTalentPool, initialFilters }) {
  const [query, setQuery] = useState("");
  const [position, setPosition] = useState(initialFilters?.position || "全部职位");
  const [stage, setStage] = useState(initialFilters?.stage || "全部阶段");
  const [owner, setOwner] = useState("全部负责人");
  const [minScore, setMinScore] = useState("不限分数");
  const [selected, setSelected] = useState([]);

  useEffect(() => {
    setPosition(initialFilters?.position || "全部职位");
    setStage(initialFilters?.stage || "全部阶段");
  }, [initialFilters]);

  const filtered = useMemo(() => records.filter((candidate) => {
    const text = `${candidate.name}${candidate.role}${candidate.company}${candidate.phone}${candidate.email}`.toLowerCase();
    const applications = candidate.applications?.length ? candidate.applications : [{ position: candidate.position, state: candidate.stage }];
    const applicationMatches = applications.some((application) => (position === "全部职位" || application.position === position) && (stage === "全部阶段" || application.state === stage));
    return (!query || text.includes(query.toLowerCase())) && applicationMatches && (owner === "全部负责人" || candidate.owner === owner) && (minScore === "不限分数" || candidate.score >= Number(minScore));
  }), [minScore, owner, position, query, records, stage]);

  const selectable = filtered.filter((candidate) => transitions[candidate.stage]?.length).map((candidate) => candidate.id);
  const allSelected = selectable.length > 0 && selectable.every((id) => selected.includes(id));

  function bulk(label) {
    if (!selected.length) return;
    if (label === "推进到待复核") onUpdate(records.map((candidate) => selected.includes(candidate.id) && candidate.stage === "新简历" ? { ...candidate, stage: "待复核", lastActivity: "刚刚" } : candidate));
    if (label === "添加标签") onUpdate(records.map((candidate) => selected.includes(candidate.id) && !candidate.tags.includes("批量复核") ? { ...candidate, tags: [...candidate.tags, "批量复核"] } : candidate));
    if (label === "分配给张小北") onUpdate(records.map((candidate) => selected.includes(candidate.id) ? { ...candidate, owner: "张小北" } : candidate));
    onNotify(`已对 ${selected.length} 位候选人执行“${label}”`);
    setSelected([]);
  }

  return <div className="candidate-page candidate-list-page">
    <div className="candidate-page-heading"><div><h2>候选人</h2><p>跨职位搜索、比较和批量处理候选人。</p></div><span>共 {records.length} 人</span></div>
    <section className="candidate-list-panel">
      <div className="candidate-filters">
        <label className="candidate-search"><Search size={17} /><input aria-label="搜索候选人" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索姓名、经历或联系方式" /></label>
        <label><select aria-label="职位筛选" value={position} onChange={(event) => setPosition(event.target.value)}><option>全部职位</option>{[...new Set(records.map((item) => item.position))].map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={14} /></label>
        <label><select aria-label="阶段筛选" value={stage} onChange={(event) => setStage(event.target.value)}><option>全部阶段</option>{Object.keys(transitions).map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={14} /></label>
        <label><select aria-label="负责人筛选" value={owner} onChange={(event) => setOwner(event.target.value)}><option>全部负责人</option>{[...new Set(records.map((item) => item.owner))].map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={14} /></label>
        <label><select aria-label="分数筛选" value={minScore} onChange={(event) => setMinScore(event.target.value)}><option>不限分数</option><option value="80">80 分以上</option><option value="70">70 分以上</option></select><ChevronDown size={14} /></label>
        <button className="button secondary compact" type="button" onClick={() => { setQuery(""); setPosition("全部职位"); setStage("全部阶段"); setOwner("全部负责人"); setMinScore("不限分数"); }}><X size={15} />清空</button>
      </div>
      {selected.length > 0 && <div className="candidate-bulk-bar"><strong>已选择 {selected.length} 人</strong><button type="button" onClick={() => bulk("推进到待复核")}><UserRoundCheck size={15} />推进到待复核</button><button type="button" onClick={() => bulk("添加标签")}><Tag size={15} />添加标签</button><button type="button" onClick={() => bulk("分配给张小北")}><Users size={15} />分配负责人</button><button type="button" onClick={() => { if (onAddToTalentPool) onAddToTalentPool(selected); setSelected([]); }}><BriefcaseBusiness size={15} />加入人才库</button><button type="button" aria-label="清除选择" onClick={() => setSelected([])}><X size={16} /></button></div>}
      <div className="candidate-table">
        <div className="candidate-table-head"><label><input type="checkbox" checked={allSelected} onChange={() => setSelected(allSelected ? selected.filter((id) => !selectable.includes(id)) : [...new Set([...selected, ...selectable])])} /></label><span>候选人</span><span>当前申请</span><span>阶段</span><span>匹配分</span><span>来源</span><span>负责人</span><span>最近进展</span><span>下一步</span></div>
        {filtered.map((candidate) => <div className="candidate-table-row" role="button" tabIndex={0} key={candidate.id} onClick={() => onOpen(candidate)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onOpen(candidate); }}><label onClick={(event) => event.stopPropagation()}><input type="checkbox" disabled={!transitions[candidate.stage]?.length} checked={selected.includes(candidate.id)} onChange={() => setSelected((current) => current.includes(candidate.id) ? current.filter((id) => id !== candidate.id) : [...current, candidate.id])} /></label><span className="candidate-name-cell"><span>{candidate.name.slice(-1)}</span><span><strong>{candidate.name}</strong><small>{candidate.role} · {candidate.company}</small></span></span><span><strong>{candidate.position}</strong><small>{candidate.city}</small></span><span><StageTag stage={candidate.stage} /></span><span className="candidate-score">{candidate.score}</span><span>{candidate.source}</span><span>{candidate.owner}</span><span><strong>{candidate.lastActivity}</strong><small>{candidate.recommendation}</small></span><span className="next-cell">{transitions[candidate.stage]?.[0] || "已结束"}<ChevronRight size={16} /></span></div>)}
        {filtered.length === 0 && <div className="candidate-empty"><Filter size={24} /><strong>没有符合条件的候选人</strong><span>调整或清空筛选条件后重试。</span></div>}
      </div>
    </section>
  </div>;
}

function TransitionDialog({ candidate, onClose, onCommit, onConflictRefresh, serverBacked = false, submitting = false, actionError = "", conflict = false }) {
  const options = candidateTransitionOptions(candidate.stage, serverBacked);
  const [target, setTarget] = useState(options[0] || "");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [fixtureConflict, setFixtureConflict] = useState(false);

  async function submit(force = false) {
    if (target === "已淘汰" && !reason.trim()) { setError("淘汰候选人必须填写原因"); return; }
    if (!serverBacked && candidate.version === 2 && !force) { setFixtureConflict(true); return; }
    await onCommit(target, reason);
  }

  return <div className="candidate-dialog-backdrop" role="presentation" onMouseDown={onClose}><section className="candidate-dialog" role="dialog" aria-modal="true" aria-label="推进候选人状态" onMouseDown={(event) => event.stopPropagation()}>
    <header><div><h3>推进候选人</h3><p>{candidate.name} · {candidate.position}</p></div><button className="icon-button" type="button" aria-label="关闭" onClick={onClose}><X size={19} /></button></header>
    {(conflict || fixtureConflict) ? <div className="conflict-state" role="alert"><CircleAlert size={23} /><h4>候选人状态已被其他成员更新</h4><p>{serverBacked ? "你的修改没有覆盖服务端记录。请加载最新详情并重新确认。" : "服务端最新状态为“待沟通”，负责人为张小北。你的修改尚未覆盖该更新。"}</p><div><button className="button secondary" type="button" onClick={() => onConflictRefresh(serverBacked ? undefined : "待沟通")}>{serverBacked ? "刷新最新详情" : "使用最新状态"}</button>{!serverBacked && <button className="button primary" type="button" onClick={() => submit(true)}>基于最新状态重新应用</button>}</div></div> : <>
      <div className="candidate-dialog-body"><div className="transition-current"><span>当前状态</span><StageTag stage={candidate.stage} /></div><label>下一状态<select value={target} disabled={submitting} onChange={(event) => { setTarget(event.target.value); setError(""); }}>{options.map((item) => <option key={item}>{item}</option>)}</select></label><label>操作原因{target === "已淘汰" && <span className="required-label">必填</span>}<textarea rows="4" value={reason} disabled={submitting} onChange={(event) => { setReason(event.target.value); setError(""); }} placeholder={target === "已淘汰" ? "请选择或填写淘汰原因" : "补充本次状态变更说明（选填）"} /></label><div className="transition-impact"><ShieldCheck size={16} /><span>提交后将写入候选人时间线，并保留规则、LLM 和人工结论。</span></div>{(error || actionError) && <p className="field-error" role="alert"><CircleAlert size={14} />{error || actionError}</p>}</div>
      <footer><button className="button secondary" type="button" disabled={submitting} onClick={onClose}>取消</button><button className="button primary" type="button" disabled={submitting || !target} onClick={() => void submit(false)}>{submitting ? "正在推进" : "确认推进"}</button></footer>
    </>}
  </section></div>;
}

function ResumePreview({ candidate, preview, loading, error, onClose, onRetry, onDownload }) {
  return <aside className="resume-preview-drawer" role="dialog" aria-modal="true" aria-label="简历预览">
    <header><div><FileText size={21} /><div><h2>简历预览</h2><p>{resumeDisplayName(candidate.resume)}</p></div></div><button className="icon-button" type="button" aria-label="关闭简历预览" onClick={onClose}><X size={19} /></button></header>
    <div className="resume-preview-body">
      {loading && <div className="candidate-detail-state" role="status"><LoaderCircle className="spin" size={24} /><strong>正在加载简历预览</strong></div>}
      {error && <div className="candidate-detail-state error" role="alert"><CircleAlert size={24} /><strong>{error}</strong><button className="button secondary" type="button" onClick={onRetry}><RotateCcw size={15} />重试预览</button></div>}
      {!loading && !error && <article className="resume-preview-page"><pre>{preview?.text || "服务端未返回可预览文本。"}</pre></article>}
    </div>
    <footer><button className="button secondary" type="button" onClick={onClose}>关闭</button><button className="button primary" type="button" onClick={onDownload}><Download size={15} />下载原文件</button></footer>
  </aside>;
}

function CandidateDetail({ candidate, onBack, onUpdate, onNotify, onScheduleInterview, onOpenInterviewFeedback, onAddToTalentPool, actorName, controller, onRefresh }) {
  const [tab, setTab] = useState("档案与简历");
  const [transitionOpen, setTransitionOpen] = useState(false);
  const [note, setNote] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [conclusion, setConclusion] = useState(candidate.humanConclusion || "");
  const [conclusionReason, setConclusionReason] = useState(candidate.humanConclusionReason || "");
  const [pendingAction, setPendingAction] = useState("");
  const [actionError, setActionError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [previewState, setPreviewState] = useState(null);

  useEffect(() => {
    setConclusion(candidate.humanConclusion || "");
    setConclusionReason(candidate.humanConclusionReason || "");
  }, [candidate.humanConclusion, candidate.humanConclusionReason, candidate.id]);

  function update(patch) { onUpdate({ ...candidate, ...patch }); }

  async function runServerAction(type, action, successMessage) {
    setPendingAction(type); setActionError(""); setConflict(false);
    try {
      await action();
      await onRefresh();
      onNotify(successMessage);
      return true;
    } catch (error) {
      setConflict(error?.status === 409);
      setActionError(candidateMutationError(error));
      return false;
    } finally {
      setPendingAction("");
    }
  }

  async function addNote() {
    if (!note.trim()) return;
    if (candidate.serverBacked) {
      const saved = await runServerAction("note", () => controller.addNote(candidate.id, candidate.application?.id, note), "备注已保存");
      if (saved) setNote("");
      return;
    }
    update({ notes: [...candidate.notes, note.trim()], timeline: [{ time: "刚刚", actor: actorName, action: `添加备注：${note.trim()}` }, ...candidate.timeline], lastActivity: "刚刚" });
    setNote(""); onNotify("备注已保存");
  }

  function addTag() {
    const value = tagInput.trim(); if (!value || candidate.tags.includes(value)) return;
    update({ tags: [...candidate.tags, value] }); setTagInput(""); onNotify("标签已添加");
  }

  async function commitTransition(target, reason) {
    if (candidate.serverBacked) {
      const saved = await runServerAction("transition", () => controller.transition(candidate.application, target, reason), `候选人已推进到${target}`);
      if (saved) setTransitionOpen(false);
      return;
    }
    update({ stage: target, version: candidate.version + 1, lastActivity: "刚刚", applications: candidate.applications.map((item, index) => index === 0 ? { ...item, state: target } : item), timeline: [{ time: "刚刚", actor: actorName, action: `${candidate.stage} → ${target}${reason ? `；原因：${reason}` : ""}` }, ...candidate.timeline] });
    setTransitionOpen(false); onNotify(`候选人已推进到${target}`);
  }

  async function saveConclusion() {
    if (!candidate.serverBacked) {
      update({ humanConclusion: conclusion, timeline: [{ time: "刚刚", actor: actorName, action: `更新人工结论：${conclusion}${conclusionReason ? `；${conclusionReason}` : ""}` }, ...candidate.timeline] });
      onNotify("人工结论已保存");
      return;
    }
    await runServerAction("conclusion", () => controller.saveConclusion(candidate.application, conclusion, conclusionReason), "人工结论已保存");
  }

  async function loadPreview() {
    if (!candidate.resume?.id) return;
    setPreviewState({ loading: true, error: "", data: null });
    try {
      const data = await controller.previewResume(candidate.resume.id);
      setPreviewState({ loading: false, error: "", data });
    } catch {
      setPreviewState({ loading: false, error: "简历预览加载失败，请重试。", data: null });
    }
  }

  async function downloadResume() {
    if (!candidate.serverBacked) { onNotify("简历下载已记录到审计日志"); return; }
    if (!candidate.resume?.id || pendingAction) return;
    setPendingAction("download"); setActionError("");
    try {
      const result = await controller.downloadResume(candidate.resume.id);
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = url; link.download = result.filename || resumeDisplayName(candidate.resume); link.hidden = true;
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
      onNotify("简历下载已开始");
    } catch {
      setActionError("简历下载失败，请稍后重试。");
    } finally {
      setPendingAction("");
    }
  }

  const next = (!candidate.serverBacked || candidate.application) ? candidateTransitionOptions(candidate.stage, candidate.serverBacked)[0] : null;
  const tabs = candidateDetailTabs(candidate.serverBacked);
  const notes = candidate.notes || [];
  const profileLine = [candidate.role, candidate.company, candidate.city].filter(Boolean).join(" · ");
  return <div className="candidate-page candidate-detail-page">
    <button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />{candidate.serverBacked ? "返回筛选任务" : "返回候选人列表"}</button>
    <section className="candidate-detail-hero"><div className="candidate-profile"><span>{candidate.name.slice(-1)}</span><div><div><h2>{candidate.name}</h2><StageTag stage={candidate.stage} /></div><p>{profileLine}</p><div className="masked-contacts"><span><Phone size={13} />{candidate.phone}</span><span><Mail size={13} />{candidate.email}</span></div></div></div><div className="candidate-detail-actions">{!candidate.serverBacked && <button className="button secondary" type="button" onClick={() => onNotify("联系方式已复制，操作已记录") }><ClipboardCopy size={16} />复制联系信息</button>}<button className="button secondary" type="button" disabled={candidate.serverBacked && (!candidate.resume?.id || pendingAction === "download")} onClick={() => void downloadResume()}><Download size={16} />{pendingAction === "download" ? "下载中" : "下载简历"}</button>{!candidate.serverBacked && onAddToTalentPool && <button className="button secondary" type="button" onClick={() => onAddToTalentPool([candidate.id])}><BriefcaseBusiness size={16} />加入人才库</button>}{next && <button className="button primary" type="button" onClick={() => { setActionError(""); setConflict(false); setTransitionOpen(true); }}><UserRoundCheck size={16} />推进候选人</button>}</div></section>
    {actionError && !transitionOpen && <div className="candidate-action-error" role="alert"><CircleAlert size={16} /><span>{actionError}</span>{conflict && <button type="button" onClick={() => void onRefresh()}>刷新最新详情</button>}</div>}
    <div className="candidate-detail-layout"><main className="candidate-detail-main"><section className="candidate-detail-panel"><div className="candidate-detail-tabs">{tabs.map((item) => <button type="button" key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}</div>
      {tab === "档案与简历" && <div className="candidate-tab-content profile-tab"><section><h3>候选人摘要</h3><p>{candidate.summary}</p></section><section><h3>技能</h3><div className="candidate-skill-tags">{candidate.skills.length ? candidate.skills.map((item) => <span key={item}>{item}</span>) : <span>暂无结构化技能</span>}</div></section><div className="profile-facts"><div><BriefcaseBusiness size={18} /><span><strong>工作经验</strong><small>{candidate.experience}</small></span></div><div><GraduationCap size={18} /><span><strong>教育经历</strong><small>{candidate.education}</small></span></div><div className="resume-detail-row"><FileText size={18} /><span><strong>当前简历</strong><small>{candidate.serverBacked ? resumeDisplayName(candidate.resume) : `${candidate.name}_简历.pdf · 解析质量良好`}</small>{candidate.serverBacked && candidate.resume?.id && <span className="resume-inline-actions"><button type="button" onClick={() => void loadPreview()}><Eye size={14} />预览</button><button type="button" onClick={() => void downloadResume()}><Download size={14} />下载</button></span>}</span></div></div></div>}
      {tab === "职位申请" && <div className="candidate-tab-content"><div className="applications-table"><div><span>职位</span><span>状态</span><span>{candidate.serverBacked ? "最近更新" : "申请日期"}</span><span>来源</span></div>{candidate.applications.map((item) => <div key={`${item.position}-${item.created}`}><strong>{item.position}</strong><StageTag stage={item.state} /><span>{item.created}</span><span>{item.source}</span></div>)}</div></div>}
      {tab === "筛选证据" && <div className="candidate-tab-content evidence-grid"><section className="rule-evidence"><header><FileText size={18} /><div><h3>规则评分</h3><span>{candidate.serverBacked ? "本次筛选结果" : "岗位规则 v3 · 今天 10:30"}</span></div><strong>{candidate.ruleScore ?? "—"}</strong></header><p>命中：{candidate.matched}</p><p>缺失：{candidate.missing}</p><p>风险：{candidate.risk}</p></section><section className="llm-evidence"><header><Sparkles size={18} /><div><h3>LLM 辅助评分</h3><span>{candidate.serverBacked ? "本次筛选结果" : "OpenAI 兼容接口 · 今天 10:30"}</span></div><strong>{candidate.llmScore ?? "—"}</strong></header><p>{candidate.llmReason}</p><small>此内容为 AI 辅助建议，不替代人工结论。</small></section><section className="human-evidence"><header><UserRoundCheck size={18} /><div><h3>人工结论</h3><span>由招聘团队维护</span></div></header><div className="conclusion-options">{["建议推进", "需要补充", "暂不合适"].map((item) => <button type="button" disabled={pendingAction === "conclusion" || (candidate.serverBacked && !candidate.application)} key={item} className={conclusion === item ? "active" : ""} onClick={() => setConclusion(item)}>{item}</button>)}</div><textarea rows="3" disabled={pendingAction === "conclusion" || (candidate.serverBacked && !candidate.application)} value={conclusionReason} onChange={(event) => setConclusionReason(event.target.value)} placeholder="补充人工判断依据" /><button className="button primary" type="button" disabled={!conclusion || pendingAction === "conclusion" || (candidate.serverBacked && !candidate.application)} onClick={() => void saveConclusion()}>{pendingAction === "conclusion" ? "保存中" : "保存人工结论"}</button></section></div>}
      {tab === "面试与反馈" && <div className="candidate-tab-content"><div className="candidate-interview-toolbar"><div><h3>面试记录</h3><span>安排、通知和反馈统一记录在候选人时间线中。</span></div>{onScheduleInterview && <button className="button primary" type="button" onClick={() => onScheduleInterview(candidate)}><CalendarDays size={16} />安排面试</button>}</div>{candidate.interviews.length ? <div className="interview-feedback-list">{candidate.interviews.map((item) => <section key={item.time}><header><div><strong>{item.round}</strong><span>{item.time}</span></div><span className="feedback-result">{item.result}</span></header><p>面试官：{item.interviewer}</p><blockquote>{item.feedback}</blockquote>{onOpenInterviewFeedback && item.interviewId && <button className="button secondary" type="button" onClick={() => onOpenInterviewFeedback(item.interviewId)}>查看面试详情</button>}</section>)}</div> : <div className="candidate-empty compact"><MessageSquareText size={23} /><strong>暂无面试记录</strong><span>可以直接为该候选人创建第一场面试。</span>{onScheduleInterview && <button className="button primary" type="button" onClick={() => onScheduleInterview(candidate)}><CalendarDays size={16} />安排面试</button>}</div>}</div>}
      {tab === "时间线" && <div className="candidate-tab-content candidate-timeline">{candidate.timeline.map((item, index) => <div key={`${item.time}-${index}`}><span /><div><strong>{item.action}</strong><p>{item.actor} · {item.time}</p></div></div>)}{candidate.timeline.length === 0 && <div className="candidate-muted">暂无可见时间线记录</div>}</div>}
    </section></main><aside className="candidate-context"><section><h3>当前申请</h3><dl><div><dt>应聘职位</dt><dd>{candidate.position}</dd></div><div><dt>当前状态</dt><dd><StageTag stage={candidate.stage} /></dd></div><div><dt>负责人</dt><dd>{candidate.owner}</dd></div><div><dt>下一步</dt><dd>{next || "流程已结束"}</dd></div><div><dt>最近进展</dt><dd>{candidate.lastActivity || "未记录"}</dd></div></dl>{next && <button className="button primary full" type="button" onClick={() => { setActionError(""); setConflict(false); setTransitionOpen(true); }}>推进到{next}</button>}</section>{!candidate.serverBacked && <section><h3>标签</h3><div className="context-tags">{candidate.tags.map((item) => <span key={item}>{item}</span>)}</div><div className="inline-add"><input value={tagInput} onChange={(event) => setTagInput(event.target.value)} placeholder="添加标签" /><button type="button" aria-label="添加标签" onClick={addTag}><Plus size={15} /></button></div></section>}<section><h3>招聘备注</h3>{notes.map((item, index) => <p className="saved-note" key={typeof item === "object" ? item.id : `${item}-${index}`}>{typeof item === "object" ? item.body : item}</p>)}{notes.length === 0 && <p className="candidate-muted">暂无招聘备注</p>}<textarea rows="4" disabled={pendingAction === "note"} value={note} onChange={(event) => setNote(event.target.value)} placeholder="记录沟通重点或后续事项" /><button className="button secondary full" type="button" disabled={!note.trim() || pendingAction === "note"} onClick={() => void addNote()}>{pendingAction === "note" ? "保存中" : "保存备注"}</button></section></aside></div>
    {transitionOpen && <TransitionDialog candidate={candidate} serverBacked={candidate.serverBacked} submitting={pendingAction === "transition"} actionError={actionError} conflict={conflict} onClose={() => setTransitionOpen(false)} onCommit={commitTransition} onConflictRefresh={(latestStage) => { if (candidate.serverBacked) { void onRefresh(); setTransitionOpen(false); return; } update({ stage: latestStage, version: 3, lastActivity: "刚刚", timeline: [{ time: "刚刚", actor: "系统", action: `检测到其他成员已将状态更新为${latestStage}` }, ...candidate.timeline] }); setTransitionOpen(false); onNotify("已刷新为服务端最新状态"); }} />}
    {previewState && <ResumePreview candidate={candidate} preview={previewState.data} loading={previewState.loading} error={previewState.error} onClose={() => setPreviewState(null)} onRetry={() => void loadPreview()} onDownload={() => void downloadResume()} />}
  </div>;
}

export function CandidatesWorkspace({ mode, setMode, selectedCandidate, setSelectedCandidate, records, setRecords, onNotify, onBackDetail, onScheduleInterview, onOpenInterviewFeedback, onAddToTalentPool, initialFilters, actorName = "张小北", controller, detailState, onRetryDetail }) {
  function updateCandidate(updated) { setRecords((current) => current.map((item) => item.id === updated.id ? updated : item)); setSelectedCandidate(updated); }
  if (mode === "detail" && detailState?.status === "loading") return <div className="candidate-page"><button className="back-link" type="button" onClick={onBackDetail}><ArrowLeft size={17} />返回筛选任务</button><div className="candidate-detail-state" role="status"><LoaderCircle className="spin" size={28} /><strong>正在加载候选人详情</strong><span>将从服务端读取候选人、申请、简历和时间线。</span></div></div>;
  if (mode === "detail" && detailState?.status === "error") return <div className="candidate-page"><button className="back-link" type="button" onClick={onBackDetail}><ArrowLeft size={17} />返回筛选任务</button><div className="candidate-detail-state error" role="alert"><CircleAlert size={28} /><strong>候选人详情加载失败</strong><span>{detailState.error}</span><button className="button primary" type="button" onClick={onRetryDetail}><RotateCcw size={16} />重试加载</button></div></div>;
  if (mode === "detail" && selectedCandidate) return <CandidateDetail candidate={selectedCandidate} onBack={onBackDetail || (() => { setSelectedCandidate(null); setMode("list"); })} onUpdate={updateCandidate} onNotify={onNotify} onScheduleInterview={onScheduleInterview} onOpenInterviewFeedback={onOpenInterviewFeedback} onAddToTalentPool={onAddToTalentPool} actorName={actorName} controller={controller} onRefresh={onRetryDetail} />;
  return <CandidateList records={records} onOpen={(candidate) => { setSelectedCandidate(candidate); setMode("detail"); }} onUpdate={setRecords} onNotify={onNotify} onAddToTalentPool={onAddToTalentPool} initialFilters={initialFilters} />;
}
