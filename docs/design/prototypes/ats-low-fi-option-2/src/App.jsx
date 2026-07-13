import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  BriefcaseBusiness,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  FileText,
  Filter,
  Home,
  Import,
  LayoutList,
  LogOut,
  Menu,
  MoreHorizontal,
  Plus,
  Settings,
  SlidersHorizontal,
  Users,
  UserRound,
  UserRoundSearch,
  X,
} from "lucide-react";
import { initialPositionRecords, JobsWorkspace } from "./JobViews.jsx";
import { ImportWizard, ScreeningTaskView } from "./ScreeningViews.jsx";
import { CandidatesWorkspace, initialCandidateRecords } from "./CandidateViews.jsx";
import { initialInterviewRecords, InterviewsWorkspace } from "./InterviewViews.jsx";
import { initialTalentMemberships, initialTalentPools, TalentPoolWorkspace } from "./TalentPoolViews.jsx";
import { ReportWorkspace } from "./ReportViews.jsx";
import { SettingsWorkspace } from "./SettingsViews.jsx";
import { syntheticResumeFilesFor } from "./syntheticResumeFixtures.js";
import { canPerformAction, getAllowedNavItems, getDefaultNavItem } from "./roleCapabilities.js";
import { addTalentMemberships, applyScreeningResults, reactivateTalentCandidate, recalculatePositionCounts, saveInterview, submitInterviewFeedback, validateWorkflowState } from "./ux08Workflow.js";
import { AccessDeniedView, LoginView, SessionLoadingView } from "./LoginView.jsx";
import { getSessionIdentity, getSessionMessage, sessionController } from "./session.js";
import { screeningController as defaultScreeningController } from "./screeningController.js";
import { getRecentScreeningTaskStorageKey, LEGACY_RECENT_SCREENING_TASK_STORAGE_KEY, parseRecentScreeningTask, serializeRecentScreeningTask } from "./screeningIntegration.js";

const navItems = [
  ["工作台", Home],
  ["职位", BriefcaseBusiness],
  ["候选人", Users],
  ["面试", CalendarDays],
  ["人才库", UserRoundSearch],
  ["报表", LayoutList],
  ["设置", Settings],
];

const stageMeta = [
  ["新简历", 22],
  ["待复核", 8],
  ["待沟通", 6],
  ["待安排", 4],
  ["面试中", 5],
  ["待决策", 3],
];

const emptyStages = stageMeta.map(() => []);

const jobData = {
  "AI 工程师": {
    count: 12,
    stages: [
      [
        { name: "候 A1", role: "AI 算法工程师", company: "字节", age: "3 小时前", tag: "来自 智联" },
        { name: "候 A2", role: "算法工程师", company: "百度", age: "5 小时前", tag: "来自 拉勾" },
        { name: "候 A3", role: "深度学习工程师", company: "商汤", age: "1 天前", tag: "来自 猎聘" },
        { name: "候 A4", role: "NLP 算法工程师", company: "科大讯飞", age: "1 天前", tag: "来自 内推" },
        { name: "候 A5", role: "算法工程师", company: "快手", age: "2 天前", tag: "来自 BOSS 直聘" },
      ],
      [
        { name: "候 B1", role: "算法工程师", company: "腾讯", age: "1 天前", tag: "来自 猎聘" },
        { name: "候 B2", role: "AI 研究员", company: "阿里", age: "2 天前", tag: "来自 拉勾" },
        { name: "候 B3", role: "计算机视觉工程师", company: "美团", age: "2 天前", tag: "来自 内推" },
        { name: "候 B4", role: "算法工程师", company: "字节", age: "3 天前", tag: "来自 猎聘" },
        { name: "候 B5", role: "NLP 算法工程师", company: "百度", age: "3 天前", tag: "来自 智联" },
      ],
      [
        { name: "候 C1", role: "算法工程师", company: "字节", age: "今天", schedule: "今日 15:00" },
        { name: "候 C2", role: "AI 工程师", company: "腾讯", age: "昨天", schedule: "今日 16:30" },
        { name: "候 C3", role: "算法工程师", company: "美团", age: "2 天前", schedule: "明日 10:00" },
        { name: "候 C4", role: "深度学习工程师", company: "商汤", age: "2 天前", schedule: "明日 14:00" },
        { name: "候 C5", role: "NLP 算法工程师", company: "百度", age: "3 天前", schedule: "07-13 10:00" },
      ],
      [
        { name: "候 D1", role: "算法工程师", company: "快手", age: "昨天", tag: "待安排面试" },
        { name: "候 D2", role: "AI 工程师", company: "阿里", age: "2 天前", tag: "待安排面试" },
        { name: "候 D3", role: "计算机视觉工程师", company: "字节", age: "2 天前", tag: "待安排面试" },
        { name: "候 D4", role: "算法工程师", company: "小米", age: "3 天前", tag: "待安排面试" },
      ],
      [
        { name: "候 E1", role: "一面 · 进行中", company: "", age: "", schedule: "今天 10:00", interviewer: "面试官：李明" },
        { name: "候 E2", role: "二面 · 进行中", company: "", age: "", schedule: "今天 14:00", interviewer: "面试官：王磊" },
        { name: "候 E3", role: "三面 · 进行中", company: "", age: "", schedule: "07-12 10:00", interviewer: "面试官：张敏" },
        { name: "候 E4", role: "一面 · 已安排", company: "", age: "", schedule: "07-13 15:00", interviewer: "面试官：赵强" },
        { name: "候 E5", role: "一面 · 已安排", company: "", age: "", schedule: "07-13 16:30", interviewer: "面试官：李明" },
      ],
      [
        { name: "候 F1", role: "HR 评估中", company: "", age: "", note: "预计 07-13 前完成" },
        { name: "候 F2", role: "用人经理评估中", company: "", age: "", note: "预计 07-14 前完成" },
        { name: "候 F3", role: "HR 评估中", company: "", age: "", note: "预计 07-15 前完成" },
      ],
    ],
  },
  "Java 后端工程师": { count: 8 },
  产品经理: { count: 6 },
};

function IconButton({ label, children, className = "", onClick, disabled = false }) {
  return (
    <button className={`icon-button ${className}`} type="button" title={label} aria-label={label} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

function CandidateCard({ candidate, onOpen }) {
  return (
    <button className="candidate-card" type="button" onClick={() => onOpen(candidate)}>
      <div className="candidate-line">
        <span className="avatar-mini"><UserRound size={11} /></span>
        <strong>{candidate.name}</strong>
        <span className="age">{candidate.age}</span>
      </div>
      <div className="candidate-role">{candidate.role}{candidate.company ? ` · ${candidate.company}` : ""}</div>
      {candidate.schedule && <div className="meta-line"><CalendarDays size={13} />{candidate.schedule}</div>}
      {candidate.interviewer && <div className="meta-line"><FileText size={13} />{candidate.interviewer}</div>}
      {candidate.note && <div className="candidate-note">{candidate.note}</div>}
      {candidate.tag && <span className="source-tag">{candidate.tag}</span>}
    </button>
  );
}

function Modal({ title, children, onClose, footer }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header className="modal-header">
          <h2>{title}</h2>
          <IconButton label="关闭" onClick={onClose}><X size={20} /></IconButton>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </section>
    </div>
  );
}

export function App({ controller = sessionController, screeningController = defaultScreeningController }) {
  const session = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);

  useEffect(() => {
    void controller.bootstrap();
  }, [controller]);

  if (session.status === "bootstrapping") return <SessionLoadingView />;
  if (session.status === "anonymous") {
    return <LoginView error={session.error} submitting={session.submitting} onLogin={(credentials) => controller.login(credentials)} />;
  }
  if (session.status !== "authenticated") {
    const identity = getSessionIdentity(session.user, null);
    return <AccessDeniedView displayName={identity.name} error={session.error} loggingOut={session.loggingOut} onLogout={() => controller.logout()} />;
  }
  return <AuthenticatedApp session={session} onLogout={() => controller.logout()} screeningController={screeningController} />;
}

function AuthenticatedApp({ session, onLogout, screeningController }) {
  const currentRole = session.role || "未知角色";
  const recentTaskStorageKey = getRecentScreeningTaskStorageKey(session.user);
  const [activeNav, setActiveNav] = useState(() => getDefaultNavItem(currentRole) || "设置");
  const [activeJob, setActiveJob] = useState("AI 工程师");
  const [menuOpen, setMenuOpen] = useState(false);
  const [view, setView] = useState("board");
  const [modal, setModal] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [toast, setToast] = useState("");
  const [filterOnlyUrgent, setFilterOnlyUrgent] = useState(false);
  const [jobs, setJobs] = useState(Object.keys(jobData));
  const [jobMode, setJobMode] = useState("list");
  const [selectedJob, setSelectedJob] = useState(null);
  const [positionRecords, setPositionRecords] = useState(() => recalculatePositionCounts(initialPositionRecords, initialCandidateRecords));
  const [candidateMode, setCandidateMode] = useState("list");
  const [candidateRecords, setCandidateRecords] = useState(initialCandidateRecords);
  const [candidateOrigin, setCandidateOrigin] = useState(null);
  const [candidatePreset, setCandidatePreset] = useState(null);
  const [currentScenario, setCurrentScenario] = useState("default");
  const [interviewMode, setInterviewMode] = useState("list");
  const [interviewRecords, setInterviewRecords] = useState(initialInterviewRecords);
  const [selectedInterview, setSelectedInterview] = useState(null);
  const [scheduleCandidateId, setScheduleCandidateId] = useState(null);
  const [interviewOrigin, setInterviewOrigin] = useState(null);
  const [talentMode, setTalentMode] = useState("list");
  const [talentPools, setTalentPools] = useState(initialTalentPools);
  const [talentMemberships, setTalentMemberships] = useState(initialTalentMemberships);
  const [selectedPoolId, setSelectedPoolId] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [screeningTask, setScreeningTask] = useState(null);
  const [recentTask, setRecentTask] = useState(() => {
    return recentTaskStorageKey ? parseRecentScreeningTask(window.localStorage.getItem(recentTaskStorageKey)) : null;
  });

  const stages = useMemo(() => stageMeta.map(([stage]) => candidateRecords.filter((candidate) => candidate.position === activeJob && candidate.stage === stage).map((candidate) => {
    const latestInterview = candidate.interviews?.at(-1);
    return { name: candidate.name, role: candidate.role, company: candidate.company, age: candidate.lastActivity, tag: candidate.stage === "待安排" ? "待安排面试" : `来自 ${candidate.source}`, schedule: latestInterview?.time, interviewer: latestInterview?.interviewer ? `面试官：${latestInterview.interviewer}` : null, note: candidate.stage === "待决策" ? "等待 HR 决策" : null };
  })), [activeJob, candidateRecords]);
  const visibleStageMeta = stageMeta.map(([name], index) => [name, stages[index].length]);
  const pendingScheduleCandidates = useMemo(() => candidateRecords.filter((candidate) => candidate.stage === "待安排"), [candidateRecords]);
  const pendingFeedbackInterviews = useMemo(() => interviewRecords.filter((interview) => interview.feedbackStatus === "待反馈"), [interviewRecords]);
  const upcomingInterviewDays = useMemo(() => {
    const labels = new Map();
    interviewRecords
      .filter((interview) => interview.date >= "2026-07-11" && interview.status !== "已取消")
      .forEach((interview) => {
        const label = interview.dateLabel || interview.date;
        labels.set(label, (labels.get(label) || 0) + 1);
      });
    return [...labels.entries()].sort(([left], [right]) => left.localeCompare(right)).slice(0, 4);
  }, [interviewRecords]);
  const duplicateCandidateGroups = useMemo(() => {
    const identityCounts = new Map();
    candidateRecords.forEach((candidate) => {
      const identity = candidate.email || candidate.phone || candidate.name;
      identityCounts.set(identity, (identityCounts.get(identity) || 0) + 1);
    });
    return [...identityCounts.values()].filter((count) => count > 1).length;
  }, [candidateRecords]);
  const allowedNavItems = useMemo(() => new Set(getAllowedNavItems(currentRole)), [currentRole]);
  const roleIdentity = getSessionIdentity(session.user, currentRole);
  const sessionMessage = getSessionMessage(session.error);
  const myPendingFeedbackInterviews = pendingFeedbackInterviews.filter((item) => item.interviewers.includes(roleIdentity.name));
  const screeningSummary = useMemo(() => {
    if (!recentTask?.files?.length) return null;
    return {
      total: recentTask.files.length,
      success: recentTask.files.filter((file) => file.status === "success").length,
      partial: recentTask.files.filter((file) => file.status === "partial").length,
      failed: recentTask.files.filter((file) => file.status === "failed").length,
    };
  }, [recentTask]);
  const workflowValidation = useMemo(() => validateWorkflowState({ positions: positionRecords, candidates: candidateRecords, interviews: interviewRecords, pools: talentPools, memberships: talentMemberships }), [candidateRecords, interviewRecords, positionRecords, talentMemberships, talentPools]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [activeNav, jobMode, candidateMode, interviewMode, talentMode, Boolean(screeningTask)]);

  useEffect(() => {
    window.localStorage.removeItem(LEGACY_RECENT_SCREENING_TASK_STORAGE_KEY);
    setRecentTask(recentTaskStorageKey ? parseRecentScreeningTask(window.localStorage.getItem(recentTaskStorageKey)) : null);
  }, [recentTaskStorageKey]);

  function notify(message) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  }

  function drillDownReport({ position, stage }) {
    setCandidatePreset({ position: position === "全部职位" ? "全部职位" : position, stage });
    setSelectedCandidate(null);
    setCandidateMode("list");
    setActiveNav("候选人");
  }

  const persistRecentServerTask = useCallback((task) => {
    setRecentTask(task);
    const serialized = serializeRecentScreeningTask(task);
    if (recentTaskStorageKey && serialized) window.localStorage.setItem(recentTaskStorageKey, serialized);
  }, [recentTaskStorageKey]);

  const handleTaskChange = useCallback((task) => {
    setScreeningTask(task);
    if (task?.serverBacked) {
      persistRecentServerTask(task);
    } else {
      setRecentTask(task);
      if (recentTaskStorageKey) window.localStorage.removeItem(recentTaskStorageKey);
    }
  }, [persistRecentServerTask, recentTaskStorageKey]);

  const updateCandidateRecords = useCallback((update) => {
    setCandidateRecords((current) => {
      const next = typeof update === "function" ? update(current) : update;
      setPositionRecords((positions) => recalculatePositionCounts(positions, next));
      return next;
    });
  }, []);

  function workflowState() {
    return { positions: positionRecords, candidates: candidateRecords, interviews: interviewRecords, pools: talentPools, memberships: talentMemberships };
  }

  function applyWorkflowState(next) {
    setPositionRecords(next.positions);
    setCandidateRecords(next.candidates);
    setInterviewRecords(next.interviews);
    setTalentPools(next.pools);
    setTalentMemberships(next.memberships);
  }

  function applyScreeningAction({ action, files, task }) {
    const previous = workflowState();
    const targetStage = action === "标记淘汰" ? "已淘汰" : "待复核";
    let next = applyScreeningResults(previous, { task, files, targetStage });
    const candidateIds = files.map((file) => next.candidates.find((candidate) => file.email ? candidate.email === file.email : candidate.name === file.candidate)?.id).filter(Boolean);
    if (action === "加入人才库") next = addTalentMemberships(next, { candidateIds, poolId: "POOL-FOLLOW", actor: roleIdentity.name });
    if (action === "添加标签") next.candidates = next.candidates.map((candidate) => candidateIds.includes(candidate.id) && !candidate.tags.includes("批量复核") ? { ...candidate, tags: [...candidate.tags, "批量复核"] } : candidate);
    applyWorkflowState(next);
    return { previousState: previous, affectedCount: new Set(candidateIds).size };
  }

  function resetScenario(scenario) {
    const baseCandidates = structuredClone(initialCandidateRecords);
    const basePositions = recalculatePositionCounts(structuredClone(initialPositionRecords), baseCandidates);
    const baseInterviews = structuredClone(initialInterviewRecords);
    const basePools = structuredClone(initialTalentPools);
    const baseMemberships = structuredClone(initialTalentMemberships);
    setCandidateRecords(baseCandidates);
    setPositionRecords(basePositions);
    setInterviewRecords(baseInterviews);
    setTalentPools(basePools);
    setTalentMemberships(baseMemberships);
    setActiveNav("工作台");
    setActiveJob("AI 工程师");
    setScreeningTask(null);
    setRecentTask(null);
    setSelectedCandidate(null);
    setCandidateMode("list");
    setSelectedInterview(null);
    setInterviewMode("list");
    setScheduleCandidateId(null);
    setSelectedPoolId(null);
    setTalentMode("list");
    setSelectedJob(null);
    setJobMode("list");
    setImportOpen(false);
    if (recentTaskStorageKey) window.localStorage.removeItem(recentTaskStorageKey);

    if (scenario === "new-position") {
      setActiveNav("职位");
      setSelectedJob(basePositions.find((position) => position.name === "AI 工程师"));
      setJobMode("detail");
    }
    if (scenario === "partial-screening") {
      const files = syntheticResumeFilesFor("AI 工程师").map((file) => ({ ...file, status: file.expectedParseStatus === "failed" ? "failed" : file.expectedLlmStatus === "failed" ? "partial" : "success", traceId: file.expectedParseStatus === "failed" ? "TR-PARSE-4081" : file.expectedLlmStatus === "failed" ? "TR-LLM-4297" : null, error: file.expectedParseStatus === "failed" ? "PDF 文本层损坏，未能提取有效内容" : file.expectedLlmStatus === "failed" ? "LLM 请求额度暂时不可用，已保留规则评分" : null }));
      const task = { id: "SCR-UX08-PARTIAL", position: "AI 工程师", source: "UX-08 合成数据", note: "部分失败恢复验收", llmEnabled: true, creator: "张小北", createdAt: "刚刚", status: "partial", stage: "已完成", completed: files.length, elapsed: 56, files, serverBacked: false };
      setScreeningTask(task);
      setRecentTask(task);
    }
    if (scenario === "pending-feedback") {
      setActiveNav("面试");
      setSelectedInterview(baseInterviews.find((interview) => interview.id === "INT-002"));
      setInterviewMode("feedback");
    }
    if (scenario === "talent-reactivation") {
      setActiveNav("人才库");
      setSelectedPoolId("POOL-FOLLOW");
      setTalentMode("detail");
    }
    if (scenario === "empty") {
      setCandidateRecords([]);
      setPositionRecords(recalculatePositionCounts(basePositions, []));
      setInterviewRecords([]);
      setTalentMemberships([]);
      setTalentPools(basePools.map((pool) => ({ ...pool, memberIds: [] })));
      setActiveNav("候选人");
    }
    if (scenario === "restricted") {
      setActiveNav("报表");
    }
    setCurrentScenario(scenario);
    notify(`已切换到“${scenario}”验收场景`);
  }

  function openJobForm() {
    setActiveNav("职位");
    setSelectedJob(null);
    setJobMode("form");
  }

  function registerJob(record) {
    setJobs((current) => current.includes(record.name) ? current : [...current, record.name]);
    setActiveJob(record.name);
  }

  function openCandidate(summary) {
    let candidate = candidateRecords.find((item) => (summary.fileId && item.sourceFileId === summary.fileId) || (summary.email && item.email === summary.email))
      || candidateRecords.find((item) => item.name === summary.name);
    if (!candidate) {
      notify("请先将该结果推进到候选人，再查看完整档案");
      return;
    }
    setCandidateOrigin(activeNav === "候选人" && !screeningTask ? null : { activeNav, screeningTask });
    setScreeningTask(null);
    setActiveNav("候选人");
    setSelectedCandidate(candidate);
    setCandidateMode("detail");
  }

  function backFromCandidateDetail() {
    if (candidateOrigin) {
      setActiveNav(candidateOrigin.activeNav);
      setScreeningTask(candidateOrigin.screeningTask);
      setCandidateOrigin(null);
    }
    setSelectedCandidate(null);
    setCandidateMode("list");
  }

  function openInterviewList() {
    setScreeningTask(null);
    setActiveNav("面试");
    setInterviewMode("list");
    setSelectedInterview(null);
    setScheduleCandidateId(null);
    setInterviewOrigin(null);
  }

  function openScheduleInterview(candidate = null, interview = null) {
    setInterviewOrigin(activeNav === "面试" ? null : { activeNav, candidateMode, selectedCandidate, screeningTask });
    setScreeningTask(null);
    setActiveNav("面试");
    setInterviewMode("schedule");
    setSelectedInterview(interview);
    setScheduleCandidateId(candidate?.id || null);
  }

  function openFeedbackInterview(interviewOrId) {
    const interview = typeof interviewOrId === "string" ? interviewRecords.find((item) => item.id === interviewOrId) : interviewOrId;
    if (!interview) { notify("未找到对应面试记录"); return; }
    setInterviewOrigin(activeNav === "面试" ? null : { activeNav, candidateMode, selectedCandidate, screeningTask });
    setScreeningTask(null);
    setActiveNav("面试");
    setInterviewMode("feedback");
    setSelectedInterview(interview);
    setScheduleCandidateId(null);
  }

  function backFromInterview() {
    if (!interviewOrigin) return;
    setActiveNav(interviewOrigin.activeNav);
    setCandidateMode(interviewOrigin.candidateMode);
    setSelectedCandidate(interviewOrigin.selectedCandidate);
    setScreeningTask(interviewOrigin.screeningTask);
    setInterviewOrigin(null);
  }

  function syncInterviewToCandidate(interview) {
    const next = interview.feedbackStatus === "已提交" && interview.feedback
      ? submitInterviewFeedback(workflowState(), interview.id, interview.feedback)
      : saveInterview(workflowState(), interview);
    applyWorkflowState(next);
    if (selectedCandidate?.id === interview.candidateId) setSelectedCandidate(next.candidates.find((candidate) => candidate.id === interview.candidateId));
  }

  function addCandidatesToTalentPool(candidateIds, poolId = "POOL-FOLLOW") {
    const pool = talentPools.find((item) => item.id === poolId) || talentPools[0];
    const before = talentMemberships.length;
    const next = addTalentMemberships(workflowState(), { candidateIds, poolId: pool.id, actor: roleIdentity.name });
    const additions = next.memberships.length - before;
    if (!additions) { notify(`候选人已在“${pool.name}”中`); return; }
    applyWorkflowState(next);
    notify(`已将 ${additions} 位候选人加入“${pool.name}”`);
  }

  function reactivateTalent(candidateId, position, poolId, resumeVersion) {
    const result = reactivateTalentCandidate(workflowState(), { candidateId, position, poolId, resumeVersion, actor: roleIdentity.name });
    if (!result.created) return null;
    applyWorkflowState(result.state);
    return result.application;
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand">招聘协同平台</div>
        <nav aria-label="主导航">
          {navItems.filter(([label]) => allowedNavItems.has(label)).map(([label, Icon]) => (
            <button
              key={label}
              type="button"
              className={activeNav === label ? "nav-item active" : "nav-item"}
              onClick={() => {
                setActiveNav(label);
                setMenuOpen(false);
                setScreeningTask(null);
                setCandidateOrigin(null);
                setSelectedCandidate(null);
                setInterviewOrigin(null);
                setScheduleCandidateId(null);
                setSelectedPoolId(null);
                if (label === "职位") {
                  setSelectedJob(null);
                  setJobMode("list");
                } else if (label === "候选人") {
                  setCandidateMode("list");
                  setCandidatePreset(null);
                } else if (label === "面试") {
                  setInterviewMode("list");
                  setSelectedInterview(null);
                } else if (label === "人才库") {
                  setTalentMode("list");
                } else if (!['工作台', '报表', '设置'].includes(label)) {
                  notify(`${label}模块将在后续原型中展开`);
                }
              }}
            >
              <Icon size={19} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="profile">
          <span className="profile-avatar"><UserRound size={20} /></span>
          <div><strong>{roleIdentity.name}</strong><span>{roleIdentity.title}</span></div>
          <ChevronDown size={17} />
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <IconButton label="打开菜单" className="mobile-menu" onClick={() => setMenuOpen((value) => !value)}><Menu size={21} /></IconButton>
          <h1>{screeningTask ? "筛选任务" : activeNav === "职位" ? (jobMode === "detail" ? "职位详情" : jobMode === "form" ? (selectedJob ? "编辑职位" : "新建职位") : "职位") : activeNav === "候选人" && candidateMode === "detail" ? "候选人详情" : activeNav === "面试" && interviewMode === "schedule" ? (selectedInterview ? "改期面试" : "安排面试") : activeNav === "面试" && interviewMode === "feedback" ? "面试反馈" : activeNav === "人才库" && talentMode === "detail" ? "人才库详情" : activeNav}</h1>
          <div className="top-actions">
            {!screeningTask && activeNav === "工作台" && canPerformAction(currentRole, "导入简历") && <button className="button primary" type="button" onClick={() => setImportOpen(true)}><Import size={17} />导入简历</button>}
            {!screeningTask && (activeNav === "工作台" || (activeNav === "职位" && jobMode === "list")) && canPerformAction(currentRole, "新建职位") && <button className={activeNav === "职位" ? "button primary" : "button secondary"} type="button" onClick={openJobForm}><Plus size={17} />新建职位</button>}
            <IconButton label={session.loggingOut ? "正在退出" : "退出登录"} className="logout-action" disabled={session.loggingOut} onClick={() => { void onLogout().catch(() => {}); }}><LogOut size={18} /></IconButton>
          </div>
        </header>

        {!screeningTask && activeNav === "工作台" && currentRole === "面试官" && <div className="interviewer-workbench">
          <header><div><h2>我的面试工作台</h2><p>仅展示你参与的面试和待提交反馈。</p></div><span>{myPendingFeedbackInterviews.length} 项待反馈</span></header>
          <section><h3>待提交反馈</h3>{myPendingFeedbackInterviews.map((interview) => <button type="button" key={interview.id} onClick={() => openFeedbackInterview(interview)}><span><strong>{interview.candidate}</strong><small>{interview.position} · {interview.round}</small></span><span>{interview.dateLabel} {interview.time}<ChevronRight size={16} /></span></button>)}{myPendingFeedbackInterviews.length === 0 && <p>暂无待提交反馈</p>}</section>
          <section><h3>我的面试</h3>{interviewRecords.filter((item) => item.interviewers.includes(roleIdentity.name) && item.feedbackStatus !== "待反馈").slice(0, 6).map((interview) => <button type="button" key={interview.id} onClick={() => openFeedbackInterview(interview)}><span><strong>{interview.candidate}</strong><small>{interview.position} · {interview.round}</small></span><span>{interview.dateLabel} {interview.time}<ChevronRight size={16} /></span></button>)}</section>
        </div>}

        {!screeningTask && activeNav === "工作台" && currentRole !== "面试官" && <div className="page-body">
          <section className="main-column">
            <div className="job-switcher">
              <span className="switcher-label">当前职位</span>
              <div className="job-tabs">
                {jobs.slice(0, 3).map((job) => (
                  <button key={job} type="button" className={activeJob === job ? "job-tab selected" : "job-tab"} onClick={() => setActiveJob(job)}>
                    <strong>{job}</strong><span>{candidateRecords.filter((candidate) => candidate.position === job && !["已录用", "已淘汰", "已撤回"].includes(candidate.stage)).length} 人进行中</span>
                  </button>
                ))}
                <button className="more-jobs" type="button" onClick={() => notify("已展示全部在招职位")}>更多职位<ChevronDown size={15} /></button>
              </div>
            </div>

            <section className="pipeline-panel">
              <header className="pipeline-header">
                <div><h2>{activeJob}</h2><span>全职 · 北京 · 技术部</span></div>
                <div className="pipeline-tools">
                  <button type="button" className={filterOnlyUrgent ? "text-tool active" : "text-tool"} onClick={() => setFilterOnlyUrgent((value) => !value)}><Filter size={15} />筛选</button>
                  <button type="button" className="text-tool" onClick={() => setView((value) => value === "board" ? "list" : "board")}><LayoutList size={16} />{view === "board" ? "视图" : "看板"}</button>
                  <IconButton label="更多操作" onClick={() => notify("已打开职位操作菜单")}><MoreHorizontal size={19} /></IconButton>
                </div>
              </header>

              {view === "board" ? (
                <div className="kanban" aria-label="候选人招聘阶段">
                  {visibleStageMeta.map(([name, count], index) => (
                    <section className="stage" key={name}>
                      <header><strong>{name}</strong><span>{filterOnlyUrgent ? Math.min(count, 3) : count}</span></header>
                      <div className="stage-list">
                        {stages[index].slice(0, filterOnlyUrgent ? 2 : 5).map((candidate) => (
                          <CandidateCard key={candidate.name} candidate={candidate} onOpen={openCandidate} />
                        ))}
                      </div>
                      <button className="load-more" type="button" onClick={() => notify(`${name}已加载更多候选人`)}><Plus size={14} />加载更多 ({Math.max(0, count - stages[index].length)})</button>
                    </section>
                  ))}
                </div>
              ) : (
                <div className="list-view">
                  <div className="list-head"><span>候选人</span><span>当前阶段</span><span>最近进展</span><span>操作</span></div>
                  {stages.flat().slice(0, 10).map((candidate, index) => (
                    <button type="button" className="list-row" key={candidate.name} onClick={() => openCandidate(candidate)}>
                      <span><span className="avatar-mini"><UserRound size={11} /></span><strong>{candidate.name}</strong></span>
                      <span>{visibleStageMeta.find((_, stageIndex) => stages[stageIndex].includes(candidate))?.[0]}</span>
                      <span>{candidate.age || candidate.schedule || candidate.note}</span>
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </div>
              )}

              {duplicateCandidateGroups > 0 && <div className="duplicate-alert">
                <CircleAlert size={19} />
                <div><strong>发现重复候选人</strong><span>系统检测到 {duplicateCandidateGroups} 组重复候选人，建议合并以避免重复跟进。</span></div>
                <button className="button small secondary" type="button" onClick={() => setModal("duplicates")}>去处理（{duplicateCandidateGroups}）</button>
                <IconButton label="忽略提醒" onClick={() => notify("本次提醒已忽略")}><X size={17} /></IconButton>
              </div>}
            </section>
            <footer className="updated">更新时间：2026-07-11 11:05 <button type="button" onClick={() => notify("数据已刷新")}>刷新</button></footer>
          </section>

          <aside className="right-rail">
            <section className="rail-section">
              <header><h3>待处理事项</h3><IconButton label="更多"><MoreHorizontal size={18} /></IconButton></header>
              <div className="rail-group">
                <div className="rail-group-title"><span className="status-dot red" />超期沟通（6）<button type="button" onClick={() => setFilterOnlyUrgent(true)}>查看全部</button></div>
                {["候 C3  已超期 1 天", "候 C4  已超期 1 天", "候 C5  已超期 1 天"].map((item) => <button className="rail-item" type="button" key={item} onClick={() => notify("已定位到对应候选人")}>{item}<small>算法工程师 · 北京</small></button>)}
                <button className="expand-link" type="button">展开 3 项<ChevronDown size={14} /></button>
              </div>
              <div className="rail-group">
                <div className="rail-group-title"><span className="status-dot orange" />待安排面试（{pendingScheduleCandidates.length}）<button type="button" onClick={openInterviewList}>查看全部</button></div>
                {pendingScheduleCandidates.slice(0, 3).map((candidate) => <button className="rail-item" type="button" key={candidate.id} onClick={() => openScheduleInterview(candidate)}>{candidate.name}　等待安排<small>{candidate.position} · {candidate.city}</small></button>)}
                {pendingScheduleCandidates.length === 0 && <p>暂无待安排面试</p>}
              </div>
              <div className="rail-group compact">
                <div className="rail-group-title"><span className="status-dot blue" />待反馈面试（{pendingFeedbackInterviews.length}）<button type="button" onClick={openInterviewList}>查看全部</button></div>
                {pendingFeedbackInterviews.slice(0, 3).map((interview) => <button className="rail-item" type="button" key={interview.id} onClick={() => openFeedbackInterview(interview)}>{interview.candidate}　{interview.dateLabel} {interview.round}</button>)}
                {pendingFeedbackInterviews.length === 0 && <p>暂无待提交反馈</p>}
              </div>
            </section>

            <section className="rail-section calendar-card">
              <header><h3>面试日历（未来 7 天）</h3><button type="button" onClick={openInterviewList}>查看日历</button></header>
              {upcomingInterviewDays.map(([day, count]) => <button type="button" className="calendar-row" key={day} onClick={openInterviewList}><span>{day}</span><strong>{count} 场</strong></button>)}
              {upcomingInterviewDays.length === 0 && <div className="calendar-empty-slot">未来 7 天暂无面试</div>}
              <button className="more-calendar" type="button">更多<MoreHorizontal size={15} /></button>
            </section>
          </aside>
        </div>}

        {!screeningTask && activeNav === "职位" && (
          <JobsWorkspace
            mode={jobMode}
            setMode={setJobMode}
            selectedJob={selectedJob}
            setSelectedJob={setSelectedJob}
            records={positionRecords}
            setRecords={setPositionRecords}
            onNotify={notify}
            onImport={() => { setActiveJob(selectedJob?.name || activeJob); setImportOpen(true); }}
            onOpenCandidate={openCandidate}
            onCreateJob={registerJob}
          />
        )}

        {!screeningTask && activeNav === "候选人" && (
          <CandidatesWorkspace mode={candidateMode} setMode={setCandidateMode} selectedCandidate={selectedCandidate} setSelectedCandidate={setSelectedCandidate} records={candidateRecords} setRecords={updateCandidateRecords} onNotify={notify} onBackDetail={backFromCandidateDetail} onScheduleInterview={(candidate) => openScheduleInterview(candidate)} onOpenInterviewFeedback={openFeedbackInterview} onAddToTalentPool={addCandidatesToTalentPool} initialFilters={candidatePreset} actorName={roleIdentity.name} />
        )}

        {!screeningTask && activeNav === "面试" && (
          <InterviewsWorkspace mode={interviewMode} setMode={setInterviewMode} selectedInterview={selectedInterview} setSelectedInterview={setSelectedInterview} scheduleCandidateId={scheduleCandidateId} records={interviewRecords} setRecords={setInterviewRecords} candidates={candidateRecords} onNotify={notify} onBack={backFromInterview} onRecordSaved={syncInterviewToCandidate} canSchedule={canPerformAction(currentRole, "安排面试")} actorName={roleIdentity.name} />
        )}

        {!screeningTask && activeNav === "人才库" && (
          <TalentPoolWorkspace mode={talentMode} setMode={setTalentMode} selectedPoolId={selectedPoolId} setSelectedPoolId={setSelectedPoolId} pools={talentPools} setPools={setTalentPools} memberships={talentMemberships} setMemberships={setTalentMemberships} candidates={candidateRecords} positions={positionRecords} onReactivateCandidate={reactivateTalent} onOpenCandidate={openCandidate} onNotify={notify} />
        )}

        {!screeningTask && activeNav === "报表" && (
          <ReportWorkspace candidates={candidateRecords} positions={positionRecords} screeningSummary={screeningSummary} currentRole={currentRole} onDrillDown={drillDownReport} onNotify={notify} />
        )}

        {!screeningTask && activeNav === "设置" && (
          <SettingsWorkspace currentRole={currentRole} onNotify={notify} />
        )}

        {!screeningTask && activeNav !== "工作台" && activeNav !== "职位" && activeNav !== "候选人" && activeNav !== "面试" && activeNav !== "人才库" && activeNav !== "报表" && activeNav !== "设置" && (
          <section className="module-placeholder"><div><BriefcaseBusiness size={26} /><h2>{activeNav}</h2><p>该模块将在后续 UX 任务中继续完善。</p></div></section>
        )}

        {screeningTask && <ScreeningTaskView task={screeningTask} controller={screeningController} onTaskChange={handleTaskChange} onBack={() => setScreeningTask(null)} onOpenCandidate={openCandidate} onNotify={notify} onApplyResults={applyScreeningAction} onUndoResults={applyWorkflowState} />}
      </main>

      {importOpen && <ImportWizard activeJob={activeJob} recentTask={recentTask} controller={screeningController} onClose={() => setImportOpen(false)} onCreateTask={(task) => { setImportOpen(false); handleTaskChange(task); }} onRunCreated={persistRecentServerTask} onResumeTask={(task) => { setImportOpen(false); setScreeningTask(task); }} onNotify={notify} actorName={roleIdentity.name} />}

      {modal === "duplicates" && (
        <Modal title="处理重复候选人" onClose={() => setModal(null)} footer={<><button className="button secondary" type="button" onClick={() => setModal(null)}>暂不处理</button><button className="button primary" type="button" onClick={() => { setModal(null); notify("2 组候选人已合并"); }}>确认合并</button></>}>
          <p className="modal-intro">系统根据手机号、邮箱和履历相似度发现以下重复记录。</p>
          {["候 A2 / 候 B2", "候 C1 / 候 D1"].map((pair) => <label className="duplicate-row" key={pair}><input type="checkbox" defaultChecked /><span className="profile-avatar"><UserRound size={18} /></span><div><strong>{pair}</strong><span>履历相似度 96%，建议保留最近更新记录</span></div><SlidersHorizontal size={17} /></label>)}
        </Modal>
      )}

      {menuOpen && <button className="mobile-scrim" type="button" aria-label="关闭菜单" onClick={() => setMenuOpen(false)} />}
      {toast && <div className="toast" role="status"><Check size={16} />{toast}</div>}
      {sessionMessage && <div className="toast error" role="alert"><CircleAlert size={16} />{sessionMessage}</div>}
    </div>
  );
}
