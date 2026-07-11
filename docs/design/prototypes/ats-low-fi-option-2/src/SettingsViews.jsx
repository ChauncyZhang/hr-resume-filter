import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, Database, FileClock, KeyRound, LockKeyhole, Plus, RefreshCw, Search, ShieldCheck, SlidersHorizontal, Users, X } from "lucide-react";
import { getRoleCapabilities, isPermissionExpansion } from "./ux07Domain.js";

const settingsSections = [
  ["组织与权限", Users],
  ["流程与评价模板", SlidersHorizontal],
  ["AI 设置", Bot],
  ["审计与数据治理", FileClock],
];
const defaultAiForm = { enabled: true, provider: "OpenAI 兼容接口", model: "glm-5.2", baseUrl: "https://open.bigmodel.cn/api/paas/v4", scopes: ["AI 工程师"] };

const seedUsers = [
  { id: "U-001", name: "张小北", email: "zhang***@company.com", department: "技术部", role: "招聘管理员", status: "启用", scopes: ["AI 工程师", "Java 后端工程师", "产品经理"] },
  { id: "U-002", name: "陈雨", email: "chen***@company.com", department: "技术部", role: "HR", status: "启用", scopes: ["Java 后端工程师"] },
  { id: "U-003", name: "王磊", email: "wang***@company.com", department: "技术部", role: "面试官", status: "启用", scopes: ["AI 工程师"] },
  { id: "U-004", name: "刘思远", email: "liu***@company.com", department: "产品部", role: "HR", status: "停用", scopes: ["产品经理"] },
];

const auditRows = [
  { id: "AUD-1072", time: "今天 11:24", actor: "张小北", action: "下载简历", object: "李嘉明 · 当前简历", result: "成功", ip: "10.***.18.24", trace: "tr_8c21f7", change: "下载人才库候选人当前简历" },
  { id: "AUD-1071", time: "今天 10:58", actor: "陈雨", action: "状态变化", object: "陈浩 · Java 后端工程师", result: "成功", ip: "10.***.21.16", trace: "tr_67d12a", change: "待安排 → 面试中" },
  { id: "AUD-1070", time: "今天 10:32", actor: "张小北", action: "配置变更", object: "LLM 设置", result: "成功", ip: "10.***.18.24", trace: "tr_51aa93", change: "模型范围新增 AI 工程师" },
  { id: "AUD-1069", time: "昨天 17:46", actor: "系统", action: "登录", object: "王磊", result: "失败", ip: "103.***.44.8", trace: "tr_03bc18", change: "登录凭据校验失败" },
];

function RoleSwitch({ value, onChange }) {
  return <div className="role-switch" aria-label="当前角色">{["招聘管理员", "HR", "面试官"].map((role) => <button type="button" key={role} className={value === role ? "active" : ""} onClick={() => onChange(role)}>{role}</button>)}</div>;
}

function DangerDialog({ title, description, impact, confirmText, onCancel, onConfirm }) {
  return <div className="ux07-dialog-backdrop"><section className="ux07-dialog" role="dialog" aria-modal="true" aria-label={title}><header><div><h3>{title}</h3><p>{description}</p></div><button className="icon-button" type="button" aria-label="关闭" onClick={onCancel}><X size={19} /></button></header><div className="ux07-danger-impact"><AlertTriangle size={22} /><span>{impact}</span></div><footer><button className="button secondary" type="button" onClick={onCancel}>取消</button><button className="button danger" type="button" onClick={onConfirm}>{confirmText}</button></footer></section></div>;
}

function PermissionNotice({ children }) {
  return <div className="settings-permission-notice"><LockKeyhole size={18} /><span>{children}</span></div>;
}

function OrganizationSettings({ role, onNotify }) {
  const editable = getRoleCapabilities(role).settingsEdit;
  const [users, setUsers] = useState(seedUsers);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("全部角色");
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null);
  const [risk, setRisk] = useState(null);
  if (role === "面试官") return <section className="settings-denied"><LockKeyhole size={31} /><h3>无组织权限</h3><p>面试官不能查看公司成员、部门或职位可见范围。</p></section>;
  const visible = users.filter((user) => `${user.name}${user.email}${user.department}`.includes(query) && (roleFilter === "全部角色" || user.role === roleFilter) && (role === "招聘管理员" || user.name === "张小北"));
  function openUser(user) { setSelected(user); setDraft({ ...user, scopes: [...user.scopes] }); }
  function save() {
    if (isPermissionExpansion(selected.scopes, draft.scopes)) { setRisk("permission"); return; }
    setUsers((current) => current.map((item) => item.id === draft.id ? draft : item)); setSelected(null); onNotify("用户权限已保存并记录审计");
  }
  function commitExpanded() { setUsers((current) => current.map((item) => item.id === draft.id ? draft : item)); setRisk(null); setSelected(null); onNotify("权限范围已扩大并记录审计"); }
  return <div className="settings-section"><div className="settings-section-heading"><div><h2>组织与权限</h2><p>管理用户、角色、部门和职位可见范围。</p></div>{editable && <button className="button primary" type="button" onClick={() => onNotify("新建用户入口已打开")}><Plus size={16} />新增用户</button>}</div>{!editable && <PermissionNotice>HR 仅可查看本人权限，修改由招聘管理员完成。</PermissionNotice>}<div className="settings-toolbar"><label className="settings-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索用户或部门" /></label><label><select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}><option>全部角色</option><option>招聘管理员</option><option>HR</option><option>面试官</option></select><ChevronDown size={14} /></label></div><div className="settings-table users-table"><div className="settings-table-head"><span>用户</span><span>部门</span><span>角色</span><span>状态</span><span>职位范围</span><span /></div>{visible.map((user) => <button type="button" className="settings-table-row" key={user.id} onClick={() => openUser(user)}><span><strong>{user.name}</strong><small>{user.email}</small></span><span>{user.department}</span><span>{user.role}</span><span className={user.status === "启用" ? "status-ok" : "status-muted"}>{user.status}</span><span>{user.scopes.join("、")}</span><span>查看</span></button>)}</div><section className="department-strip"><div><strong>技术部</strong><span>负责人：赵强 · 6 人 · 3 个可见职位</span></div><div><strong>产品部</strong><span>负责人：孙敏 · 3 人 · 1 个可见职位</span></div></section>{selected && <aside className="settings-drawer" aria-label="编辑用户"><header><div><h2>{editable ? "编辑用户" : "查看权限"}</h2><p>{selected.name} · {selected.email}</p></div><button className="icon-button" type="button" aria-label="关闭" onClick={() => setSelected(null)}><X size={20} /></button></header><div className="settings-drawer-body"><label>部门<select disabled={!editable} value={draft.department} onChange={(event) => setDraft({ ...draft, department: event.target.value })}><option>技术部</option><option>产品部</option></select></label><label>角色<select disabled={!editable} value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value })}><option>招聘管理员</option><option>HR</option><option>面试官</option></select></label><label>状态<select disabled={!editable} value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option>启用</option><option>停用</option></select></label><fieldset disabled={!editable}><legend>职位可见范围</legend>{["AI 工程师", "Java 后端工程师", "产品经理"].map((scope) => <label key={scope}><input type="checkbox" checked={draft.scopes.includes(scope)} onChange={(event) => setDraft({ ...draft, scopes: event.target.checked ? [...draft.scopes, scope] : draft.scopes.filter((item) => item !== scope) })} />{scope}</label>)}</fieldset></div><footer><button className="button secondary" type="button" onClick={() => setSelected(null)}>关闭</button>{editable && <button className="button primary" type="button" onClick={save}>保存权限</button>}</footer></aside>}{risk === "permission" && <DangerDialog title="确认扩大职位权限" description={`将为 ${draft.name} 增加新的候选人可见范围。`} impact="保存后该用户可以查看新增职位下的候选人、面试和筛选信息，操作将进入权限审计。" confirmText="确认扩大权限" onCancel={() => setRisk(null)} onConfirm={commitExpanded} />}</div>;
}

function TemplateSettings({ role, onNotify }) {
  const editable = role === "招聘管理员";
  const [tab, setTab] = useState(role === "面试官" ? "面试评价模板" : "招聘流程");
  const [stages, setStages] = useState(["新简历", "待复核", "待沟通", "待安排", "面试中", "待决策", "已录用"]);
  const [draftName, setDraftName] = useState("标准社招流程");
  const [saveFailed, setSaveFailed] = useState(false);
  const tabs = role === "面试官" ? ["面试评价模板"] : ["招聘流程", "淘汰原因", "面试评价模板"];
  function saveTemplate() { if (!saveFailed) { setSaveFailed(true); return; } setSaveFailed(false); onNotify("模板草稿已保存"); }
  return <div className="settings-section"><div className="settings-section-heading"><div><h2>流程与评价模板</h2><p>管理招聘阶段、状态原因和结构化评价。</p></div></div>{!editable && <PermissionNotice>{role === "面试官" ? "你只能查看面试评价模板。" : "当前为只读模式，模板修改由招聘管理员完成。"}</PermissionNotice>}<div className="settings-tabs">{tabs.map((item) => <button type="button" key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}</div>{tab === "招聘流程" && <section className="template-editor"><header><div><input disabled={!editable} value={draftName} onChange={(event) => setDraftName(event.target.value)} /><span>适用职位：AI 工程师、Java 后端工程师</span></div>{editable && <button className="button primary" type="button" onClick={saveTemplate}>{saveFailed ? "重试保存" : "保存模板"}</button>}</header>{saveFailed && <div className="settings-error"><AlertTriangle size={18} /><span>保存失败，草稿已保留。网络恢复后可直接重试。</span></div>}<div className="stage-editor">{stages.map((stage, index) => <div key={`${stage}-${index}`}><span>{index + 1}</span><input disabled={!editable} value={stage} onChange={(event) => setStages(stages.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} /><small>{["新简历", "面试中"].includes(stage) ? "进行中申请正在使用，不可删除" : "可调整"}</small>{editable && <button type="button" disabled={["新简历", "面试中"].includes(stage)} onClick={() => setStages(stages.filter((_, itemIndex) => itemIndex !== index))}>删除</button>}</div>)}</div></section>}{tab === "淘汰原因" && <div className="reason-list">{[["岗位要求不匹配", "必填", "启用"], ["候选人主动放弃", "必填", "启用"], ["薪资预期不匹配", "可选", "启用"], ["暂不招聘", "可选", "停用"]].map((item) => <div key={item[0]}><strong>{item[0]}</strong><span>{item[1]}</span><span>{item[2]}</span>{editable && <button type="button">编辑</button>}</div>)}</div>}{tab === "面试评价模板" && <div className="evaluation-template"><header><div><strong>技术岗位结构化评价</strong><span>适用：技术一面、技术二面</span></div>{editable && <button className="button secondary" type="button">编辑模板</button>}</header>{["专业能力", "问题解决", "沟通协作", "岗位匹配"].map((item) => <div key={item}><span>{item}</span><small>必填 · 需提升 / 一般 / 良好 / 优秀</small></div>)}<footer>结论：强烈推荐、推荐、保留、不推荐</footer></div>}</div>;
}

function AiSettings({ role, onNotify, initialForm, onFormChange }) {
  const editable = role === "招聘管理员";
  const [form, setForm] = useState(initialForm ?? defaultAiForm);
  const [keyMode, setKeyMode] = useState(false);
  const [testState, setTestState] = useState("idle");
  const [risk, setRisk] = useState(false);
  useEffect(() => { onFormChange?.(form); }, [form, onFormChange]);
  if (role === "面试官") return <section className="settings-denied"><LockKeyhole size={31} /><h3>无 AI 设置权限</h3><p>面试官不能查看 Provider、模型范围或密钥状态。</p></section>;
  function toggleEnabled(checked) { if (checked && !form.enabled) { setRisk(true); return; } setForm({ ...form, enabled: checked }); }
  function testConnection() { setTestState("testing"); window.setTimeout(() => setTestState(form.baseUrl.includes("invalid") ? "error" : "success"), 450); }
  return <div className="settings-section ai-settings"><div className="settings-section-heading"><div><h2>AI 设置</h2><p>控制候选人文本是否发送到外部模型服务。</p></div></div>{!editable && <PermissionNotice>HR 仅可查看启用状态和岗位范围，不能查看或替换密钥。</PermissionNotice>}<section className="ai-governance"><ShieldCheck size={20} /><div><strong>数据外发控制</strong><p>启用后仅向已配置 Provider 发送 JD 与简历文本，不发送审计日志或账号凭据。</p></div><label><input type="checkbox" disabled={!editable} checked={form.enabled} onChange={(event) => toggleEnabled(event.target.checked)} />启用</label></section><div className="settings-form"><label>Provider<select disabled={!editable} value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })}><option>OpenAI 兼容接口</option><option>Azure OpenAI</option><option>企业内部模型</option></select></label><label>模型<input disabled={!editable} value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} /></label><label>Base URL<input disabled={!editable} value={form.baseUrl} onChange={(event) => { setForm({ ...form, baseUrl: event.target.value }); setTestState("idle"); }} /></label><label>API Key<div className="masked-key"><KeyRound size={16} /><span>{editable ? "••••••••••••••••••••••••" : "已配置"}</span>{editable && <button type="button" onClick={() => setKeyMode(!keyMode)}>{keyMode ? "取消替换" : "替换"}</button>}</div>{keyMode && <input type="password" placeholder="输入新的 API Key，保存后不再回显" />}</label><fieldset><legend>允许使用的岗位</legend>{["AI 工程师", "Java 后端工程师", "产品经理"].map((scope) => <label key={scope}><input type="checkbox" disabled={!editable} checked={form.scopes.includes(scope)} onChange={(event) => setForm({ ...form, scopes: event.target.checked ? [...form.scopes, scope] : form.scopes.filter((item) => item !== scope) })} />{scope}</label>)}</fieldset></div><div className={`llm-test-result ${testState}`}><div>{testState === "success" ? <CheckCircle2 size={20} /> : testState === "error" ? <AlertTriangle size={20} /> : <Bot size={20} />}<span><strong>{testState === "testing" ? "正在测试连接" : testState === "success" ? "连接成功" : testState === "error" ? "连接失败" : "尚未测试当前配置"}</strong>{testState === "error" && <small>HTTP 404：Provider 路径不存在或模型不可用。请检查 Base URL 与模型名称。Trace ID：llm_test_72ad</small>}{testState === "success" && <small>模型响应正常，耗时 482ms，未发送真实候选人数据。</small>}</span></div>{editable && <button className="button secondary" type="button" disabled={testState === "testing"} onClick={testConnection}>{testState === "testing" ? <RefreshCw size={15} /> : null}测试连接</button>}</div>{editable && <div className="settings-sticky-actions"><span>配置修改会记录到审计日志。</span><button className="button primary" type="button" onClick={() => onNotify("AI 设置已保存")}>保存设置</button></div>}{risk && <DangerDialog title="确认启用外部 Provider" description="启用后，授权岗位的 JD 与简历文本将发送到外部模型服务。" impact="请确认该 Provider 符合公司隐私与数据处理要求。API Key 不会发送给除目标 Provider 以外的服务。" confirmText="确认启用" onCancel={() => setRisk(false)} onConfirm={() => { setForm({ ...form, enabled: true }); setRisk(false); onNotify("外部 Provider 已启用并记录审计"); }} />}</div>;
}

function AuditSettings({ role, onNotify }) {
  const editable = role === "招聘管理员";
  const capabilities = getRoleCapabilities(role);
  const [action, setAction] = useState("全部操作");
  const [selected, setSelected] = useState(null);
  const [retention, setRetention] = useState(730);
  const [draftRetention, setDraftRetention] = useState(730);
  const [risk, setRisk] = useState(false);
  if (!capabilities.auditView) return <section className="settings-denied"><LockKeyhole size={31} /><h3>无审计与治理权限</h3><p>面试官不能查看系统访问记录或候选人保留策略。</p></section>;
  const rows = auditRows.filter((item) => action === "全部操作" || item.action === action);
  function saveRetention() { if (draftRetention < retention) { setRisk(true); return; } setRetention(draftRetention); onNotify("数据保留策略已保存"); }
  return <div className="settings-section"><div className="settings-section-heading"><div><h2>审计与数据治理</h2><p>查询关键操作并管理候选人数据保留周期。</p></div></div>{!editable && <PermissionNotice>HR 仅可查看授权对象的审计记录，不能修改保留策略。</PermissionNotice>}<div className="audit-toolbar"><label><select value={action} onChange={(event) => setAction(event.target.value)}><option>全部操作</option><option>登录</option><option>下载简历</option><option>状态变化</option><option>配置变更</option></select><ChevronDown size={14} /></label><span>近 30 天 · {rows.length} 条示例记录</span></div><div className="settings-table audit-table"><div className="settings-table-head"><span>时间</span><span>操作者</span><span>操作</span><span>对象</span><span>结果</span><span /></div>{rows.map((row) => <button type="button" className="settings-table-row" key={row.id} onClick={() => setSelected(row)}><span>{row.time}</span><span>{row.actor}</span><span>{row.action}</span><span>{row.object}</span><span className={row.result === "成功" ? "status-ok" : "status-danger"}>{row.result}</span><span>详情</span></button>)}</div><section className="retention-policy"><header><Database size={21} /><div><h3>数据保留策略</h3><p>缩短周期可能触发不可逆的数据清理。</p></div></header><div><label>候选人档案保留<select disabled={!editable} value={draftRetention} onChange={(event) => setDraftRetention(Number(event.target.value))}><option value="365">365 天</option><option value="540">540 天</option><option value="730">730 天</option><option value="1095">1095 天</option></select></label><label>审计日志保留<input disabled value="1095 天" /></label><label>备份保留<input disabled value="90 天" /></label>{editable && <button className="button primary" type="button" onClick={saveRetention}>保存保留策略</button>}</div></section>{selected && <aside className="settings-drawer" aria-label="审计详情"><header><div><h2>审计详情</h2><p>{selected.id} · {selected.result}</p></div><button className="icon-button" type="button" aria-label="关闭" onClick={() => setSelected(null)}><X size={20} /></button></header><div className="settings-drawer-body"><dl><div><dt>时间</dt><dd>{selected.time}</dd></div><div><dt>操作者</dt><dd>{selected.actor}</dd></div><div><dt>操作</dt><dd>{selected.action}</dd></div><div><dt>对象</dt><dd>{selected.object}</dd></div><div><dt>来源 IP</dt><dd>{selected.ip}</dd></div><div><dt>Trace ID</dt><dd>{selected.trace}</dd></div><div><dt>变更摘要</dt><dd>{selected.change}</dd></div></dl></div><footer><button className="button primary" type="button" onClick={() => setSelected(null)}>完成</button></footer></aside>}{risk && <DangerDialog title="确认缩短候选人保留期限" description={`保留周期将从 ${retention} 天缩短为 ${draftRetention} 天。`} impact="预计 18 位候选人将在下一次清理任务中进入删除队列；删除后只能从仍在保留期内的备份恢复。" confirmText="确认缩短期限" onCancel={() => setRisk(false)} onConfirm={() => { setRetention(draftRetention); setRisk(false); onNotify("保留策略已缩短并记录审计"); }} />}</div>;
}

export function SettingsWorkspace({ currentRole, onRoleChange, onNotify }) {
  const [section, setSection] = useState("组织与权限");
  const [aiDirty, setAiDirty] = useState(false);
  const [aiFormDraft, setAiFormDraft] = useState(defaultAiForm);
  const [pendingSection, setPendingSection] = useState(null);
  const content = section === "组织与权限" ? <OrganizationSettings role={currentRole} onNotify={onNotify} /> : section === "流程与评价模板" ? <TemplateSettings role={currentRole} onNotify={onNotify} /> : section === "AI 设置" ? <AiSettings role={currentRole} onNotify={onNotify} initialForm={aiFormDraft} onFormChange={setAiFormDraft} /> : <AuditSettings role={currentRole} onNotify={onNotify} />;
  function openSection(nextSection) {
    if (section === "AI 设置" && aiDirty && nextSection !== section) {
      setPendingSection(nextSection);
      return;
    }
    setSection(nextSection);
  }
  function leaveAiSettings(saveDraft) {
    if (saveDraft) onNotify("AI 设置草稿已保存在当前浏览器");
    else setAiFormDraft(defaultAiForm);
    setAiDirty(false);
    setSection(pendingSection);
    setPendingSection(null);
  }
  return <div className="settings-page"><div className="settings-heading"><div><h2>设置</h2><p>管理招聘组织、流程、AI 和数据治理。</p></div><RoleSwitch value={currentRole} onChange={onRoleChange} /></div><div className="settings-layout"><nav className="settings-subnav" aria-label="设置导航">{settingsSections.map(([label, Icon]) => <button type="button" key={label} className={section === label ? "active" : ""} onClick={() => openSection(label)}><Icon size={17} />{label}</button>)}</nav><main className="settings-content" onChangeCapture={() => { if (section === "AI 设置" && currentRole === "招聘管理员") setAiDirty(true); }} onClickCapture={(event) => { if (event.target.closest("button")?.textContent === "保存设置") setAiDirty(false); }}>{content}</main></div>{pendingSection && <div className="ux07-dialog-backdrop"><section className="ux07-dialog" role="dialog" aria-modal="true" aria-label="AI 设置尚未保存"><header><div><h3>AI 设置尚未保存</h3><p>离开后可以放弃本次修改，或将配置保存为本地草稿。</p></div><button className="icon-button" type="button" aria-label="关闭" onClick={() => setPendingSection(null)}><X size={19} /></button></header><div className="ux07-danger-impact"><AlertTriangle size={22} /><span>草稿只保存在当前浏览器，不会启用 Provider，也不会写入生产配置。</span></div><footer><button className="button secondary" type="button" onClick={() => setPendingSection(null)}>继续编辑</button><button className="button secondary" type="button" onClick={() => leaveAiSettings(false)}>放弃修改</button><button className="button primary" type="button" onClick={() => leaveAiSettings(true)}>保存草稿并离开</button></footer></section></div>}</div>;
}
