import { useMemo, useState } from "react";
import {
  BriefcaseBusiness,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Clock3,
  FileText,
  Filter,
  Home,
  Import,
  LayoutList,
  Menu,
  MoreHorizontal,
  Plus,
  Search,
  Settings,
  SlidersHorizontal,
  Users,
  UserRound,
  UserRoundSearch,
  X,
} from "lucide-react";

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

function IconButton({ label, children, className = "", onClick }) {
  return (
    <button className={`icon-button ${className}`} type="button" title={label} aria-label={label} onClick={onClick}>
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

export function App() {
  const [activeNav, setActiveNav] = useState("工作台");
  const [activeJob, setActiveJob] = useState("AI 工程师");
  const [menuOpen, setMenuOpen] = useState(false);
  const [view, setView] = useState("board");
  const [modal, setModal] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [toast, setToast] = useState("");
  const [filterOnlyUrgent, setFilterOnlyUrgent] = useState(false);
  const [importState, setImportState] = useState("idle");
  const [newJobName, setNewJobName] = useState("");
  const [jobs, setJobs] = useState(Object.keys(jobData));

  const stages = useMemo(() => jobData[activeJob]?.stages || jobData["AI 工程师"].stages, [activeJob]);

  function notify(message) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  }

  function completeImport() {
    setImportState("loading");
    window.setTimeout(() => setImportState("done"), 900);
  }

  function createJob() {
    const name = newJobName.trim();
    if (!name) return;
    setJobs((current) => [...current, name]);
    setActiveJob(name);
    setNewJobName("");
    setModal(null);
    notify("职位已创建");
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand">招聘协同平台</div>
        <nav aria-label="主导航">
          {navItems.map(([label, Icon]) => (
            <button
              key={label}
              type="button"
              className={activeNav === label ? "nav-item active" : "nav-item"}
              onClick={() => { setActiveNav(label); setMenuOpen(false); if (label !== "工作台") notify(`${label}模块将在后续原型中展开`); }}
            >
              <Icon size={19} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="profile">
          <span className="profile-avatar"><UserRound size={20} /></span>
          <div><strong>张小北</strong><span>HR 招聘专员</span></div>
          <ChevronDown size={17} />
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <IconButton label="打开菜单" className="mobile-menu" onClick={() => setMenuOpen((value) => !value)}><Menu size={21} /></IconButton>
          <h1>{activeNav}</h1>
          <div className="top-actions">
            <button className="button primary" type="button" onClick={() => { setModal("import"); setImportState("idle"); }}><Import size={17} />导入简历</button>
            <button className="button secondary" type="button" onClick={() => setModal("job")}><Plus size={17} />新建职位</button>
          </div>
        </header>

        <div className="page-body">
          <section className="main-column">
            <div className="job-switcher">
              <span className="switcher-label">当前职位</span>
              <div className="job-tabs">
                {jobs.slice(0, 3).map((job) => (
                  <button key={job} type="button" className={activeJob === job ? "job-tab selected" : "job-tab"} onClick={() => setActiveJob(job)}>
                    <strong>{job}</strong><span>{jobData[job]?.count || 0} 人进行中</span>
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
                  {stageMeta.map(([name, count], index) => (
                    <section className="stage" key={name}>
                      <header><strong>{name}</strong><span>{filterOnlyUrgent ? Math.min(count, 3) : count}</span></header>
                      <div className="stage-list">
                        {stages[index].slice(0, filterOnlyUrgent ? 2 : 5).map((candidate) => (
                          <CandidateCard key={candidate.name} candidate={candidate} onOpen={setSelectedCandidate} />
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
                    <button type="button" className="list-row" key={candidate.name} onClick={() => setSelectedCandidate(candidate)}>
                      <span><span className="avatar-mini"><UserRound size={11} /></span><strong>{candidate.name}</strong></span>
                      <span>{stageMeta.find((_, stageIndex) => stages[stageIndex].includes(candidate))?.[0]}</span>
                      <span>{candidate.age || candidate.schedule || candidate.note}</span>
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </div>
              )}

              <div className="duplicate-alert">
                <CircleAlert size={19} />
                <div><strong>发现重复候选人</strong><span>系统检测到 2 组重复候选人，建议合并以避免重复跟进。</span></div>
                <button className="button small secondary" type="button" onClick={() => setModal("duplicates")}>去处理（2）</button>
                <IconButton label="忽略提醒" onClick={() => notify("本次提醒已忽略")}><X size={17} /></IconButton>
              </div>
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
                <div className="rail-group-title"><span className="status-dot orange" />待安排面试（4）<button type="button" onClick={() => notify("已筛选待安排面试")}>查看全部</button></div>
                {["候 D1  等待安排 1 天", "候 D2  等待安排 2 天", "候 D3  等待安排 2 天"].map((item) => <button className="rail-item" type="button" key={item} onClick={() => notify("已打开面试安排")}>{item}<small>AI 工程师 · 北京</small></button>)}
              </div>
              <div className="rail-group compact">
                <div className="rail-group-title"><span className="status-dot blue" />待反馈面试（3）<button type="button" onClick={() => notify("已筛选待反馈面试")}>查看全部</button></div>
                <p>候 E4　07-10 二面</p><p>候 E5　07-10 一面</p><p>候 E6　07-09 三面</p>
              </div>
            </section>

            <section className="rail-section calendar-card">
              <header><h3>面试日历（未来 7 天）</h3><button type="button" onClick={() => notify("日历模块将在后续原型展开")}>查看日历</button></header>
              {["07-11（今天）", "07-12（明天）", "07-13（周一）", "07-14（周二）"].map((day, index) => <button type="button" className="calendar-row" key={day}><span>{day}</span><strong>{[3, 5, 6, 4][index]} 场</strong></button>)}
              <button className="more-calendar" type="button">更多<MoreHorizontal size={15} /></button>
            </section>
          </aside>
        </div>
      </main>

      {selectedCandidate && (
        <aside className="detail-drawer" aria-label="候选人详情">
          <header><div><span className="profile-avatar"><UserRound size={20} /></span><div><h2>{selectedCandidate.name}</h2><p>{selectedCandidate.role}</p></div></div><IconButton label="关闭" onClick={() => setSelectedCandidate(null)}><X size={20} /></IconButton></header>
          <div className="drawer-body">
            <section><h3>候选人概览</h3><dl><div><dt>最近公司</dt><dd>{selectedCandidate.company || "暂无"}</dd></div><div><dt>应聘职位</dt><dd>{activeJob}</dd></div><div><dt>当前阶段</dt><dd>待复核</dd></div></dl></section>
            <section><h3>AI 简历评估</h3><div className="score-row"><strong>82</strong><span>匹配度较高<br />建议进入沟通阶段</span></div><p>具备算法与模型应用经验，核心技能与岗位要求基本匹配。建议重点确认项目深度与到岗时间。</p></section>
            <section><h3>最近动态</h3><p className="timeline"><Clock3 size={15} />今天 10:28　系统完成简历解析</p><p className="timeline"><Check size={15} />今天 10:30　AI 初筛通过</p></section>
          </div>
          <footer><button className="button secondary" type="button" onClick={() => notify("已加入人才库")}>加入人才库</button><button className="button primary" type="button" onClick={() => { setSelectedCandidate(null); notify("候选人已推进至待沟通"); }}>推进到待沟通</button></footer>
        </aside>
      )}

      {modal === "import" && (
        <Modal title="导入简历" onClose={() => setModal(null)} footer={<><button className="button secondary" type="button" onClick={() => setModal(null)}>取消</button><button className="button primary" type="button" onClick={completeImport} disabled={importState === "loading"}>{importState === "loading" ? "解析中..." : "开始导入"}</button></>}>
          <label className="form-label">导入到职位<select value={activeJob} onChange={(event) => setActiveJob(event.target.value)}>{jobs.map((job) => <option key={job}>{job}</option>)}</select></label>
          <button className="dropzone" type="button" onClick={() => setImportState("ready")}><Import size={27} /><strong>{importState === "ready" ? "已选择 5 份简历" : "选择或拖入简历文件"}</strong><span>支持 PDF、DOCX，单次最多 100 份</span></button>
          {importState === "loading" && <div className="progress"><span /></div>}
          {importState === "done" && <p className="success-message"><Check size={17} />5 份简历已导入，正在进行 AI 初筛</p>}
        </Modal>
      )}

      {modal === "job" && (
        <Modal title="新建职位" onClose={() => setModal(null)} footer={<><button className="button secondary" type="button" onClick={() => setModal(null)}>取消</button><button className="button primary" type="button" onClick={createJob}>创建职位</button></>}>
          <label className="form-label">职位名称<input value={newJobName} onChange={(event) => setNewJobName(event.target.value)} placeholder="例如：前端工程师" autoFocus /></label>
          <div className="form-grid"><label className="form-label">工作地点<select><option>北京</option><option>上海</option><option>深圳</option></select></label><label className="form-label">所属部门<select><option>技术部</option><option>产品部</option></select></label></div>
          <label className="form-label">职位描述<textarea rows="5" placeholder="粘贴 JD，后续可用于 AI 简历筛选" /></label>
        </Modal>
      )}

      {modal === "duplicates" && (
        <Modal title="处理重复候选人" onClose={() => setModal(null)} footer={<><button className="button secondary" type="button" onClick={() => setModal(null)}>暂不处理</button><button className="button primary" type="button" onClick={() => { setModal(null); notify("2 组候选人已合并"); }}>确认合并</button></>}>
          <p className="modal-intro">系统根据手机号、邮箱和履历相似度发现以下重复记录。</p>
          {["候 A2 / 候 B2", "候 C1 / 候 D1"].map((pair) => <label className="duplicate-row" key={pair}><input type="checkbox" defaultChecked /><span className="profile-avatar"><UserRound size={18} /></span><div><strong>{pair}</strong><span>履历相似度 96%，建议保留最近更新记录</span></div><SlidersHorizontal size={17} /></label>)}
        </Modal>
      )}

      {menuOpen && <button className="mobile-scrim" type="button" aria-label="关闭菜单" onClick={() => setMenuOpen(false)} />}
      {toast && <div className="toast" role="status"><Check size={16} />{toast}</div>}
    </div>
  );
}
