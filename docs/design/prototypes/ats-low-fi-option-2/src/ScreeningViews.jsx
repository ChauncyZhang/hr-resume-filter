import { useEffect, useMemo, useState } from "react";
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
  Tag,
  Trash2,
  UserRoundCheck,
  Users,
  X,
} from "lucide-react";

const demoFiles = [
  { id: "f1", name: "AI工程师_李嘉明.pdf", size: "1.4 MB", type: "PDF", valid: true },
  { id: "f2", name: "算法工程师_王晨.docx", size: "860 KB", type: "DOCX", valid: true },
  { id: "f3", name: "大模型应用_赵宁.pdf", size: "1.1 MB", type: "PDF", valid: true },
  { id: "f4", name: "候选人简历_陈浩.pdf", size: "2.0 MB", type: "PDF", valid: true },
  { id: "f5", name: "算法实习生_孙悦.pdf", size: "720 KB", type: "PDF", valid: true },
  { id: "f6", name: "候选人作品集.zip", size: "8.6 MB", type: "ZIP", valid: false, error: "不支持 ZIP 文件，请仅上传 PDF、DOCX 或 TXT" },
];

const resultProfiles = [
  { candidate: "李嘉明", recommendation: "可沟通", ruleScore: 81, llmScore: 78, matched: "Python、LLM、RAG", missing: "Kubernetes", risk: "项目规模待确认" },
  { candidate: "王晨", recommendation: "人工复核", ruleScore: 74, llmScore: 72, matched: "Python、机器学习", missing: "Agent", risk: "大模型经验偏少" },
  { candidate: "赵宁", recommendation: "优先沟通", ruleScore: 88, llmScore: 84, matched: "LLM、RAG、Agent", missing: "无明显缺失", risk: "到岗时间待确认" },
  { candidate: "陈浩", recommendation: "待重试", ruleScore: null, llmScore: null, matched: "—", missing: "—", risk: "文件解析失败" },
  { candidate: "孙悦", recommendation: "人工复核", ruleScore: 66, llmScore: null, matched: "Python、深度学习", missing: "项目经验", risk: "LLM 评分失败" },
];

function statusLabel(status) {
  return {
    queued: "排队中",
    running: "处理中",
    success: "成功",
    partial: "部分成功",
    failed: "失败",
    complete: "已完成",
  }[status] || status;
}

function fileStatusClass(status) {
  return status === "success" ? "success" : status === "partial" ? "partial" : status === "failed" ? "failed" : "running";
}

export function ImportWizard({ activeJob, jobs, recentTask, onClose, onCreateTask, onResumeTask }) {
  const [step, setStep] = useState(1);
  const [position, setPosition] = useState(activeJob);
  const [source, setSource] = useState("BOSS 直聘");
  const [note, setNote] = useState("7 月 AI 工程师主动搜寻批次");
  const [files, setFiles] = useState([]);
  const [llmEnabled, setLlmEnabled] = useState(true);
  const [error, setError] = useState("");

  const validFiles = files.filter((file) => file.valid);
  const invalidFiles = files.filter((file) => !file.valid);

  function next() {
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
    setError("");
    setStep((current) => Math.min(3, current + 1));
  }

  function createTask() {
    const now = new Date();
    const task = {
      id: `SCR-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}-${String(now.getTime()).slice(-4)}`,
      position,
      source,
      note,
      llmEnabled,
      creator: "张小北",
      createdAt: "刚刚",
      status: "running",
      stage: "解析中",
      completed: 0,
      elapsed: 0,
      files: validFiles.map((file, index) => ({ ...file, ...resultProfiles[index], status: "queued", traceId: null })),
    };
    onCreateTask(task);
  }

  return (
    <div className="screening-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="screening-modal" role="dialog" aria-modal="true" aria-label="导入并筛选简历" onMouseDown={(event) => event.stopPropagation()}>
        <header className="screening-modal-header">
          <div><h2>导入并筛选简历</h2><p>为职位创建一次可跟踪、可恢复的筛选任务。</p></div>
          <button className="icon-button" type="button" aria-label="关闭" onClick={onClose}><X size={20} /></button>
        </header>

        <div className="wizard-steps" aria-label="导入步骤">
          {["批次信息", "文件校验", "确认创建"].map((label, index) => <div key={label} className={step === index + 1 ? "active" : step > index + 1 ? "done" : ""}><span>{step > index + 1 ? <Check size={14} /> : index + 1}</span><strong>{label}</strong>{index < 2 && <i />}</div>)}
        </div>

        <div className="screening-modal-body">
          {step === 1 && <div className="wizard-section">
            {recentTask && <button className="recent-task-banner" type="button" onClick={() => onResumeTask(recentTask)}><Clock3 size={18} /><span><strong>继续最近的筛选任务</strong><small>{recentTask.id} · {recentTask.position} · {recentTask.completed}/{recentTask.files.length} 已完成</small></span><ChevronRight size={17} /></button>}
            <div className="wizard-grid">
              <label>目标职位<select value={position} onChange={(event) => setPosition(event.target.value)}>{jobs.map((job) => <option key={job}>{job}</option>)}</select></label>
              <label>简历来源<select value={source} onChange={(event) => setSource(event.target.value)}><option>BOSS 直聘</option><option>猎聘</option><option>智联招聘</option><option>员工内推</option><option>人才库重新激活</option><option>其他合法来源</option></select></label>
            </div>
            <label className="wizard-field">批次说明<textarea rows="4" value={note} onChange={(event) => setNote(event.target.value)} placeholder="例如：7 月 AI 工程师主动搜寻批次" /></label>
            <div className="privacy-note"><CircleAlert size={17} /><span>请确认简历来源合法并符合公司隐私政策。候选人数据仅用于本次招聘流程。</span></div>
          </div>}

          {step === 2 && <div className="wizard-section">
            {files.length === 0 ? <button className="wizard-dropzone" type="button" onClick={() => setFiles(demoFiles)}><Import size={28} /><strong>选择演示简历</strong><span>模拟选择 PDF、DOCX 和一个不支持的 ZIP 文件</span></button> : <>
              <div className="file-summary"><span><strong>{validFiles.length}</strong> 份有效简历</span><span>总大小 6.1 MB</span><span className={invalidFiles.length ? "has-error" : "is-valid"}>{invalidFiles.length ? `${invalidFiles.length} 个文件需处理` : "全部文件可导入"}</span><button type="button" onClick={() => setFiles(demoFiles)}><Plus size={15} />重新选择</button></div>
              <div className="import-file-list">{files.map((file) => <div className={file.valid ? "" : "invalid"} key={file.id}><span className="file-icon">{file.valid ? <FileText size={18} /> : <FileArchive size={18} />}</span><span><strong>{file.name}</strong><small>{file.type} · {file.size}{file.error ? ` · ${file.error}` : ""}</small></span><span className={file.valid ? "valid-label" : "invalid-label"}>{file.valid ? "可导入" : "不支持"}</span><button type="button" aria-label={`移除 ${file.name}`} onClick={() => setFiles((current) => current.filter((item) => item.id !== file.id))}><Trash2 size={16} /></button></div>)}</div>
            </>}
          </div>}

          {step === 3 && <div className="wizard-section confirmation-section">
            <div className="confirmation-summary">
              <h3>任务摘要</h3>
              <dl><div><dt>目标职位</dt><dd>{position}</dd></div><div><dt>简历来源</dt><dd>{source}</dd></div><div><dt>批次说明</dt><dd>{note || "未填写"}</dd></div><div><dt>有效文件</dt><dd>{validFiles.length} 份 · 6.1 MB</dd></div></dl>
            </div>
            <div className="screening-options">
              <label><span><FileText size={18} /><span><strong>规则评分</strong><small>根据职位必须条件、加分项和风险规则评分</small></span></span><input type="checkbox" checked readOnly /></label>
              <label><span><Bot size={18} /><span><strong>LLM 语义评估</strong><small>分别展示 LLM 分数和理由，不覆盖规则结果</small></span></span><input type="checkbox" checked={llmEnabled} onChange={(event) => setLlmEnabled(event.target.checked)} /></label>
            </div>
            <p className="background-task-note"><Clock3 size={16} />创建后可离开页面，任务会在后台继续；再次进入可通过任务 ID 恢复进度。</p>
          </div>}
          {error && <p className="wizard-error"><CircleAlert size={15} />{error}</p>}
        </div>

        <footer className="screening-modal-footer">
          <button className="button secondary" type="button" onClick={step === 1 ? onClose : () => setStep((current) => current - 1)}>{step === 1 ? "取消" : "上一步"}</button>
          {step < 3 ? <button className="button primary" type="button" onClick={next}>下一步</button> : <button className="button primary" type="button" onClick={createTask}><Import size={16} />创建筛选任务</button>}
        </footer>
      </section>
    </div>
  );
}

export function ScreeningTaskView({ task: initialTask, onTaskChange, onBack, onOpenCandidate, onNotify }) {
  const [task, setTask] = useState(initialTask);
  const [filter, setFilter] = useState("全部");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState([]);
  const [undo, setUndo] = useState(null);

  useEffect(() => {
    onTaskChange(task);
    window.localStorage.setItem("ats_recent_screening_task", JSON.stringify(task));
  }, [onTaskChange, task]);

  useEffect(() => {
    if (task.status !== "running") return undefined;
    const timer = window.setTimeout(() => {
      setTask((current) => {
        const index = current.completed;
        if (index >= current.files.length) return current;
        const files = current.files.map((file, fileIndex) => {
          if (fileIndex !== index) return file;
          if (index === 3) return { ...file, status: "failed", recommendation: "待重试", traceId: "TR-PARSE-4081", error: "PDF 文本层损坏，未能提取有效内容" };
          if (index === 4 && current.llmEnabled) return { ...file, status: "partial", traceId: "TR-LLM-4297", error: "LLM 请求额度暂时不可用，已保留规则评分" };
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

  const currentFile = task.files[task.completed]?.name || "全部文件已处理";
  const selectableIds = filtered.filter((file) => file.status === "success" || file.status === "partial").map((file) => file.id);
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => selected.includes(id));

  function retry(id, kind) {
    setTask((current) => {
      const files = current.files.map((file) => file.id === id ? { ...file, status: "success", traceId: null, error: null, ruleScore: file.ruleScore ?? 71, llmScore: kind === "llm" ? 69 : (file.llmScore ?? 68), recommendation: "人工复核" } : file);
      return { ...current, files, status: files.some((file) => file.status === "failed" || file.status === "partial") ? "partial" : "complete" };
    });
    onNotify(kind === "llm" ? "LLM 评分重试成功" : "文件重新解析成功");
  }

  function bulkAction(label) {
    if (selected.length === 0) {
      onNotify("请先选择已完成的候选人");
      return;
    }
    setUndo({ label, count: selected.length });
    setSelected([]);
    onNotify(`已对 ${selected.length} 位候选人执行“${label}”`);
    window.setTimeout(() => setUndo(null), 6000);
  }

  return (
    <div className="screening-task-page">
      <button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />返回来源页面</button>
      <section className="task-overview">
        <div className="task-title-row"><span className={`task-state-icon ${task.status}`} >{task.status === "running" ? <LoaderCircle size={21} /> : task.status === "complete" ? <CircleCheck size={21} /> : <CircleAlert size={21} />}</span><div><div><h2>{task.position} · 简历筛选任务</h2><span className={`task-status ${fileStatusClass(task.status)}`}>{statusLabel(task.status)}</span></div><p>{task.id} · {task.source} · 发起人 {task.creator} · {task.createdAt}</p></div></div>
        <button className="button secondary" type="button" onClick={() => onNotify("筛选结果导出任务已创建")}><Download size={16} />导出结果</button>
      </section>

      <section className="task-progress-panel">
        <div className="progress-primary"><div><span>处理进度</span><strong>{task.completed}/{task.files.length}</strong></div><div className="task-progress-track"><span style={{ width: `${(task.completed / task.files.length) * 100}%` }} /></div><p>{task.status === "running" ? `正在处理：${currentFile}` : `处理完成：${task.completed}/${task.files.length} 份简历`}<span>当前阶段：{task.stage}</span></p></div>
        <div className="progress-stats"><div><strong>{counts.成功}</strong><span>成功</span></div><div><strong>{counts.部分成功}</strong><span>部分成功</span></div><div><strong>{counts.失败}</strong><span>失败</span></div><div><strong>{task.elapsed}s</strong><span>已耗时</span></div></div>
      </section>

      {task.status === "running" && <p className="task-background-tip"><Clock3 size={15} />任务正在后台处理，可以安全离开此页面；稍后通过任务 ID 恢复。</p>}
      {(counts.失败 > 0 || counts.部分成功 > 0) && task.status !== "running" && <div className="partial-warning"><CircleAlert size={18} /><div><strong>部分文件需要处理</strong><span>单文件失败没有影响其他简历。可在对应行查看原因并单独重试。</span></div></div>}

      <section className="task-results-panel">
        <header className="results-header"><div><h3>逐文件结果</h3><span>{task.note}</span></div><div className="result-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索候选人或文件名" /></div></header>
        <div className="result-status-tabs">{["全部", "处理中", "成功", "部分成功", "失败"].map((item) => <button key={item} type="button" className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item}<span>{counts[item]}</span></button>)}</div>

        {selected.length > 0 && <div className="bulk-action-bar"><strong>已选择 {selected.length} 项</strong><button type="button" onClick={() => bulkAction("推进到待复核")}><UserRoundCheck size={15} />推进到待复核</button><button type="button" onClick={() => bulkAction("标记淘汰")}><Trash2 size={15} />淘汰</button><button type="button" onClick={() => bulkAction("添加标签")}><Tag size={15} />加标签</button><button type="button" onClick={() => bulkAction("加入人才库")}><Users size={15} />加入人才库</button><button type="button" aria-label="清除选择" onClick={() => setSelected([])}><X size={16} /></button></div>}

        <div className="screening-table">
          <div className="screening-table-head"><label><input type="checkbox" checked={allSelected} onChange={() => setSelected(allSelected ? selected.filter((id) => !selectableIds.includes(id)) : [...new Set([...selected, ...selectableIds])])} /></label><span>候选人 / 文件</span><span>状态</span><span>建议</span><span>规则分</span><span>LLM 分</span><span>命中 / 缺失</span><span>风险与操作</span></div>
          {filtered.map((file) => <div className="screening-row" key={file.id}>
            <label><input type="checkbox" disabled={!['success','partial'].includes(file.status)} checked={selected.includes(file.id)} onChange={() => setSelected((current) => current.includes(file.id) ? current.filter((id) => id !== file.id) : [...current, file.id])} /></label>
            <button className="screening-identity" type="button" onClick={() => onOpenCandidate({ name: file.candidate, role: task.position, company: "", age: "本批次" })}><strong>{file.candidate}</strong><small>{file.name}</small></button>
            <span><span className={`file-state ${fileStatusClass(file.status)}`}>{file.status === "queued" && <Clock3 size={13} />}{file.status === "success" && <Check size={13} />}{file.status === "partial" && <CircleAlert size={13} />}{file.status === "failed" && <X size={13} />}{statusLabel(file.status)}</span></span>
            <span className="recommendation-cell">{file.status === "queued" ? "等待处理" : file.recommendation}</span>
            <span className="score-source"><strong>{file.status === "queued" ? "—" : (file.ruleScore ?? "—")}</strong><small>规则</small></span>
            <span className="score-source llm"><strong>{file.status === "queued" ? "—" : (file.llmScore ?? "—")}</strong><small>LLM</small></span>
            <span className="evidence-cell"><strong>{file.status === "queued" ? "等待处理" : (file.matched || "—")}</strong><small>缺失：{file.status === "queued" ? "—" : (file.missing || "—")}</small></span>
            <span className="risk-cell"><strong>{file.status === "queued" ? "等待处理" : (file.error || file.risk || "—")}</strong>{file.traceId && <small>追踪 ID：{file.traceId}</small>}{file.status === "failed" && <button type="button" onClick={() => retry(file.id, "parse")}><RotateCcw size={14} />重新解析</button>}{file.status === "partial" && <button type="button" onClick={() => retry(file.id, "llm")}><Redo2 size={14} />重试 LLM</button>}</span>
          </div>)}
        </div>
      </section>

      {undo && <div className="undo-toast"><Check size={16} />已完成“{undo.label}”，影响 {undo.count} 人<button type="button" onClick={() => { setUndo(null); onNotify("已撤销上一步批量操作"); }}>撤销</button></div>}
    </div>
  );
}
