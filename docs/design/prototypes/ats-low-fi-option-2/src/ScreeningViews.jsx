import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Bot,
  Check,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Clock3,
  Download,
  FileArchive,
  FileText,
  Filter,
  Import,
  LoaderCircle,
  Plus,
  Redo2,
  RotateCcw,
  Search,
  Trash2,
  UserRoundCheck,
  X,
} from "lucide-react";
import { screeningController as defaultScreeningController } from "./screeningController.js";
import { createScreeningWorkflow, pollServerTask } from "./screeningIntegration.js";

const demoFiles = [
  { id: "f1", name: "AI工程师_李嘉明.pdf", size: "1.4 MB", type: "PDF", valid: true },
  { id: "f2", name: "算法工程师_王晨.docx", size: "860 KB", type: "DOCX", valid: true },
  { id: "f3", name: "大模型应用_赵宁.pdf", size: "1.1 MB", type: "PDF", valid: true },
  { id: "f4", name: "候选人简历_陈浩.pdf", size: "2.0 MB", type: "PDF", valid: true },
  { id: "f5", name: "算法实习生_孙悦.pdf", size: "720 KB", type: "PDF", valid: true },
  { id: "f6", name: "候选人作品集.zip", size: "8.6 MB", type: "ZIP", valid: false, error: "不支持 ZIP 文件，请仅上传 PDF、DOCX 或 TXT" },
].map((file) => ({ ...file, example: true }));

const resultProfiles = [
  { candidate: "李嘉明", recommendation: "可沟通", ruleScore: 81, llmScore: 78, matched: "Python、LLM、RAG", missing: "Kubernetes", risk: "项目规模待确认" },
  { candidate: "王晨", recommendation: "人工复核", ruleScore: 74, llmScore: 72, matched: "Python、机器学习", missing: "Agent", risk: "大模型经验偏少" },
  { candidate: "赵宁", recommendation: "优先沟通", ruleScore: 88, llmScore: 84, matched: "LLM、RAG、Agent", missing: "无明显缺失", risk: "到岗时间待确认" },
  { candidate: "陈浩", recommendation: "待重试", ruleScore: null, llmScore: null, matched: "—", missing: "—", risk: "文件解析失败" },
  { candidate: "孙悦", recommendation: "人工复核", ruleScore: 66, llmScore: null, matched: "Python、深度学习", missing: "项目经验", risk: "LLM 评分失败" },
];

export function statusLabel(status) {
  return {
    queued: "排队中",
    running: "处理中",
    success: "成功",
    partial: "部分成功",
    failed: "失败",
    complete: "已完成",
    cancelled: "已取消",
  }[status] || status;
}

function fileStatusClass(status) {
  return status === "success" ? "success" : status === "partial" ? "partial" : status === "failed" ? "failed" : status === "cancelled" ? "cancelled" : "running";
}

export function resolveInitialJobId(jobs, activeJob) {
  const matches = jobs.filter((job) => job.title === activeJob);
  return matches.length === 1 ? matches[0].id : "";
}

function shortJobId(id) {
  return id.length <= 8 ? id : `${id.slice(0, 4)}…${id.slice(-4)}`;
}

export function jobOptionLabel(job, jobs) {
  const duplicateTitle = jobs.filter((item) => item.title === job.title).length > 1;
  return duplicateTitle ? `${job.title}（ID: ${shortJobId(job.id)}）` : job.title;
}

export function canAdvanceFromFiles(files) {
  return files.length > 0 && files.every((file) => file.valid && file.sourceFile && !file.example);
}

export function candidateDisplayName(file, serverBacked) {
  if (!serverBacked) return file.candidate || "待识别候选人";
  return file.candidate ? `${file.candidate}（待核验）` : "候选人姓名待核验";
}

export function canOpenCandidateReview(file, serverBacked) {
  const completed = file?.status === "success" || file?.status === "partial";
  if (!completed) return false;
  return serverBacked !== true || (typeof file?.candidateId === "string" && file.candidateId.trim().length > 0);
}

export function candidateReviewContext(file, task) {
  return {
    candidateId: file.candidateId,
    jobId: task.jobId,
    position: task.position,
    evidence: {
      ruleScore: file.ruleScore,
      llmScore: file.llmScore,
      recommendation: file.recommendation,
      matched: file.matched,
      missing: file.missing,
      risk: file.risk,
      llmReason: file.llmReason,
    },
  };
}

export function serverIssueMessage(file) {
  if (file.status === "partial") return file.llmRetryable ? "LLM 评估未完成，规则结果已保留；可使用下方“重试 LLM”操作。" : "LLM 评估未完成，规则结果已保留；当前没有可用的 LLM 重试操作。";
  if (file.status === "failed" && file.error === "malware_detected") return "检测到恶意文件，已拒绝并从隔离区删除。";
  if (file.status === "failed") return file.retryable ? "文件处理失败，可使用下方“重新解析”操作。" : "文件处理失败，当前没有可用的重试操作。";
  if (file.llmStatus === "skipped" || file.llmStatus === "not_requested") return "LLM 未启用，规则评分已保留；请由招聘团队完成人工复核。";
  return file.risk || "—";
}

export function taskMetadataLine(task) {
  if (!task.serverBacked) return `${task.id} · ${task.source} · 发起人 ${task.creator} · ${task.createdAt}`;
  return `${task.id} · 来源备注（本机）${task.source} · 发起人记录（本机）${task.creator} · ${task.createdAt}`;
}

export function isAdvanceSelectable(file, serverBacked) {
  return serverBacked === true
    && (file?.status === "success" || file?.status === "partial")
    && file?.application_stage === "new"
    && Number.isInteger(file?.application_version)
    && file.application_version > 0;
}

export function restoreScreeningViewState(viewState, task) {
  if (viewState?.taskId !== task?.id) return { query: "", filter: "全部", selected: [] };
  const validFilters = ["全部", "处理中", "成功", "部分成功", "失败"];
  const selected = Array.isArray(viewState.selected) ? viewState.selected : [];
  return {
    query: typeof viewState.query === "string" ? viewState.query : "",
    filter: validFilters.includes(viewState.filter) ? viewState.filter : "全部",
    selected: selected.filter((id) => task.files.some((file) => file.id === id && isAdvanceSelectable(file, task.serverBacked))),
  };
}

export function advanceItems(files, selectedIds) {
  const selected = new Set(selectedIds);
  return files
    .filter((file) => selected.has(file.id) && isAdvanceSelectable(file, true))
    .map((file) => ({
      item_id: file.id,
      expected_application_version: file.application_version,
    }));
}

function safeActionCount(value) {
  return Number.isInteger(value) && value >= 0 ? value : 0;
}

export function advanceSuccessMessage(result) {
  const applied = safeActionCount(result?.applied);
  const alreadyApplied = safeActionCount(result?.already_applied);
  return `已推进 ${applied + alreadyApplied} 位候选人到待复核（新推进 ${applied} 位，已在待复核 ${alreadyApplied} 位）`;
}

export function advanceErrorMessage(error) {
  return error?.status === 409
    ? "推进未完成，候选人状态可能已变化；正在刷新服务端结果，请重新选择。"
    : "推进失败，请稍后重试。";
}

export function bulkUndoActionState(items, submitting) {
  return {
    visible: Array.isArray(items) && items.length > 0,
    disabled: submitting === true,
    label: submitting ? "撤销中" : "撤销批量推进",
  };
}

export function undoSuccessMessage(result) {
  return `已撤销 ${safeActionCount(result?.applied)} 位候选人的本次批量推进，服务端结果已刷新。`;
}

export function undoErrorMessage(error) {
  return error?.status === 409
    ? "无法撤销：候选人状态已变化，已刷新服务端结果。"
    : "撤销失败，请稍后重试。";
}

export function progressSummary(task, currentFile = "") {
  if (task.status === "running") return `正在处理：${currentFile}`;
  if (task.status === "cancelled") return `任务已取消：已处理 ${task.completed}/${task.total} 份简历`;
  return `处理完成：${task.completed}/${task.total} 份简历`;
}

export function reconcileRetryingIds(retryingIds, files) {
  const byId = new Map(files.map((file) => [file.id, file]));
  return retryingIds.filter((id) => {
    const file = byId.get(id);
    return (file?.status === "failed" && file.retryable === true)
      || (file?.status === "partial" && file.llmRetryable === true);
  });
}

export function ImportWizard({ activeJob, recentTask, onClose, onCreateTask, onRunCreated, onResumeTask, onNotify, actorName = "张小北", controller = defaultScreeningController }) {
  const [step, setStep] = useState(1);
  const [serverJobs, setServerJobs] = useState([]);
  const [jobsState, setJobsState] = useState("loading");
  const [position, setPosition] = useState("");
  const [source, setSource] = useState("BOSS 直聘");
  const [note, setNote] = useState("7 月 AI 工程师主动搜寻批次");
  const [files, setFiles] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ completed: 0, total: 0 });
  const fileInputRef = useRef(null);
  const abortRef = useRef(null);
  const workflowRef = useRef(null);

  if (!workflowRef.current) workflowRef.current = createScreeningWorkflow(controller);

  useEffect(() => {
    const abortController = new AbortController();
    abortRef.current = abortController;
    setJobsState("loading");
    controller.listJobs({ signal: abortController.signal }).then((authorizedJobs) => {
      if (abortController.signal.aborted) return;
      setServerJobs(authorizedJobs);
      setPosition(resolveInitialJobId(authorizedJobs, activeJob));
      setJobsState(authorizedJobs.length > 0 ? "ready" : "empty");
    }).catch((loadError) => {
      if (loadError?.name === "AbortError" || abortController.signal.aborted) return;
      setServerJobs([]);
      setPosition("");
      setJobsState("error");
    });
    return () => abortController.abort();
  }, [activeJob, controller]);

  const validFiles = files.filter((file) => file.valid);
  const invalidFiles = files.filter((file) => !file.valid);

  function selectLocalFiles(event) {
    const selectedFiles = [...event.target.files].map((file, index) => {
      const extension = file.name.split(".").pop()?.toLowerCase();
      const valid = ["pdf", "docx", "txt"].includes(extension);
      const candidate = file.name.replace(/\.(pdf|docx|txt)$/i, "").split(/[_-]/).pop() || `候选人 ${index + 1}`;
      return {
        id: `LOCAL-${Date.now()}-${index}`,
        name: file.name,
        candidate,
        email: `local-${index + 1}@example.com`,
        phone: `138****${String(index + 1).padStart(4, "0")}`,
        size: file.size > 1024 * 1024 ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`,
        type: extension?.toUpperCase() || "未知",
        valid,
        sourceFile: file,
        error: valid ? null : "不支持该文件格式，请仅上传 PDF、DOCX 或 TXT",
        expectedParseStatus: "success",
        expectedLlmStatus: "success",
      };
    });
    setFiles(selectedFiles);
    setError("");
    event.target.value = "";
  }

  function next() {
    if (step === 1 && (jobsState !== "ready" || !position)) {
      setError(jobsState === "empty" ? "暂无可用职位，无法创建筛选任务" : "职位列表尚未就绪，请稍后重试");
      return;
    }
    if (step === 1 && !source) {
      setError("请选择简历的合法来源");
      return;
    }
    if (step === 2 && validFiles.length === 0) {
      setError("请至少选择一份有效简历");
      return;
    }
    if (step === 2 && invalidFiles.length > 0) {
      setError("请先移除不支持的文件");
      return;
    }
    if (step === 2 && files.some((file) => file.example)) {
      setError("格式错误示例不会上传或创建任务，请选择本地简历继续");
      return;
    }
    setError("");
    setStep((current) => Math.min(3, current + 1));
  }

  async function createTask() {
    if (submitting || workflowRef.current.isSubmitting()) return;
    const selectedJob = serverJobs.find((job) => job.id === position);
    if (!selectedJob || !canAdvanceFromFiles(files)) return;
    setSubmitting(true);
    setError("");
    try {
      const result = await workflowRef.current.submit({
        jobId: selectedJob.id,
        files: validFiles.map((file) => file.sourceFile),
        metadata: { position: selectedJob.title, source, note, creator: actorName, createdAt: "刚刚" },
        signal: abortRef.current?.signal,
        onProgress: setUploadProgress,
        onRunCreated,
      });
      if (!result) return;
      onCreateTask(result.task);
      if (result.failedCount > 0) onNotify?.(`${result.failedCount} 份简历上传失败，其余文件已开始筛选`);
    } catch (submitError) {
      if (submitError?.name === "AbortError") return;
      setError(submitError?.code === "ALL_UPLOADS_FAILED" ? "所有文件均上传失败，请检查文件后重试" : "筛选任务创建失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="screening-modal-backdrop" role="presentation" onMouseDown={() => { if (!submitting) onClose(); }}>
      <section className="screening-modal" role="dialog" aria-modal="true" aria-label="导入并筛选简历" onMouseDown={(event) => event.stopPropagation()}>
        <header className="screening-modal-header">
          <div><h2>导入并筛选简历</h2><p>为职位创建一次可跟踪、可恢复的筛选任务。</p></div>
          <button className="icon-button" type="button" aria-label={submitting ? "正在上传，暂时无法关闭" : "关闭"} disabled={submitting} onClick={onClose}><X size={20} /></button>
        </header>

        <div className="wizard-steps" aria-label="导入步骤">
          {["批次信息", "文件校验", "确认创建"].map((label, index) => <div key={label} className={step === index + 1 ? "active" : step > index + 1 ? "done" : ""}><span>{step > index + 1 ? <Check size={14} /> : index + 1}</span><strong>{label}</strong>{index < 2 && <i />}</div>)}
        </div>

        <div className="screening-modal-body">
          {step === 1 && <div className="wizard-section">
            {recentTask?.serverBacked && <button className="recent-task-banner" type="button" onClick={() => onResumeTask({ ...recentTask, status: "running", completed: 0, total: 0, files: [] })}><Clock3 size={18} /><span><strong>继续最近的筛选任务</strong><small>{recentTask.id} · {recentTask.position} · 打开后获取最新进度</small></span><ChevronRight size={17} /></button>}
            <div className="wizard-grid">
              <label>目标职位<select value={position} disabled={jobsState !== "ready"} onChange={(event) => setPosition(event.target.value)} aria-describedby="server-jobs-state"><option value="">{jobsState === "loading" ? "正在加载可用职位…" : jobsState === "error" ? "职位加载失败，请关闭后重试" : jobsState === "empty" ? "暂无可用职位" : "请选择职位"}</option>{serverJobs.map((job) => <option key={job.id} value={job.id}>{jobOptionLabel(job, serverJobs)}</option>)}</select><small id="server-jobs-state" className="field-state" aria-live="polite">{jobsState === "error" ? "无法获取授权职位，当前不能继续。" : jobsState === "empty" ? "当前账号没有可用于筛选的职位。" : ""}</small></label>
              <label>简历来源<select value={source} onChange={(event) => setSource(event.target.value)}><option>BOSS 直聘</option><option>猎聘</option><option>智联招聘</option><option>员工内推</option><option>人才库重新激活</option><option>其他合法来源</option></select></label>
            </div>
            <label className="wizard-field">批次说明<textarea rows="4" value={note} onChange={(event) => setNote(event.target.value)} placeholder="例如：7 月 AI 工程师主动搜寻批次" /></label>
            <div className="privacy-note"><CircleAlert size={17} /><span>请确认简历来源合法并符合公司隐私政策。候选人数据仅用于本次招聘流程。</span></div>
          </div>}

          {step === 2 && <div className="wizard-section">
            <input ref={fileInputRef} className="visually-hidden" type="file" accept=".pdf,.docx,.txt" multiple onChange={selectLocalFiles} />
            {files.length === 0 ? <div className="wizard-dropzone-group"><button className="wizard-dropzone" type="button" onClick={() => fileInputRef.current?.click()}><Import size={28} /><strong>选择本地简历</strong><span>支持 PDF、DOCX 或 TXT，将按顺序逐份上传</span></button><button className="text-button" type="button" onClick={() => setFiles(demoFiles)}>查看格式错误示例</button></div> : <>
              <div className="file-summary"><span><strong>{validFiles.length}</strong> 份有效简历</span><span>{files.some((file) => file.example) ? "格式错误示例（不可创建）" : files.some((file) => file.synthetic) ? "UX-08 合成数据" : "本地选择"}</span><span className={invalidFiles.length || files.some((file) => file.example) ? "has-error" : "is-valid"}>{files.some((file) => file.example) ? "仅用于查看校验状态" : invalidFiles.length ? `${invalidFiles.length} 个文件需处理` : "全部文件可导入"}</span><button type="button" onClick={() => fileInputRef.current?.click()}><Plus size={15} />重新选择</button></div>
              {files.some((file) => file.example) && <div className="privacy-note" role="status"><CircleAlert size={17} /><span>以下内容是格式校验示例，不会上传，也不能进入真实任务创建流程。</span></div>}
              <div className="import-file-list">{files.map((file) => <div className={file.valid ? "" : "invalid"} key={file.id}><span className="file-icon">{file.valid ? <FileText size={18} /> : <FileArchive size={18} />}</span><span><strong>{file.name}</strong><small>{file.type} · {file.size}{file.error ? ` · ${file.error}` : ""}</small></span><span className={file.example || !file.valid ? "invalid-label" : "valid-label"}>{file.example ? "示例" : file.valid ? "可导入" : "不支持"}</span><button type="button" aria-label={`移除 ${file.name}`} onClick={() => setFiles((current) => current.filter((item) => item.id !== file.id))}><Trash2 size={16} /></button></div>)}</div>
            </>}
          </div>}

          {step === 3 && <div className="wizard-section confirmation-section">
            <div className="confirmation-summary">
              <h3>任务摘要</h3>
              <dl><div><dt>目标职位</dt><dd>{serverJobs.find((job) => job.id === position)?.title || "—"}</dd></div><div><dt>简历来源</dt><dd>{source}</dd></div><div><dt>批次说明</dt><dd>{note || "未填写"}</dd></div><div><dt>有效文件</dt><dd>{validFiles.length} 份</dd></div></dl>
            </div>
            <div className="screening-options">
              <label><span><FileText size={18} /><span><strong>规则评分</strong><small>根据职位必须条件、加分项和风险规则评分</small></span></span><input type="checkbox" checked readOnly /></label>
              <label><span><Bot size={18} /><span><strong>LLM 语义评估</strong><small>是否启用由系统设置决定；LLM 部分失败时仍保留规则结果</small></span></span><span>由系统设置决定</span></label>
            </div>
            <p className="background-task-note"><Clock3 size={16} />创建后可离开页面，任务会在后台继续；再次进入可通过任务 ID 恢复进度。</p>
          </div>}
          {error && <p className="wizard-error"><CircleAlert size={15} />{error}</p>}
        </div>

        <footer className="screening-modal-footer">
          <button className="button secondary" type="button" disabled={submitting} onClick={step === 1 ? onClose : () => setStep((current) => current - 1)}>{step === 1 ? "取消" : "上一步"}</button>
          {step < 3 ? <button className="button primary" type="button" disabled={submitting || (step === 1 && jobsState !== "ready") || (step === 2 && !canAdvanceFromFiles(files))} onClick={next}>下一步</button> : <button className="button primary" type="button" disabled={submitting || !canAdvanceFromFiles(files)} onClick={createTask}><Import size={16} />{submitting ? `正在上传 ${uploadProgress.completed}/${uploadProgress.total}` : "创建筛选任务"}</button>}
        </footer>
      </section>
    </div>
  );
}

export function ScreeningTaskView({ task: initialTask, initialViewState, onTaskChange, onBack, onOpenCandidate, onNotify, controller = defaultScreeningController }) {
  const restoredViewState = restoreScreeningViewState(initialViewState, initialTask);
  const [task, setTask] = useState(initialTask);
  const [filter, setFilter] = useState(restoredViewState.filter);
  const [query, setQuery] = useState(restoredViewState.query);
  const [selected, setSelected] = useState(restoredViewState.selected);
  const [pollError, setPollError] = useState("");
  const [bulkError, setBulkError] = useState("");
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [undoItems, setUndoItems] = useState([]);
  const [pollAttempt, setPollAttempt] = useState(0);
  const [retryingIds, setRetryingIds] = useState([]);
  const pollingRef = useRef(null);
  const retryingRef = useRef(new Set());
  const bulkAbortRef = useRef(null);

  useEffect(() => {
    const nextViewState = restoreScreeningViewState(initialViewState, initialTask);
    setTask(initialTask);
    setFilter(nextViewState.filter);
    setQuery(nextViewState.query);
    setSelected(nextViewState.selected);
    setBulkError("");
    setBulkSubmitting(false);
    setUndoItems([]);
    bulkAbortRef.current?.abort();
    bulkAbortRef.current = null;
    retryingRef.current.clear();
    setRetryingIds([]);
  }, [initialTask.id]);

  useEffect(() => () => bulkAbortRef.current?.abort(), []);

  useEffect(() => {
    onTaskChange(task);
  }, [onTaskChange, task]);

  useEffect(() => {
    if (!initialTask.serverBacked) return undefined;
    const abortController = new AbortController();
    setPollError("");
    pollingRef.current = pollServerTask({
      task: initialTask,
      controller,
      signal: abortController.signal,
      onTaskChange: setTask,
      onError: (pollFailure) => setPollError(pollFailure?.code === "RECOVERED_RUN_EMPTY" ? "该任务在上传前中断，没有可恢复的简历，请返回后重新导入。" : "暂时无法获取最新进度，已保留上次结果。"),
    });
    return () => abortController.abort();
  }, [controller, initialTask.id, initialTask.serverBacked, pollAttempt]);

  useEffect(() => {
    if (task.serverBacked || task.status !== "running") return undefined;
    const timer = window.setTimeout(() => {
      setTask((current) => {
        const index = current.completed;
        if (index >= current.files.length) return current;
        const files = current.files.map((file, fileIndex) => {
          if (fileIndex !== index) return file;
          if (file.expectedParseStatus === "failed" || (!file.expectedParseStatus && index === 3)) return { ...file, status: "failed", recommendation: "待重试", traceId: "TR-PARSE-4081", error: "PDF 文本层损坏，未能提取有效内容" };
          if ((file.expectedLlmStatus === "failed" || (!file.expectedLlmStatus && index === 4)) && current.llmEnabled) return { ...file, status: "partial", traceId: "TR-LLM-4297", error: "LLM 请求额度暂时不可用，已保留规则评分" };
          return { ...file, status: "success" };
        });
        const completed = index + 1;
        const finished = completed === files.length;
        return { ...current, files, completed, elapsed: current.elapsed + 7, stage: finished ? "已完成" : completed < 2 ? "规则评分中" : "LLM 评分中", status: finished ? (files.some((file) => file.status === "failed" || file.status === "partial") ? "partial" : "complete") : "running" };
      });
    }, 650);
    return () => window.clearTimeout(timer);
  }, [task]);

  const counts = useMemo(() => ({
    全部: task.files.length,
    处理中: task.files.filter((file) => file.status === "queued" || file.status === "running").length,
    成功: task.files.filter((file) => file.status === "success").length,
    部分成功: task.files.filter((file) => file.status === "partial").length,
    失败: task.files.filter((file) => file.status === "failed").length,
  }), [task.files]);

  const filtered = useMemo(() => task.files.filter((file) => {
    const matchQuery = !query || `${file.name}${file.candidate}`.toLowerCase().includes(query.toLowerCase());
    const matchFilter = filter === "全部" || (filter === "处理中" && ["queued", "running"].includes(file.status)) || (filter === "成功" && file.status === "success") || (filter === "部分成功" && file.status === "partial") || (filter === "失败" && file.status === "failed");
    return matchQuery && matchFilter;
  }), [filter, query, task.files]);

  const total = task.serverBacked ? task.total : task.files.length;
  const currentFile = task.files[task.completed]?.name || (task.serverBacked && total === 0 ? "正在获取服务端任务" : "全部文件已处理");
  const selectableIds = filtered.filter((file) => isAdvanceSelectable(file, task.serverBacked)).map((file) => file.id);
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => selected.includes(id));
  const undoAction = bulkUndoActionState(undoItems, bulkSubmitting);

  useEffect(() => {
    setSelected((current) => current.filter((id) => task.files.some((file) => file.id === id && isAdvanceSelectable(file, task.serverBacked))));
    setRetryingIds((current) => {
      const next = reconcileRetryingIds(current, task.files);
      retryingRef.current = new Set(next);
      return next;
    });
  }, [task.files, task.serverBacked]);

  async function retry(id, kind) {
    if (retryingRef.current.has(id)) return;
    retryingRef.current.add(id);
    setRetryingIds((current) => [...current, id]);
    if (task.serverBacked) {
      setPollError("");
      const accepted = await pollingRef.current?.retry(id);
      if (accepted) {
        onNotify("已提交单文件重试，正在刷新服务端进度");
      } else {
        retryingRef.current.delete(id);
        setRetryingIds((current) => current.filter((itemId) => itemId !== id));
      }
      return;
    }
    try {
      setTask((current) => {
        const files = current.files.map((file) => file.id === id ? { ...file, status: "success", traceId: null, error: null, ruleScore: file.ruleScore ?? 71, llmScore: kind === "llm" ? 69 : (file.llmScore ?? 68), recommendation: "人工复核" } : file);
        return { ...current, files, status: files.some((file) => file.status === "failed" || file.status === "partial") ? "partial" : "complete" };
      });
      onNotify(kind === "llm" ? "LLM 评分重试成功" : "文件重新解析成功");
    } finally {
      retryingRef.current.delete(id);
      setRetryingIds((current) => current.filter((itemId) => itemId !== id));
    }
  }

  async function advanceToReview() {
    const items = advanceItems(task.files, selected);
    if (bulkSubmitting || items.length === 0) return;
    const abortController = new AbortController();
    bulkAbortRef.current?.abort();
    bulkAbortRef.current = abortController;
    setBulkSubmitting(true);
    setBulkError("");
    try {
      const result = await controller.bulkAction(task.id, items, { signal: abortController.signal });
      if (abortController.signal.aborted) return;
      setSelected([]);
      setUndoItems(result.undo_items);
      onNotify(advanceSuccessMessage(result));
      setPollAttempt((value) => value + 1);
    } catch (error) {
      if (abortController.signal.aborted || error?.name === "AbortError") return;
      setBulkError(advanceErrorMessage(error));
      if (error?.status === 409) setPollAttempt((value) => value + 1);
    } finally {
      if (bulkAbortRef.current === abortController) {
        bulkAbortRef.current = null;
        setBulkSubmitting(false);
      }
    }
  }

  async function undoBulkAdvance() {
    if (bulkSubmitting || undoItems.length === 0) return;
    const abortController = new AbortController();
    bulkAbortRef.current?.abort();
    bulkAbortRef.current = abortController;
    setBulkSubmitting(true);
    setBulkError("");
    try {
      const result = await controller.undoBulkAction(task.id, undoItems, { signal: abortController.signal });
      if (abortController.signal.aborted) return;
      setUndoItems([]);
      setPollAttempt((value) => value + 1);
      onNotify(undoSuccessMessage(result));
    } catch (error) {
      if (abortController.signal.aborted || error?.name === "AbortError") return;
      setBulkError(undoErrorMessage(error));
      if (error?.status === 409) {
        setUndoItems([]);
        setPollAttempt((value) => value + 1);
      }
    } finally {
      if (bulkAbortRef.current === abortController) {
        bulkAbortRef.current = null;
        setBulkSubmitting(false);
      }
    }
  }

  return (
    <div className="screening-task-page">
      <button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />返回来源页面</button>
      <section className="task-overview">
        <div className="task-title-row"><span className={`task-state-icon ${task.status}`} >{task.status === "running" ? <LoaderCircle size={21} /> : task.status === "complete" ? <CircleCheck size={21} /> : <CircleAlert size={21} />}</span><div><div><h2>{task.position} · 简历筛选任务</h2><span className={`task-status ${fileStatusClass(task.status)}`}>{statusLabel(task.status)}</span></div><p>{taskMetadataLine(task)}</p></div></div>
        {task.serverBacked ? <button className="button secondary" type="button" disabled title="服务端导出尚未实现"><Download size={16} />导出结果（暂不可用）</button> : <button className="button secondary" type="button" onClick={() => onNotify("筛选结果导出任务已创建")}><Download size={16} />导出结果</button>}
      </section>

      <section className="task-progress-panel">
        <div className="progress-primary"><div><span>处理进度</span><strong>{task.completed}/{total}</strong></div><div className="task-progress-track"><span style={{ width: `${total > 0 ? (task.completed / total) * 100 : 0}%` }} /></div><p>{progressSummary({ ...task, total }, currentFile)}<span>当前阶段：{task.stage || (task.status === "running" ? "服务端处理中" : task.status === "cancelled" ? "已取消" : "服务端已结束")}</span></p></div>
        <div className="progress-stats"><div><strong>{counts.成功}</strong><span>成功</span></div><div><strong>{counts.部分成功}</strong><span>部分成功</span></div><div><strong>{counts.失败}</strong><span>失败</span></div><div><strong>{task.serverBacked ? `${task.completed}/${total}` : `${task.elapsed}s`}</strong><span>{task.serverBacked ? "服务端进度" : "已耗时"}</span></div></div>
      </section>

      {pollError && <div className="task-poll-error" role="alert"><CircleAlert size={17} /><span>{pollError}</span><button type="button" onClick={() => setPollAttempt((value) => value + 1)}>重试获取</button></div>}
      {task.status === "running" && <p className="task-background-tip"><Clock3 size={15} />任务正在后台处理，可以安全离开此页面；稍后通过任务 ID 恢复。</p>}
      {(counts.失败 > 0 || counts.部分成功 > 0) && task.status !== "running" && <div className="partial-warning"><CircleAlert size={18} /><div><strong>部分文件需要处理</strong><span>单文件失败没有影响其他简历。可在对应行查看原因并单独重试。</span></div></div>}

      <section className="task-results-panel">
        <header className="results-header"><div><h3>逐文件结果</h3><span>{task.serverBacked ? `本机批次备注：${task.note}` : task.note}</span></div><div className="result-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索候选人或文件名" /></div></header>
        <div className="result-status-tabs">{["全部", "处理中", "成功", "部分成功", "失败"].map((item) => <button key={item} type="button" className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item}<span>{counts[item]}</span></button>)}</div>

        {task.serverBacked && selected.length > 0 && <div className="bulk-action-bar"><strong>已选择 {selected.length} 项</strong><button type="button" disabled={bulkSubmitting} onClick={advanceToReview}><UserRoundCheck size={15} />{bulkSubmitting ? "推进中" : "推进到待复核"}</button><button type="button" disabled={bulkSubmitting} aria-label="清除选择" onClick={() => setSelected([])}><X size={16} /></button></div>}
        {undoAction.visible && <div className="bulk-action-bar"><strong>本次批量推进可立即撤销</strong><button type="button" disabled={undoAction.disabled} onClick={undoBulkAdvance}><RotateCcw size={15} />{undoAction.label}</button></div>}
        {bulkError && <div className="task-poll-error" role="alert"><CircleAlert size={17} /><span>{bulkError}</span></div>}

        <div className="screening-table">
          <div className="screening-table-head"><label><input type="checkbox" disabled={bulkSubmitting || selectableIds.length === 0} aria-label="选择全部可推进结果" checked={allSelected} onChange={() => setSelected(allSelected ? selected.filter((id) => !selectableIds.includes(id)) : [...new Set([...selected, ...selectableIds])])} /></label><span>候选人 / 文件</span><span>状态</span><span>建议</span><span>规则分</span><span>LLM 分</span><span>命中 / 缺失</span><span>风险与操作</span></div>
          {filtered.map((file) => <div className="screening-row" key={file.id}>
            <label><input type="checkbox" disabled={bulkSubmitting || !isAdvanceSelectable(file, task.serverBacked)} aria-label={`选择 ${file.candidate || file.name}`} checked={selected.includes(file.id)} onChange={() => setSelected((current) => current.includes(file.id) ? current.filter((id) => id !== file.id) : [...current, file.id])} /></label>
            <button className="screening-identity" type="button" disabled={!canOpenCandidateReview(file, task.serverBacked)} title={!canOpenCandidateReview(file, task.serverBacked) ? (task.serverBacked && !file.candidateId ? "服务端尚未生成候选人记录" : "处理成功后可查看候选人") : undefined} onClick={() => onOpenCandidate(task.serverBacked ? { serverBacked: true, ...candidateReviewContext(file, task) } : { name: file.candidate, role: task.position, company: "", age: "本批次", fileId: file.id, email: file.email, phone: file.phone, source: task.source, ruleScore: file.ruleScore, llmScore: file.llmScore, recommendation: file.recommendation, matched: file.matched, missing: file.missing, risk: file.risk }, { taskId: task.id, query, filter, selected })}><strong>{candidateDisplayName(file, task.serverBacked)}</strong><small>{file.name}</small></button>
            <span><span className={`file-state ${fileStatusClass(file.status)}`}>{file.status === "queued" && <Clock3 size={13} />}{file.status === "success" && <Check size={13} />}{file.status === "partial" && <CircleAlert size={13} />}{(file.status === "failed" || file.status === "cancelled") && <X size={13} />}{statusLabel(file.status)}</span></span>
            <span className="recommendation-cell">{file.status === "queued" ? "等待处理" : file.status === "cancelled" ? "未处理" : file.recommendation}</span>
            <span className="score-source"><strong>{file.status === "queued" ? "—" : (file.ruleScore ?? "—")}</strong><small>规则</small></span>
            <span className="score-source llm"><strong>{file.status === "queued" ? "—" : (file.llmScore ?? "—")}</strong><small>LLM</small></span>
            <span className="evidence-cell"><strong>{file.status === "queued" ? "等待处理" : (file.matched || "—")}</strong><small>缺失：{file.status === "queued" ? "—" : (file.missing || "—")}</small></span>
            <span className="risk-cell"><strong>{file.status === "queued" ? "等待处理" : task.serverBacked ? serverIssueMessage(file) : (file.error || file.risk || "—")}</strong>{!task.serverBacked && file.traceId && <small>追踪 ID：{file.traceId}</small>}{file.status === "failed" && (!task.serverBacked || file.retryable) && <button type="button" disabled={retryingIds.includes(file.id)} onClick={() => retry(file.id, "parse")}><RotateCcw size={14} />{retryingIds.includes(file.id) ? "重试中" : "重新解析"}</button>}{file.status === "partial" && (!task.serverBacked || file.llmRetryable) && <button type="button" disabled={retryingIds.includes(file.id)} onClick={() => retry(file.id, "llm")}><Redo2 size={14} />{retryingIds.includes(file.id) ? "重试中" : "重试 LLM"}</button>}</span>
          </div>)}
        </div>
      </section>

    </div>
  );
}
