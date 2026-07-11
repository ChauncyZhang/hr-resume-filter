import { useMemo, useState } from "react";
import {
  ArrowLeft,
  Bot,
  BriefcaseBusiness,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CirclePause,
  CirclePlay,
  Clock3,
  FileText,
  Filter,
  Import,
  ListFilter,
  MoreHorizontal,
  Pencil,
  Search,
  Settings,
  Sparkles,
  Users,
  X,
} from "lucide-react";

export const initialPositionRecords = [
  {
    id: "JOB-AI-001",
    name: "AI 工程师",
    department: "技术部",
    location: "北京",
    owner: "张小北",
    status: "招聘中",
    priority: "高",
    headcount: 3,
    candidates: 48,
    review: 8,
    interview: 5,
    decision: 3,
    updated: "今天 11:05",
    jd: "负责大模型应用、AI Agent、RAG 检索增强生成等 AI 应用的设计、开发和落地。",
    mustHave: ["Python", "机器学习", "深度学习", "LLM"],
    niceToHave: ["RAG", "Agent", "Docker", "Kubernetes"],
    process: "技术岗位标准流程",
  },
  {
    id: "JOB-JAVA-002",
    name: "Java 后端工程师",
    department: "技术部",
    location: "上海",
    owner: "陈雨",
    status: "招聘中",
    priority: "中",
    headcount: 2,
    candidates: 32,
    review: 6,
    interview: 4,
    decision: 1,
    updated: "今天 09:42",
    jd: "负责核心业务服务的设计与开发，建设稳定、可观测的微服务体系。",
    mustHave: ["Java", "Spring Boot", "MySQL", "Redis"],
    niceToHave: ["Kafka", "Kubernetes", "高并发"],
    process: "技术岗位标准流程",
  },
  {
    id: "JOB-PM-003",
    name: "产品经理",
    department: "产品部",
    location: "北京",
    owner: "张小北",
    status: "招聘中",
    priority: "中",
    headcount: 1,
    candidates: 21,
    review: 4,
    interview: 2,
    decision: 1,
    updated: "昨天 18:20",
    jd: "负责企业服务产品的需求分析、方案设计、项目推进和效果复盘。",
    mustHave: ["B 端产品", "需求分析", "项目管理"],
    niceToHave: ["招聘行业", "数据分析", "AI 产品"],
    process: "产品岗位标准流程",
  },
  {
    id: "JOB-FE-004",
    name: "前端工程师",
    department: "技术部",
    location: "深圳",
    owner: "刘思远",
    status: "草稿",
    priority: "低",
    headcount: 2,
    candidates: 0,
    review: 0,
    interview: 0,
    decision: 0,
    updated: "07-10 16:30",
    jd: "负责招聘协同平台 Web 端开发与体验优化。",
    mustHave: ["React", "TypeScript", "CSS"],
    niceToHave: ["数据可视化", "设计系统"],
    process: "技术岗位标准流程",
  },
  {
    id: "JOB-OPS-005",
    name: "招聘运营专员",
    department: "人力资源部",
    location: "北京",
    owner: "王敏",
    status: "已暂停",
    priority: "低",
    headcount: 1,
    candidates: 15,
    review: 2,
    interview: 0,
    decision: 0,
    updated: "07-09 14:10",
    jd: "负责招聘渠道运营、数据分析和候选人体验提升。",
    mustHave: ["招聘运营", "数据分析"],
    niceToHave: ["ATS 使用经验", "雇主品牌"],
    process: "职能岗位标准流程",
  },
];

const stageCounts = [
  ["新简历", 22],
  ["待复核", 8],
  ["待沟通", 6],
  ["待安排", 4],
  ["面试中", 5],
  ["待决策", 3],
];

const candidateRows = [
  ["候 A1", "AI 算法工程师 · 字节", "新简历", "81", "今天 10:28", "张小北"],
  ["候 B2", "AI 研究员 · 阿里", "待复核", "78", "今天 09:45", "张小北"],
  ["候 C1", "算法工程师 · 字节", "待沟通", "86", "昨天 16:30", "陈雨"],
  ["候 D2", "AI 工程师 · 阿里", "待安排", "75", "昨天 14:12", "张小北"],
  ["候 E1", "大模型应用工程师 · 腾讯", "面试中", "88", "07-10 18:05", "刘思远"],
];

const roleProfiles = {
  "Java 后端工程师": ["Java 开发工程师 · 美团", "后端工程师 · 京东", "资深 Java 工程师 · 快手", "服务端工程师 · 小米", "Java 架构师 · 携程"],
  产品经理: ["高级产品经理 · 京东", "B 端产品经理 · 用友", "平台产品经理 · 腾讯", "产品经理 · 美团", "AI 产品经理 · 百度"],
  前端工程师: ["React 工程师 · 字节", "前端开发工程师 · 腾讯", "Web 工程师 · 美团", "资深前端工程师 · 阿里", "前端架构师 · 小米"],
  招聘运营专员: ["招聘运营 · 小红书", "招聘专员 · 美团", "人才运营 · 字节", "招聘顾问 · 猎聘", "雇主品牌专员 · 百度"],
};

function candidatesFor(job) {
  if (job.name === "AI 工程师") return candidateRows;
  const profiles = roleProfiles[job.name] || candidateRows.map(() => `${job.name}候选人 · 示例公司`);
  return candidateRows.map((row, index) => [row[0], profiles[index], ...row.slice(2)]);
}

function StatusTag({ children }) {
  const className = children === "招聘中" ? "status-active" : children === "草稿" ? "status-draft" : "status-paused";
  return <span className={`job-status ${className}`}>{children}</span>;
}

function JobDialog({ onClose, onDiscard, onSave }) {
  return (
    <div className="job-confirm-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="job-confirm" role="dialog" aria-modal="true" aria-label="保存未完成的职位" onMouseDown={(event) => event.stopPropagation()}>
        <header><CircleAlert size={21} /><h3>职位尚未保存</h3></header>
        <p>你填写的内容还没有保存。可以先保存为草稿，或者放弃本次修改。</p>
        <footer>
          <button className="button secondary" type="button" onClick={onClose}>继续编辑</button>
          <button className="button danger-text" type="button" onClick={onDiscard}>放弃修改</button>
          <button className="button primary" type="button" onClick={onSave}>保存草稿</button>
        </footer>
      </section>
    </div>
  );
}

function JobList({ records, onOpen }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("全部");
  const [department, setDepartment] = useState("全部部门");
  const [owner, setOwner] = useState("全部负责人");

  const filtered = useMemo(() => records.filter((job) => {
    const matchesQuery = !query || `${job.name}${job.id}${job.department}`.toLowerCase().includes(query.toLowerCase());
    const matchesStatus = status === "全部" || job.status === status;
    const matchesDepartment = department === "全部部门" || job.department === department;
    const matchesOwner = owner === "全部负责人" || job.owner === owner;
    return matchesQuery && matchesStatus && matchesDepartment && matchesOwner;
  }), [department, owner, query, records, status]);

  return (
    <div className="job-page job-list-page">
      <div className="job-page-heading">
        <div><h2>职位管理</h2><p>统一维护招聘职位、负责人和候选人推进情况。</p></div>
      </div>

      <div className="job-status-tabs" role="tablist" aria-label="职位状态">
        {["全部", "招聘中", "草稿", "已暂停"].map((item) => (
          <button key={item} role="tab" aria-selected={status === item} type="button" className={status === item ? "active" : ""} onClick={() => setStatus(item)}>{item}<span>{item === "全部" ? records.length : records.filter((job) => job.status === item).length}</span></button>
        ))}
      </div>

      <section className="job-list-panel">
        <div className="job-filters">
          <label className="search-control"><Search size={17} /><input aria-label="搜索职位" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索职位名称或编号" /></label>
          <label className="select-control"><BriefcaseBusiness size={16} /><select aria-label="部门筛选" value={department} onChange={(event) => setDepartment(event.target.value)}><option>全部部门</option><option>技术部</option><option>产品部</option><option>人力资源部</option></select><ChevronDown size={14} /></label>
          <label className="select-control"><Users size={16} /><select aria-label="负责人筛选" value={owner} onChange={(event) => setOwner(event.target.value)}><option>全部负责人</option><option>张小北</option><option>陈雨</option><option>刘思远</option><option>王敏</option></select><ChevronDown size={14} /></label>
          <button className="button secondary compact" type="button" onClick={() => { setQuery(""); setStatus("全部"); setDepartment("全部部门"); setOwner("全部负责人"); }}><X size={15} />清空</button>
        </div>

        <div className="job-table" role="table" aria-label="职位列表">
          <div className="job-table-head" role="row">
            <span>职位</span><span>状态</span><span>负责人</span><span>招聘进度</span><span>候选人</span><span>更新时间</span><span>操作</span>
          </div>
          {filtered.map((job) => (
            <button className="job-table-row" role="row" type="button" key={job.id} onClick={() => onOpen(job)}>
              <span className="job-title-cell"><strong>{job.name}</strong><small>{job.id} · {job.department} · {job.location}</small></span>
              <span><StatusTag>{job.status}</StatusTag></span>
              <span className="owner-cell"><span>{job.owner.slice(0, 1)}</span>{job.owner}</span>
              <span className="progress-cell"><strong>{job.headcount} 人</strong><small>优先级：{job.priority}</small></span>
              <span className="candidate-count"><strong>{job.candidates}</strong><small>待复核 {job.review}</small></span>
              <span className="updated-cell">{job.updated}</span>
              <span className="row-actions"><span title="查看职位"><ChevronRight size={18} /></span><span title="更多操作"><MoreHorizontal size={18} /></span></span>
            </button>
          ))}
          {filtered.length === 0 && <div className="job-empty"><ListFilter size={25} /><strong>没有符合条件的职位</strong><span>调整搜索词或清空筛选条件后重试。</span></div>}
        </div>
      </section>
    </div>
  );
}

function JobForm({ initialJob, onBack, onSaveDraft, onPublish }) {
  const [values, setValues] = useState({
    name: initialJob?.name || "",
    department: initialJob?.department || "技术部",
    location: initialJob?.location || "北京",
    headcount: initialJob?.headcount || 1,
    owner: initialJob?.owner || "张小北",
    priority: initialJob?.priority || "中",
    jd: initialJob?.jd || "",
    mustHave: initialJob?.mustHave?.join("、") || "",
    niceToHave: initialJob?.niceToHave?.join("、") || "",
    process: initialJob?.process || "技术岗位标准流程",
    llmEnabled: true,
  });
  const [errors, setErrors] = useState({});
  const [dirty, setDirty] = useState(false);
  const [extractState, setExtractState] = useState("idle");
  const [confirmExit, setConfirmExit] = useState(false);

  function change(field, value) {
    setValues((current) => ({ ...current, [field]: value }));
    setDirty(true);
    setErrors((current) => ({ ...current, [field]: "" }));
  }

  function validate() {
    const next = {};
    if (!values.name.trim()) next.name = "请输入职位名称";
    if (!values.jd.trim()) next.jd = "请输入公开职位描述";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function leave() {
    if (dirty) setConfirmExit(true);
    else onBack();
  }

  function extract() {
    if (!values.jd.trim()) {
      setErrors((current) => ({ ...current, jd: "请先填写 JD，再提取筛选条件" }));
      return;
    }
    setExtractState("loading");
    window.setTimeout(() => {
      setExtractState("done");
      const dataRole = values.jd.includes("数据");
      if (!values.mustHave) change("mustHave", dataRole ? "SQL、Python、数据建模、ETL" : "Python、机器学习、深度学习、LLM");
      if (!values.niceToHave) change("niceToHave", dataRole ? "Flink、Spark、数据治理、云平台" : "RAG、Agent、Docker、Kubernetes");
    }, 800);
  }

  function submit(publish) {
    if (publish && !validate()) return;
    const record = {
      ...initialJob,
      id: initialJob?.id || `JOB-${Date.now().toString().slice(-5)}`,
      ...values,
      status: publish ? "招聘中" : "草稿",
      candidates: initialJob?.candidates || 0,
      review: initialJob?.review || 0,
      interview: initialJob?.interview || 0,
      decision: initialJob?.decision || 0,
      updated: "刚刚",
      mustHave: values.mustHave.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
      niceToHave: values.niceToHave.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
    };
    setDirty(false);
    if (publish) onPublish(record);
    else onSaveDraft(record);
  }

  const completion = [values.name, values.department, values.jd, values.mustHave, values.process].filter(Boolean).length;

  return (
    <div className="job-page job-form-page">
      <button className="back-link" type="button" onClick={leave}><ArrowLeft size={17} />返回职位列表</button>
      <div className="job-page-heading form-heading">
        <div><h2>{initialJob ? "编辑职位" : "新建职位"}</h2><p>填写职位信息和筛选标准，发布后即可导入并筛选简历。</p></div>
        <div><button className="button secondary" type="button" onClick={() => submit(false)}>保存草稿</button><button className="button primary" type="button" onClick={() => submit(true)}>{initialJob ? "保存修改" : "发布职位"}</button></div>
      </div>

      <div className="job-form-layout">
        <div className="job-form-sections">
          <section className="form-section">
            <header><span>1</span><div><h3>基本信息</h3><p>设置职位归属、招聘目标和负责人。</p></div></header>
            <div className="job-fields two-columns">
              <label>职位名称<input value={values.name} onChange={(event) => change("name", event.target.value)} placeholder="例如：AI 工程师" />{errors.name && <small className="field-error">{errors.name}</small>}</label>
              <label>所属部门<select value={values.department} onChange={(event) => change("department", event.target.value)}><option>技术部</option><option>产品部</option><option>人力资源部</option></select></label>
              <label>工作地点<select value={values.location} onChange={(event) => change("location", event.target.value)}><option>北京</option><option>上海</option><option>深圳</option><option>远程</option></select></label>
              <label>招聘人数<input type="number" min="1" max="99" value={values.headcount} onChange={(event) => change("headcount", Number(event.target.value))} /></label>
              <label>负责人<select value={values.owner} onChange={(event) => change("owner", event.target.value)}><option>张小北</option><option>陈雨</option><option>刘思远</option><option>王敏</option></select></label>
              <label>优先级<div className="segmented-control">{["高", "中", "低"].map((item) => <button key={item} type="button" className={values.priority === item ? "active" : ""} onClick={() => change("priority", item)}>{item}</button>)}</div></label>
            </div>
          </section>

          <section className="form-section">
            <header><span>2</span><div><h3>职位描述与筛选标准</h3><p>JD 面向候选人展示，筛选标准仅供招聘团队使用。</p></div></header>
            <div className="job-fields">
              <label>公开 JD<textarea rows="8" value={values.jd} onChange={(event) => change("jd", event.target.value)} placeholder="粘贴或输入完整职位描述" />{errors.jd && <small className="field-error">{errors.jd}</small>}</label>
              <div className="extract-row"><button className="button secondary" type="button" onClick={extract} disabled={extractState === "loading"}><Sparkles size={16} />{extractState === "loading" ? "正在提取..." : "AI 提取筛选条件"}</button>{extractState === "done" && <span className="extract-success"><Check size={15} />已提取，可人工修改</span>}</div>
              <label>必须条件<textarea rows="3" value={values.mustHave} onChange={(event) => change("mustHave", event.target.value)} placeholder="用顿号分隔，例如：Python、机器学习" /></label>
              <label>加分项<textarea rows="3" value={values.niceToHave} onChange={(event) => change("niceToHave", event.target.value)} placeholder="用顿号分隔，例如：RAG、Agent" /></label>
            </div>
          </section>

          <section className="form-section">
            <header><span>3</span><div><h3>招聘流程与 AI</h3><p>选择候选人推进流程，并确认是否允许模型辅助评估。</p></div></header>
            <div className="job-fields">
              <label>流程模板<select value={values.process} onChange={(event) => change("process", event.target.value)}><option>技术岗位标准流程</option><option>产品岗位标准流程</option><option>职能岗位标准流程</option></select></label>
              <label className="toggle-row"><span><Bot size={18} /><span><strong>启用 LLM 简历评估</strong><small>继承组织模型设置，仅向服务商发送 JD 与简历正文。</small></span></span><input type="checkbox" checked={values.llmEnabled} onChange={(event) => change("llmEnabled", event.target.checked)} /></label>
            </div>
          </section>
        </div>

        <aside className="form-summary">
          <h3>发布检查</h3>
          <div className="completion-ring"><strong>{completion}/5</strong><span>关键项已完成</span></div>
          {[['职位名称', values.name], ['所属部门', values.department], ['公开 JD', values.jd], ['筛选条件', values.mustHave], ['招聘流程', values.process]].map(([label, value]) => <div className={value ? "check-row done" : "check-row"} key={label}>{value ? <Check size={15} /> : <Clock3 size={15} />}<span>{label}</span></div>)}
          <p>职位发布后仍可编辑，已进入流程的候选人不会被自动重置。</p>
        </aside>
      </div>

      {confirmExit && <JobDialog onClose={() => setConfirmExit(false)} onDiscard={onBack} onSave={() => submit(false)} />}
    </div>
  );
}

function JobDetail({ job, onBack, onEdit, onImport, onNotify, onOpenCandidate, onStatusChange }) {
  const [tab, setTab] = useState("候选人");
  const paused = job.status === "已暂停";
  const visibleStages = job.candidates > 0 ? stageCounts : stageCounts.map(([label]) => [label, 0]);
  const visibleCandidates = candidatesFor(job);

  return (
    <div className="job-page job-detail-page">
      <button className="back-link" type="button" onClick={onBack}><ArrowLeft size={17} />返回职位列表</button>
      <section className="job-detail-hero">
        <div className="job-detail-title"><span className="job-icon"><BriefcaseBusiness size={22} /></span><div><div><h2>{job.name}</h2><StatusTag>{job.status}</StatusTag></div><p>{job.id} · {job.department} · {job.location} · 负责人 {job.owner}</p></div></div>
        <div className="job-detail-actions">
          <button className="button secondary" type="button" onClick={onEdit}><Pencil size={16} />编辑职位</button>
          <button className="button secondary" type="button" onClick={() => { onStatusChange(paused ? "招聘中" : "已暂停"); onNotify(paused ? "职位已恢复招聘" : "职位已暂停招聘"); }}>{paused ? <CirclePlay size={16} /> : <CirclePause size={16} />}{paused ? "恢复招聘" : "暂停招聘"}</button>
          <button className="button primary" type="button" onClick={onImport}><Import size={16} />导入简历</button>
        </div>
      </section>

      <div className="job-metrics">
        {[['候选人总数', job.candidates, Users], ['待复核', job.review, FileText], ['面试中', job.interview, CalendarDays], ['待决策', job.decision, Clock3]].map(([label, value, Icon]) => <div key={label}><span><Icon size={18} /></span><div><strong>{value}</strong><small>{label}</small></div></div>)}
      </div>

      <section className="job-detail-panel">
        <div className="detail-tabs" role="tablist">
          {["候选人", "职位信息", "协作动态", "职位设置"].map((item) => <button key={item} role="tab" aria-selected={tab === item} type="button" className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}
        </div>

        {tab === "候选人" && <div className="detail-tab-content">
          <div className="funnel-strip">{visibleStages.map(([label, count], index) => <button type="button" key={label} onClick={() => onNotify(`已筛选${label}阶段`)}><span>{label}</span><strong>{count}</strong>{index < visibleStages.length - 1 && <ChevronRight size={15} />}</button>)}</div>
          <div className="candidate-toolbar"><label className="search-control"><Search size={16} /><input placeholder="搜索当前职位候选人" /></label><button className="button secondary compact" type="button" onClick={() => onNotify("已打开候选人筛选") }><Filter size={15} />筛选</button><button className="button secondary compact" type="button" onClick={() => onNotify("已进入批量操作模式") }><Check size={15} />批量操作</button></div>
          <div className="detail-candidate-table">
            <div className="detail-candidate-head"><span>候选人</span><span>当前阶段</span><span>匹配分</span><span>最近进展</span><span>负责人</span><span /></div>
            {job.candidates > 0 ? visibleCandidates.map(([name, role, stage, score, updated, owner]) => <button type="button" key={name} onClick={() => onOpenCandidate({ name, role, company: role.split(" · ")[1] || "", age: updated })}><span className="candidate-identity"><span>{name.slice(-1)}</span><span><strong>{name}</strong><small>{role}</small></span></span><span><span className="stage-pill">{stage}</span></span><span className="score-cell">{score}</span><span>{updated}</span><span>{owner}</span><ChevronRight size={16} /></button>) : <div className="detail-empty"><Users size={24} /><strong>尚无候选人</strong><span>导入简历后，候选人会出现在对应招聘阶段。</span><button className="button primary" type="button" onClick={onImport}><Import size={15} />导入简历</button></div>}
          </div>
        </div>}

        {tab === "职位信息" && <div className="detail-tab-content job-info-grid">
          <section><h3>公开职位描述</h3><p>{job.jd}</p></section>
          <section><h3>必须条件</h3><div className="skill-tags">{job.mustHave.map((item) => <span key={item}>{item}</span>)}</div><h3>加分项</h3><div className="skill-tags muted">{job.niceToHave.map((item) => <span key={item}>{item}</span>)}</div></section>
          <section><h3>招聘配置</h3><dl><div><dt>招聘人数</dt><dd>{job.headcount} 人</dd></div><div><dt>优先级</dt><dd>{job.priority}</dd></div><div><dt>流程模板</dt><dd>{job.process}</dd></div><div><dt>LLM 评估</dt><dd>已启用</dd></div></dl></section>
        </div>}

        {tab === "协作动态" && <div className="detail-tab-content activity-list">
          {[['今天 11:05', '张小北', '将候 E4 推进到二面'], ['今天 10:28', '系统', '完成 5 份简历解析与 AI 初筛'], ['昨天 16:30', '陈雨', '添加候 C1 的沟通备注'], ['07-10 14:12', '张小北', '更新职位必须条件']].map(([time, actor, action]) => <div key={`${time}-${action}`}><span className="activity-dot" /><div><strong>{actor}</strong><p>{action}</p><small>{time}</small></div></div>)}
        </div>}

        {tab === "职位设置" && <div className="detail-tab-content settings-summary">
          <section><div><Settings size={19} /><span><strong>职位可见范围</strong><small>招聘团队和技术部负责人可见</small></span></div><button type="button" onClick={onEdit}>编辑</button></section>
          <section><div><Bot size={19} /><span><strong>AI 简历评估</strong><small>使用组织默认模型，规则评分失败时仍保留人工复核</small></span></div><span className="enabled-label">已启用</span></section>
          <section><div><FileText size={19} /><span><strong>招聘流程</strong><small>{job.process}</small></span></div><button type="button" onClick={onEdit}>更换模板</button></section>
        </div>}
      </section>
    </div>
  );
}

export function JobsWorkspace({ mode, setMode, selectedJob, setSelectedJob, records, setRecords, onNotify, onImport, onOpenCandidate, onCreateJob }) {
  function upsert(record) {
    setRecords((current) => current.some((item) => item.id === record.id) ? current.map((item) => item.id === record.id ? record : item) : [record, ...current]);
    setSelectedJob(record);
    onCreateJob(record);
  }

  if (mode === "form") {
    return <JobForm initialJob={selectedJob?.formMode === "edit" ? selectedJob : null} onBack={() => { setSelectedJob(null); setMode("list"); }} onSaveDraft={(record) => { upsert(record); onNotify("职位已保存为草稿"); setMode("list"); }} onPublish={(record) => { upsert(record); onNotify(selectedJob?.formMode === "edit" ? "职位修改已保存" : "职位已发布"); setMode("detail"); }} />;
  }

  if (mode === "detail" && selectedJob) {
    return <JobDetail job={selectedJob} onBack={() => { setSelectedJob(null); setMode("list"); }} onEdit={() => { setSelectedJob((current) => ({ ...current, formMode: "edit" })); setMode("form"); }} onImport={onImport} onNotify={onNotify} onOpenCandidate={onOpenCandidate} onStatusChange={(status) => { const next = { ...selectedJob, status, formMode: undefined }; setSelectedJob(next); setRecords((current) => current.map((item) => item.id === next.id ? next : item)); }} />;
  }

  return <JobList records={records} onOpen={(job) => { setSelectedJob(job); setMode("detail"); }} />;
}
