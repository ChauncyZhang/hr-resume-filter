import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  BriefcaseBusiness,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  FileText,
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
import { candidateController as defaultCandidateController } from "./candidateController.js";
import { jobController as defaultJobController } from "./jobController.js";
import { workbenchController as defaultWorkbenchController } from "./workbenchController.js";
import {
  appendJobPage,
  createInitialJobWorkspaceState,
  failJobRequest,
  startJobRequest,
  succeedJobMutationRefresh,
  succeedJobRequest,
} from "./jobWorkspaceState.js";
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
  "新简历",
  "待复核",
  "待沟通",
  "待安排",
  "面试中",
  "待决策",
];

const emptyStages = stageMeta.map(() => []);

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
        <span className="age">{candidate.age || candidate.lastActivity}</span>
      </div>
      <div className="candidate-role">{candidate.role}{candidate.company ? ` · ${candidate.company}` : ""}</div>
      {candidate.schedule && <div className="meta-line"><CalendarDays size={13} />{candidate.schedule}</div>}
      {candidate.interviewer && <div className="meta-line"><FileText size={13} />{candidate.interviewer}</div>}
      {candidate.note && <div className="candidate-note">{candidate.note}</div>}
      {(candidate.tag || candidate.source) && <span className="source-tag">{candidate.tag || `来自 ${candidate.source}`}</span>}
    </button>
  );
}

function WorkbenchSkeleton() {
  return (
    <div className="page-body workbench-skeleton" role="status" aria-live="polite" aria-label="正在加载工作台">
      <section className="main-column">
        <div className="job-switcher">
          <span className="switcher-label">当前职位</span>
          <div className="job-tabs skeleton-tabs" aria-hidden="true">
            {[0, 1, 2].map((item) => <span key={item} />)}
          </div>
        </div>
        <section className="pipeline-panel">
          <header className="pipeline-header"><div className="skeleton-heading" aria-hidden="true"><span /><span /></div></header>
          <div className="kanban skeleton-kanban" aria-hidden="true">
            {stageMeta.map((stage) => <section className="stage" key={stage}><header><span /></header><div className="stage-list"><span /><span /></div></section>)}
          </div>
        </section>
        <span className="workbench-loading-label">正在加载工作台</span>
      </section>
      <aside className="right-rail" aria-hidden="true">
        <section className="rail-section skeleton-rail"><span /><span /><span /></section>
        <section className="rail-section skeleton-rail compact"><span /><span /></section>
      </aside>
    </div>
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

export function App({ controller = sessionController, screeningController = defaultScreeningController, candidateController = defaultCandidateController, jobController = defaultJobController, workbenchController = defaultWorkbenchController }) {
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
  return <AuthenticatedApp session={session} onLogout={() => controller.logout()} screeningController={screeningController} candidateController={candidateController} jobController={jobController} workbenchController={workbenchController} />;
}

function AuthenticatedApp({ session, onLogout, screeningController, candidateController, jobController, workbenchController }) {
  const currentRole = session.role || "未知角色";
  const recentTaskStorageKey = getRecentScreeningTaskStorageKey(session.user);
  const [activeNav, setActiveNav] = useState(() => getDefaultNavItem(currentRole) || "设置");
  const [activeJob, setActiveJob] = useState("AI 工程师");
  const [menuOpen, setMenuOpen] = useState(false);
  const [view, setView] = useState("board");
  const [modal, setModal] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [toast, setToast] = useState("");
  const [workbenchState, setWorkbenchState] = useState({ status: currentRole === "面试官" ? "unavailable" : "loading", data: null, error: "" });
  const [activeWorkbenchJobId, setActiveWorkbenchJobId] = useState(null);
  const workbenchLoadRef = useRef(null);
  const [jobMode, setJobMode] = useState("list");
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobState, setJobState] = useState(createInitialJobWorkspaceState);
  const jobListRequestRef = useRef(null);
  const jobListRequestSequenceRef = useRef(0);
  const jobMutationRefreshRef = useRef(null);
  const jobMutationRefreshSequenceRef = useRef(0);
  const [positionRecords, setPositionRecords] = useState([]);
  const [candidateMode, setCandidateMode] = useState("list");
  const [candidateRecords, setCandidateRecords] = useState(initialCandidateRecords);
  const [candidateOrigin, setCandidateOrigin] = useState(null);
  const [candidateDetailState, setCandidateDetailState] = useState(null);
  const candidateLoadRef = useRef(null);
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
  const [screeningViewState, setScreeningViewState] = useState(null);
  const [recentTask, setRecentTask] = useState(() => {
    return recentTaskStorageKey ? parseRecentScreeningTask(window.localStorage.getItem(recentTaskStorageKey)) : null;
  });

  const workbenchJobs = workbenchState.data?.jobs || [];
  const activeWorkbenchJob = workbenchJobs.find((job) => job.id === activeWorkbenchJobId) || workbenchJobs[0] || null;
  const stages = activeWorkbenchJob ? stageMeta.map((stage) => activeWorkbenchJob.stages[stage]?.items || []) : emptyStages;
  const visibleStageMeta = stageMeta.map((name, index) => [name, activeWorkbenchJob?.stages[name]?.count || 0, stages[index].length]);
  const emptyTaskGroup = { count: 0, items: [] };
  const workbenchTasks = workbenchState.data?.tasks || { contact: emptyTaskGroup, interviewPending: emptyTaskGroup, decision: emptyTaskGroup };
  const allowedNavItems = useMemo(() => new Set(getAllowedNavItems(currentRole)), [currentRole]);
  const roleIdentity = getSessionIdentity(session.user, currentRole);
  const sessionMessage = getSessionMessage(session.error);
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

  const loadWorkbench = useCallback(async () => {
    if (currentRole === "面试官") return null;
    workbenchLoadRef.current?.abort();
    const controller = new AbortController();
    workbenchLoadRef.current = controller;
    setWorkbenchState((current) => ({ status: "loading", data: current.data, error: "" }));
    try {
      const data = await workbenchController.load({ signal: controller.signal });
      if (workbenchLoadRef.current !== controller) return null;
      setWorkbenchState({ status: "ready", data, error: "" });
      if (data.jobs[0]) {
        setActiveWorkbenchJobId((current) => data.jobs.some((job) => job.id === current) ? current : data.jobs[0].id);
        setActiveJob((current) => data.jobs.some((job) => job.name === current) ? current : data.jobs[0].name);
      } else {
        setActiveWorkbenchJobId(null);
      }
      return data;
    } catch (error) {
      if (error?.name === "AbortError" || workbenchLoadRef.current !== controller) return null;
      setWorkbenchState((current) => ({ status: "error", data: current.data, error: "工作台加载失败，请检查网络后重试。" }));
      return null;
    } finally {
      if (workbenchLoadRef.current === controller) workbenchLoadRef.current = null;
    }
  }, [currentRole, workbenchController]);

  const loadJobs = useCallback(async (filters, { append = false, cursor = null, mutation = false } = {}) => {
    jobListRequestRef.current?.controller.abort();
    const controller = new AbortController();
    const requestId = ++jobListRequestSequenceRef.current;
    jobListRequestRef.current = { controller, requestId };
    setJobState((current) => startJobRequest(current, requestId, filters));
    try {
      const page = await jobController.listJobs({ ...filters, cursor: cursor || undefined, limit: 50 }, { signal: controller.signal });
      if (jobListRequestRef.current?.controller !== controller) return;
      setJobState((current) => append ? appendJobPage(current, requestId, page) : mutation ? succeedJobMutationRefresh(current, requestId, page) : succeedJobRequest(current, requestId, page));
      if (!append && !filters.q && filters.status === "全部" && !filters.departmentId && !filters.ownerId) {
        setPositionRecords(page.records);
        if (page.records[0]) setActiveJob((current) => page.records.some((record) => record.name === current) ? current : page.records[0].name);
      }
      return page;
    } catch (error) {
      if (error?.name === "AbortError" || jobListRequestRef.current?.controller !== controller) return;
      setJobState((current) => failJobRequest(current, requestId, new Error("职位加载失败，请重试。")));
    } finally {
      if (jobListRequestRef.current?.controller === controller) jobListRequestRef.current = null;
    }
    return null;
  }, [jobController]);

  const refreshJobAfterMutation = useCallback(async (mutationRecord) => {
    jobListRequestRef.current?.controller.abort();
    jobMutationRefreshRef.current?.controller.abort();
    const controller = new AbortController();
    const listRequestId = ++jobListRequestSequenceRef.current;
    const mutationRequestId = ++jobMutationRefreshSequenceRef.current;
    jobListRequestRef.current = { controller, requestId: listRequestId };
    jobMutationRefreshRef.current = { controller, requestId: mutationRequestId };
    const filters = jobState.filters;
    setJobState((current) => startJobRequest(current, listRequestId, filters));
    try {
      const [page, definition] = await Promise.all([
        jobController.listJobs({ ...filters, limit: 50 }, { signal: controller.signal }),
        jobController.loadDefinition(mutationRecord.id, { signal: controller.signal }),
      ]);
      if (jobMutationRefreshRef.current?.controller !== controller || jobListRequestRef.current?.controller !== controller) return null;
      const listRecord = page.records.find((record) => record.id === mutationRecord.id) || null;
      const complete = jobController.mergeDefinition(listRecord, definition, page);
      setJobState((current) => succeedJobMutationRefresh(current, listRequestId, page));
      setSelectedJob(complete);
      if (!filters.q && filters.status === "全部" && !filters.departmentId && !filters.ownerId) {
        setPositionRecords(page.records);
      }
      return complete;
    } catch (error) {
      if (error?.name === "AbortError" || jobMutationRefreshRef.current?.controller !== controller) return null;
      setJobState((current) => failJobRequest(current, listRequestId, new Error("职位已更新，但最新数据加载失败，请重试读取。")));
      throw error;
    } finally {
      if (jobListRequestRef.current?.controller === controller) jobListRequestRef.current = null;
      if (jobMutationRefreshRef.current?.controller === controller) jobMutationRefreshRef.current = null;
    }
  }, [jobController, jobState.filters]);

  useEffect(() => {
    const filters = createInitialJobWorkspaceState().filters;
    void loadJobs(filters);
    return () => {
      jobListRequestRef.current?.controller.abort();
      jobListRequestRef.current = null;
      jobMutationRefreshRef.current?.controller.abort();
      jobMutationRefreshRef.current = null;
    };
  }, [loadJobs]);

  useEffect(() => {
    if (activeNav === "工作台" && currentRole !== "面试官") void loadWorkbench();
    return () => {
      workbenchLoadRef.current?.abort();
      workbenchLoadRef.current = null;
    };
  }, [activeNav, currentRole, loadWorkbench]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [activeNav, jobMode, candidateMode, interviewMode, talentMode, Boolean(screeningTask)]);

  useEffect(() => {
    window.localStorage.removeItem(LEGACY_RECENT_SCREENING_TASK_STORAGE_KEY);
    setRecentTask(recentTaskStorageKey ? parseRecentScreeningTask(window.localStorage.getItem(recentTaskStorageKey)) : null);
  }, [recentTaskStorageKey]);

  useEffect(() => () => candidateLoadRef.current?.abort(), []);

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

  async function loadServerCandidate(context) {
    candidateLoadRef.current?.abort();
    const abortController = new AbortController();
    candidateLoadRef.current = abortController;
    setCandidateDetailState({ status: "loading", context, error: "" });
    setSelectedCandidate(null);
    try {
      const candidate = await candidateController.loadReview({
        ...context,
        actor: { id: session.user?.id, name: roleIdentity.name },
      }, { signal: abortController.signal });
      if (candidateLoadRef.current !== abortController) return;
      setSelectedCandidate(candidate);
      setCandidateDetailState({ status: "ready", context, error: "" });
    } catch (error) {
      if (error?.name === "AbortError" || candidateLoadRef.current !== abortController) return;
      setCandidateDetailState({ status: "error", context, error: "请检查网络连接后重试；未加载任何本地示例数据。" });
    } finally {
      if (candidateLoadRef.current === abortController) candidateLoadRef.current = null;
    }
  }

  function openCandidate(summary, nextScreeningViewState = null) {
    if (summary.serverBacked === true) {
      if (!summary.candidateId) return;
      setCandidateOrigin(activeNav === "候选人" && !screeningTask ? null : { activeNav, screeningTask, screeningViewState: nextScreeningViewState });
      setScreeningTask(null);
      setActiveNav("候选人");
      setCandidateMode("detail");
      void loadServerCandidate({ candidateId: summary.candidateId, applicationId: summary.applicationId, jobId: summary.jobId, position: summary.position, evidence: summary.evidence });
      return;
    }
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
    setCandidateDetailState(null);
    setCandidateMode("detail");
  }

  function backFromCandidateDetail() {
    candidateLoadRef.current?.abort();
    candidateLoadRef.current = null;
    if (candidateOrigin) {
      setActiveNav(candidateOrigin.activeNav);
      setScreeningTask(candidateOrigin.screeningTask);
      setScreeningViewState(candidateOrigin.screeningViewState || null);
      setCandidateOrigin(null);
    }
    setSelectedCandidate(null);
    setCandidateDetailState(null);
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
          <header><div><h2>我的面试工作台</h2><p>面试安排与反馈将在服务端面试模块接入后显示。</p></div><span>尚未接入</span></header>
          <section className="workbench-unavailable"><CalendarDays size={24} /><div><strong>暂无可读取的面试数据</strong><p>当前页面不会展示本地示例面试，避免与真实招聘安排混淆。</p></div></section>
        </div>}

        {!screeningTask && activeNav === "工作台" && currentRole !== "面试官" && workbenchState.status === "loading" && !workbenchState.data && <WorkbenchSkeleton />}
        {!screeningTask && activeNav === "工作台" && currentRole !== "面试官" && workbenchState.status === "error" && !workbenchState.data && <div className="workbench-status error" role="alert"><CircleAlert size={22} /><div><strong>工作台暂时无法加载</strong><p>{workbenchState.error}</p></div><button className="button secondary" type="button" onClick={() => void loadWorkbench()}>重试</button></div>}
        {!screeningTask && activeNav === "工作台" && currentRole !== "面试官" && workbenchState.status === "ready" && workbenchJobs.length === 0 && <div className="workbench-status empty"><BriefcaseBusiness size={24} /><div><strong>暂无在招职位</strong><p>{canPerformAction(currentRole, "新建职位") ? "发布职位并导入简历后，这里会显示真实招聘进展。" : "暂无被授权的在招职位，请联系招聘负责人确认职位协作范围。"}</p></div></div>}
        {!screeningTask && activeNav === "工作台" && currentRole !== "面试官" && activeWorkbenchJob && <div className="page-body" aria-busy={workbenchState.status === "loading"}>
          <section className="main-column">
            {workbenchState.status === "error" && <div className="workbench-inline-error" role="alert"><CircleAlert size={17} /><span>{workbenchState.error}，当前展示上次成功数据。</span><button type="button" onClick={() => void loadWorkbench()}>重新加载</button></div>}
            <div className="job-switcher">
              <span className="switcher-label">当前职位</span>
              <div className="job-tabs">
                {workbenchJobs.slice(0, 3).map((job) => (
                  <button key={job.id} type="button" aria-pressed={activeWorkbenchJob.id === job.id} className={activeWorkbenchJob.id === job.id ? "job-tab selected" : "job-tab"} onClick={() => { setActiveWorkbenchJobId(job.id); setActiveJob(job.name); }}>
                    <strong>{job.name}</strong><span>{job.activeCount} 人进行中</span>
                  </button>
                ))}
                {workbenchJobs.length > 3 && <button className="more-jobs" type="button" onClick={() => { setActiveNav("职位"); setJobMode("list"); }}>更多职位<ChevronDown size={15} /></button>}
              </div>
            </div>

            <section className="pipeline-panel">
              <header className="pipeline-header">
                <div><h2>{activeWorkbenchJob.name}</h2><span>{activeWorkbenchJob.department}</span></div>
                <div className="pipeline-tools">
                  <button type="button" className="text-tool" onClick={() => setView((value) => value === "board" ? "list" : "board")}><LayoutList size={16} />{view === "board" ? "视图" : "看板"}</button>
                  <IconButton label="更多操作" onClick={() => notify("已打开职位操作菜单")}><MoreHorizontal size={19} /></IconButton>
                </div>
              </header>

              {view === "board" ? (
                <div className="kanban" aria-label="候选人招聘阶段">
                  {visibleStageMeta.map(([name, count, loadedCount], index) => (
                    <section className="stage" key={name}>
                      <header><strong>{name}</strong><span>{count}</span></header>
                      <div className="stage-list">
                        {stages[index].slice(0, 5).map((candidate) => (
                          <CandidateCard key={candidate.applicationId || candidate.id} candidate={candidate} onOpen={openCandidate} />
                        ))}
                      </div>
                      {count > loadedCount && <button className="load-more" type="button" onClick={() => { setCandidatePreset({ jobId: activeWorkbenchJob.id, position: activeWorkbenchJob.name, stage: name }); setActiveNav("候选人"); }}><Plus size={14} />查看其余 {count - loadedCount} 人</button>}
                    </section>
                  ))}
                </div>
              ) : (
                <div className="list-view">
                  <div className="list-head"><span>候选人</span><span>当前阶段</span><span>最近进展</span><span>操作</span></div>
                  {stages.flat().slice(0, 10).map((candidate) => (
                    <button type="button" className="list-row" key={candidate.applicationId || candidate.id} onClick={() => openCandidate(candidate)}>
                      <span><span className="avatar-mini"><UserRound size={11} /></span><strong>{candidate.name}</strong></span>
                      <span>{visibleStageMeta.find((_, stageIndex) => stages[stageIndex].includes(candidate))?.[0]}</span>
                      <span>{candidate.lastActivity || candidate.age || candidate.schedule || candidate.note}</span>
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </div>
              )}

            </section>
            <footer className="updated">更新时间：{workbenchState.data?.generatedAt ? new Date(workbenchState.data.generatedAt).toLocaleString("zh-CN", { hour12: false }) : "刚刚"} <button type="button" onClick={() => void loadWorkbench()}>刷新</button></footer>
          </section>

          <aside className="right-rail">
            <section className="rail-section">
              <header><h3>待处理事项</h3><IconButton label="更多"><MoreHorizontal size={18} /></IconButton></header>
              <div className="rail-group">
                <div className="rail-group-title"><span className="status-dot red" />待沟通（{workbenchTasks.contact.count}）<button type="button" onClick={() => { setCandidatePreset({ position: "全部职位", stage: "待沟通" }); setActiveNav("候选人"); }}>查看全部</button></div>
                {workbenchTasks.contact.items.slice(0, 3).map((candidate) => <button className="rail-item" type="button" key={candidate.applicationId} onClick={() => openCandidate(candidate)}>{candidate.name}<small>{candidate.position} · {candidate.city}</small></button>)}
                {workbenchTasks.contact.count === 0 && <p>暂无待沟通候选人</p>}
              </div>
              <div className="rail-group">
                <div className="rail-group-title"><span className="status-dot orange" />待安排面试（{workbenchTasks.interviewPending.count}）<button type="button" onClick={() => { setCandidatePreset({ position: "全部职位", stage: "待安排" }); setActiveNav("候选人"); }}>查看全部</button></div>
                {workbenchTasks.interviewPending.items.slice(0, 3).map((candidate) => <button className="rail-item" type="button" key={candidate.applicationId} onClick={() => openCandidate(candidate)}>{candidate.name}<small>{candidate.position} · {candidate.city}</small></button>)}
                {workbenchTasks.interviewPending.count === 0 && <p>暂无待安排面试</p>}
              </div>
              <div className="rail-group compact">
                <div className="rail-group-title"><span className="status-dot blue" />待决策（{workbenchTasks.decision.count}）<button type="button" onClick={() => { setCandidatePreset({ position: "全部职位", stage: "待决策" }); setActiveNav("候选人"); }}>查看全部</button></div>
                {workbenchTasks.decision.items.slice(0, 3).map((candidate) => <button className="rail-item" type="button" key={candidate.applicationId} onClick={() => openCandidate(candidate)}>{candidate.name}<small>{candidate.position} · {candidate.city}</small></button>)}
                {workbenchTasks.decision.count === 0 && <p>暂无待决策候选人</p>}
              </div>
            </section>

            <section className="rail-section calendar-card">
              <header><h3>面试日历（未来 7 天）</h3></header>
              <div className="calendar-empty-slot">面试服务尚未接入，当前不展示示例日程</div>
            </section>
          </aside>
        </div>}

        {!screeningTask && activeNav === "职位" && (
          <JobsWorkspace
            mode={jobMode}
            setMode={setJobMode}
            selectedJob={selectedJob}
            setSelectedJob={setSelectedJob}
            listState={jobState}
            onLoadJobs={loadJobs}
            jobController={jobController}
            candidateController={candidateController}
            onRefreshJobMutation={refreshJobAfterMutation}
            onNotify={notify}
            onImport={() => { setActiveJob(selectedJob?.name || activeJob); setImportOpen(true); }}
            onOpenCandidate={openCandidate}
          />
        )}

        {!screeningTask && activeNav === "候选人" && (
          <CandidatesWorkspace mode={candidateMode} setMode={setCandidateMode} selectedCandidate={selectedCandidate} setSelectedCandidate={setSelectedCandidate} records={candidateRecords} setRecords={updateCandidateRecords} onNotify={notify} onBackDetail={backFromCandidateDetail} detailBackLabel={candidateOrigin?.activeNav === "工作台" ? "返回工作台" : candidateOrigin ? "返回筛选任务" : "返回候选人列表"} onOpenCandidate={openCandidate} onScheduleInterview={(candidate) => openScheduleInterview(candidate)} onOpenInterviewFeedback={openFeedbackInterview} onAddToTalentPool={addCandidatesToTalentPool} initialFilters={candidatePreset} actorName={roleIdentity.name} controller={candidateController} detailState={candidateDetailState} onRetryDetail={() => candidateDetailState?.context ? loadServerCandidate(candidateDetailState.context) : Promise.resolve()} />
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

        {screeningTask && <ScreeningTaskView task={screeningTask} initialViewState={screeningViewState} controller={screeningController} onTaskChange={handleTaskChange} onBack={() => setScreeningTask(null)} onOpenCandidate={openCandidate} onNotify={notify} onApplyResults={applyScreeningAction} onUndoResults={applyWorkflowState} />}
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
