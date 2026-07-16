import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, Copy, Database, FileClock, KeyRound, LockKeyhole, Plus, RefreshCw, Search, ShieldCheck, SlidersHorizontal, Users, X } from "lucide-react";
import { canEditAiSettings, canEditOrganizationSettings, canEditRetentionSettings, canViewAuditSettings, canViewDeletionApprovalQueue, canViewRetentionSettings, getAllowedSettingsSections } from "./roleCapabilities.js";
import { createLlmSettingsController, getTestDisabledReason, releaseLlmSettingsSubscription } from "./llmSettings.js";
import { createGovernanceSettingsController, releaseGovernanceSettingsSubscription } from "./governanceSettings.js";
import { getInviteRoleOptions, organizationSettingsController } from "./organizationSettings.js";

const settingsSections = [
  ["组织与权限", Users],
  ["流程与评价模板", SlidersHorizontal],
  ["AI 设置", Bot],
  ["审计与数据治理", FileClock],
];
const settingsDefaultTabs = { "组织与权限": "成员", "流程与评价模板": "招聘流程" };
function RoleSwitch({ value, onChange }) {
  if (!onChange || value !== "招聘管理员") return null;
  return <div className="role-switch" aria-label="当前角色">{["招聘管理员", "HR", "面试官"].map((role) => <button type="button" key={role} className={value === role ? "active" : ""} onClick={() => onChange(role)}>{role}</button>)}</div>;
}

export function createDialogFocusManager({ dialog, restoreTarget, documentRef, isBusy, onClose }) {
  const focusable = () => Array.from(dialog.querySelectorAll("button, [href], input, select, textarea, [tabindex]"))
    .filter((element) => !element.disabled && element.getAttribute("aria-hidden") !== "true" && element.getAttribute("tabindex") !== "-1");
  return {
    focusInitial() {
      const initial = dialog.querySelector("[data-dialog-initial-focus]") || focusable()[0];
      initial?.focus();
    },
    handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!isBusy()) onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusable();
      if (elements.length === 0) {
        event.preventDefault();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      const active = documentRef.activeElement;
      if (event.shiftKey && (!dialog.contains(active) || active === first)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (!dialog.contains(active) || active === last)) {
        event.preventDefault();
        first.focus();
      }
    },
    restoreFocus() {
      if (restoreTarget?.isConnected !== false) restoreTarget?.focus?.();
    },
  };
}

function DangerDialog({ title, description, impact, confirmText, confirmDisabled = false, surfaceClassName = "", onCancel, onConfirm }) {
  const dialogRef = useRef(null);
  const focusManagerRef = useRef(null);
  const restoreTargetRef = useRef(typeof document === "undefined" ? null : document.activeElement);
  const busyRef = useRef(confirmDisabled);
  const cancelRef = useRef(onCancel);
  const resolvedSurfaceClassName = surfaceClassName || (title === "确认批准删除请求" ? "deletion-approval-dialog" : "");
  busyRef.current = confirmDisabled;
  cancelRef.current = onCancel;
  useEffect(() => {
    if (!dialogRef.current || typeof document === "undefined") return undefined;
    const manager = createDialogFocusManager({
      dialog: dialogRef.current,
      restoreTarget: restoreTargetRef.current,
      documentRef: document,
      isBusy: () => busyRef.current,
      onClose: () => cancelRef.current(),
    });
    focusManagerRef.current = manager;
    manager.focusInitial();
    return () => {
      focusManagerRef.current = null;
      manager.restoreFocus();
    };
  }, []);
  function handleDialogKeyDown(event) { focusManagerRef.current?.handleKeyDown(event); }
  return <div className="ux07-dialog-backdrop"><section ref={dialogRef} className={`ux07-dialog${resolvedSurfaceClassName ? ` ${resolvedSurfaceClassName}` : ""}`} role="dialog" aria-modal="true" aria-label={title} onKeyDown={handleDialogKeyDown}><header><div><h3>{title}</h3><p>{description}</p></div><button className="icon-button" type="button" aria-label="关闭" disabled={confirmDisabled} onClick={onCancel}><X size={19} /></button></header><div className="ux07-danger-impact"><AlertTriangle size={22} /><span>{impact}</span></div><footer><button className="button secondary" type="button" data-dialog-initial-focus disabled={confirmDisabled} onClick={onCancel}>取消</button><button className="button danger" type="button" disabled={confirmDisabled} onClick={onConfirm}>{confirmText}</button></footer></section></div>;
}

function PermissionNotice({ children }) {
  return <div className="settings-permission-notice"><LockKeyhole size={18} /><span>{children}</span></div>;
}

function OrganizationDrawer({ title, busy, onClose, children, footer }) {
  const drawerRef = useRef(null);
  const restoreTargetRef = useRef(typeof document === "undefined" ? null : document.activeElement);
  const busyRef = useRef(busy);
  const closeRef = useRef(onClose);
  busyRef.current = busy;
  closeRef.current = onClose;
  useEffect(() => {
    if (!drawerRef.current || typeof document === "undefined") return undefined;
    const manager = createDialogFocusManager({ dialog: drawerRef.current, restoreTarget: restoreTargetRef.current, documentRef: document, isBusy: () => busyRef.current, onClose: () => closeRef.current() });
    manager.focusInitial();
    const handleKeyDown = (event) => manager.handleKeyDown(event);
    document.addEventListener("keydown", handleKeyDown);
    return () => { document.removeEventListener("keydown", handleKeyDown); manager.restoreFocus(); };
  }, []);
  return <aside ref={drawerRef} className="settings-drawer organization-drawer" role="dialog" aria-modal="true" aria-label={title}><header><div><h2>{title}</h2><p>{title === "邀请成员" ? "发送一次性激活邀请，成员状态将显示为待激活。" : "创建一级部门供成员和职位归属使用。"}</p></div><button className="icon-button" type="button" aria-label="关闭" disabled={busy} onClick={onClose}><X size={20} /></button></header><div className="settings-drawer-body">{children}</div><footer>{footer}</footer></aside>;
}

function OrganizationSettings({ role, onNotify, activeTab = "成员", onTabChange = () => {}, controller = organizationSettingsController }) {
  const editable = canEditOrganizationSettings(role);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const tab = activeTab === "部门" ? "部门" : "成员";
  const [query, setQuery] = useState("");
  const [drawer, setDrawer] = useState(null);
  const [invite, setInvite] = useState({ displayName: "", email: "", departmentId: "", role: getInviteRoleOptions(role)[0]?.value || "" });
  const [departmentName, setDepartmentName] = useState("");
  const [copied, setCopied] = useState(false);
  const inviteRoles = getInviteRoleOptions(role);
  const busy = state.actionStatus === "saving";
  const invitationLink = state.invitation && typeof window !== "undefined" ? `${window.location.origin}${window.location.pathname}#invite=${encodeURIComponent(state.invitation.token)}` : "";

  useEffect(() => { void controller.load(); }, [controller]);
  if (role === "面试官") return <section className="settings-denied"><LockKeyhole size={31} /><h3>无组织权限</h3><p>面试官不能查看公司成员或部门。</p></section>;
  const visibleUsers = state.users.filter((user) => `${user.name}${user.email}${user.department}${user.role}`.toLowerCase().includes(query.toLowerCase()));
  const validInvite = Boolean(invite.displayName.trim() && /^\S+@\S+\.\S+$/.test(invite.email.trim()) && invite.departmentId && invite.role);
  const closeDrawer = () => { setDrawer(null); setCopied(false); controller.dismissInvitation(); };
  async function submitInvite() {
    if (!validInvite || busy) return;
    try { await controller.inviteMember(invite); onNotify("邀请已发送，链接仅显示一次"); } catch { /* safe controller message is rendered */ }
  }
  async function submitDepartment() {
    if (!departmentName.trim() || busy) return;
    try { await controller.addDepartment(departmentName); setDrawer(null); setDepartmentName(""); onNotify("部门已创建"); } catch { /* safe controller message is rendered */ }
  }
  async function copyInvitation() {
    try { await navigator.clipboard.writeText(invitationLink); setCopied(true); } catch { setCopied(false); }
  }
  return <div className="settings-section organization-settings"><div className="settings-section-heading"><div><h2>组织与权限</h2><p>从服务端管理成员邀请和部门归属。</p></div>{editable && <button className="button primary" type="button" onClick={() => { if (tab === "部门") setDrawer("department"); else { controller.dismissInvitation(); setInvite({ displayName: "", email: "", departmentId: state.departments[0]?.id || "", role: inviteRoles[0]?.value || "" }); setDrawer("invite"); } }}><Plus size={16} />{tab === "部门" ? "新增部门" : "邀请成员"}</button>}</div>{!editable && <PermissionNotice>当前为只读模式，邀请成员和新增部门由管理员完成。</PermissionNotice>}<div className="settings-tabs organization-tabs" role="tablist" aria-label="组织与权限"><button type="button" role="tab" aria-selected={tab === "成员"} className={tab === "成员" ? "active" : ""} onClick={() => onTabChange("成员")}>成员</button><button type="button" role="tab" aria-selected={tab === "部门"} className={tab === "部门" ? "active" : ""} onClick={() => onTabChange("部门")}>部门</button></div>{state.status === "loading" && <div className="organization-state" role="status"><RefreshCw size={18} />正在加载组织信息…</div>}{state.status === "error" && <div className="organization-state error" role="alert"><AlertTriangle size={18} /><span>{state.error}</span><button className="button secondary" type="button" onClick={() => controller.load()}>重试</button></div>}{state.status === "ready" && tab === "成员" && <><div className="settings-toolbar"><label className="settings-search"><Search size={16} /><input aria-label="搜索成员" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索姓名、邮箱、部门或角色" /></label></div><div className="settings-table users-table"><div className="settings-table-head"><span>成员</span><span>部门</span><span>角色</span><span>状态</span></div>{visibleUsers.map((user) => <div className="settings-table-row" key={user.id}><span><strong>{user.name}</strong><small>{user.email}</small></span><span>{user.department}</span><span>{user.role}</span><span className={user.status === "启用" ? "status-ok" : "status-muted"}>{user.status}</span></div>)}{visibleUsers.length === 0 && <div className="organization-empty">暂无符合条件的成员</div>}</div></>}{state.status === "ready" && tab === "部门" && <div className="department-list">{state.departments.map((department) => <div key={department.id}><strong>{department.name}</strong><span>{department.memberCount} 名成员 · {department.jobCount} 个职位</span></div>)}{state.departments.length === 0 && <div className="organization-empty">暂无部门</div>}</div>}{drawer === "invite" && <OrganizationDrawer title="邀请成员" busy={busy} onClose={closeDrawer} footer={<><button className="button secondary" type="button" disabled={busy} onClick={closeDrawer}>{state.invitation ? "完成" : "取消"}</button>{!state.invitation && <button className="button primary" type="button" disabled={!validInvite || busy} onClick={submitInvite}>{busy ? "正在发送…" : "发送邀请"}</button>}</>}>{state.actionError && <div className="settings-error" role="alert"><AlertTriangle size={17} />{state.actionError}</div>}{state.invitation ? <div className="invitation-result"><CheckCircle2 size={24} /><h3>邀请已创建</h3><p>该链接仅显示一次，请立即安全发送给成员。邀请在 48 小时后失效。</p><label>邀请链接<div><input aria-label="邀请链接" readOnly value={invitationLink} /><button className="button secondary" type="button" onClick={copyInvitation}><Copy size={16} />{copied ? "已复制" : "复制"}</button></div></label><small>有效期至 {state.invitation.expiresAt ? new Date(state.invitation.expiresAt).toLocaleString("zh-CN", { hour12: false }) : "48 小时后"}</small></div> : <><label>姓名<input data-dialog-initial-focus value={invite.displayName} onChange={(event) => setInvite({ ...invite, displayName: event.target.value })} autoComplete="name" /></label><label>工作邮箱<input type="email" value={invite.email} onChange={(event) => setInvite({ ...invite, email: event.target.value })} autoComplete="email" /></label><label>部门<select value={invite.departmentId} onChange={(event) => setInvite({ ...invite, departmentId: event.target.value })}><option value="">请选择部门</option>{state.departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label><label>角色<select value={invite.role} onChange={(event) => setInvite({ ...invite, role: event.target.value })}>{inviteRoles.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><p className="form-help">成员接受邀请前状态为“待激活”。</p></>}</OrganizationDrawer>}{drawer === "department" && <OrganizationDrawer title="新增部门" busy={busy} onClose={closeDrawer} footer={<><button className="button secondary" type="button" disabled={busy} onClick={closeDrawer}>取消</button><button className="button primary" type="button" disabled={!departmentName.trim() || busy} onClick={submitDepartment}>{busy ? "正在创建…" : "创建部门"}</button></>}>{state.actionError && <div className="settings-error" role="alert"><AlertTriangle size={17} />{state.actionError}</div>}<label>部门名称<input data-dialog-initial-focus value={departmentName} onChange={(event) => setDepartmentName(event.target.value)} /></label></OrganizationDrawer>}</div>;
}

function TemplateSettings({ role, onNotify, activeTab, onTabChange = () => {} }) {
  const editable = role === "招聘管理员";
  const tabs = role === "面试官" ? ["面试评价模板"] : ["招聘流程", "淘汰原因", "面试评价模板"];
  const tab = tabs.includes(activeTab) ? activeTab : tabs[0];
  const [stages, setStages] = useState(["新简历", "待复核", "待沟通", "待安排", "面试中", "待决策", "已录用"]);
  const [draftName, setDraftName] = useState("标准社招流程");
  const [saveFailed, setSaveFailed] = useState(false);
  function saveTemplate() { if (!saveFailed) { setSaveFailed(true); return; } setSaveFailed(false); onNotify("模板草稿已保存"); }
  return <div className="settings-section"><div className="settings-section-heading"><div><h2>流程与评价模板</h2><p>管理招聘阶段、状态原因和结构化评价。</p></div></div>{!editable && <PermissionNotice>{role === "面试官" ? "你只能查看面试评价模板。" : "当前为只读模式，模板修改由招聘管理员完成。"}</PermissionNotice>}<div className="settings-tabs">{tabs.map((item) => <button type="button" key={item} className={tab === item ? "active" : ""} onClick={() => onTabChange(item)}>{item}</button>)}</div>{tab === "招聘流程" && <section className="template-editor"><header><div><input disabled={!editable} value={draftName} onChange={(event) => setDraftName(event.target.value)} /><span>适用职位：AI 工程师、Java 后端工程师</span></div>{editable && <button className="button primary" type="button" onClick={saveTemplate}>{saveFailed ? "重试保存" : "保存模板"}</button>}</header>{saveFailed && <div className="settings-error"><AlertTriangle size={18} /><span>保存失败，草稿已保留。网络恢复后可直接重试。</span></div>}<div className="stage-editor">{stages.map((stage, index) => <div key={`${stage}-${index}`}><span>{index + 1}</span><input disabled={!editable} value={stage} onChange={(event) => setStages(stages.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} /><small>{["新简历", "面试中"].includes(stage) ? "进行中申请正在使用，不可删除" : "可调整"}</small>{editable && <button type="button" disabled={["新简历", "面试中"].includes(stage)} onClick={() => setStages(stages.filter((_, itemIndex) => itemIndex !== index))}>删除</button>}</div>)}</div></section>}{tab === "淘汰原因" && <div className="reason-list">{[["岗位要求不匹配", "必填", "启用"], ["候选人主动放弃", "必填", "启用"], ["薪资预期不匹配", "可选", "启用"], ["暂不招聘", "可选", "停用"]].map((item) => <div key={item[0]}><strong>{item[0]}</strong><span>{item[1]}</span><span>{item[2]}</span>{editable && <button type="button">编辑</button>}</div>)}</div>}{tab === "面试评价模板" && <div className="evaluation-template"><header><div><strong>技术岗位结构化评价</strong><span>适用：技术一面、技术二面</span></div>{editable && <button className="button secondary" type="button">编辑模板</button>}</header>{["专业能力", "问题解决", "沟通协作", "岗位匹配"].map((item) => <div key={item}><span>{item}</span><small>必填 · 需提升 / 一般 / 良好 / 优秀</small></div>)}<footer>结论：强烈推荐、推荐、保留、不推荐</footer></div>}</div>;
}

function formatTestTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN", { hour12: false });
}

function ReadOnlyAiSettings({ config }) {
  const rows = [
    ["configured", "配置状态", (value) => value ? "已配置" : "未配置"],
    ["enabled", "启用状态", (value) => value ? "已启用" : "未启用"],
    ["provider_id", "Provider", (value) => value || "—"],
    ["model", "模型", (value) => value || "—"],
    ["version", "配置版本", (value) => String(value)],
    ["last_test_status", "最近测试", (value) => value === "succeeded" ? "成功" : value === "failed" ? "失败" : "尚未测试"],
    ["last_test_error_code", "测试错误码", (value) => value || "—"],
    ["last_test_latency_ms", "测试耗时", (value) => Number.isFinite(value) ? `${value} ms` : "—"],
    ["last_tested_at", "测试时间", formatTestTime],
  ].filter(([key]) => Object.prototype.hasOwnProperty.call(config, key));
  return <div className="llm-readonly"><PermissionNotice>招聘管理员仅可查看服务端授权返回的模型配置，修改由系统管理员完成。</PermissionNotice><dl>{rows.map(([key, label, format]) => <div key={key}><dt>{label}</dt><dd>{format(config[key])}</dd></div>)}</dl></div>;
}

function AiSettings({ role, onNotify, onDirtyChange }) {
  const editable = canEditAiSettings(role);
  const controller = useMemo(() => createLlmSettingsController(), [role]);
  const [viewState, setViewState] = useState(() => controller.getState());
  useEffect(() => {
    const unsubscribe = controller.subscribe(setViewState);
    controller.load();
    return () => {
      releaseLlmSettingsSubscription(controller, unsubscribe);
      onDirtyChange?.(false);
    };
  }, [controller, onDirtyChange]);
  useEffect(() => { onDirtyChange?.(viewState.dirty); }, [viewState.dirty, onDirtyChange]);
  if (role === "面试官") return <section className="settings-denied"><LockKeyhole size={31} /><h3>无 AI 设置权限</h3><p>面试官不能查看 Provider、模型范围或密钥状态。</p></section>;
  const { status, config, draft, replacingKey, replacementKey, dirty, error, message } = viewState;
  if ((status === "idle" || status === "loading") && !config) return <div className="settings-section ai-settings"><div className="settings-section-heading"><div><h2>AI 设置</h2><p>正在读取已保存的模型配置。</p></div></div><div className="llm-settings-loading" role="status"><RefreshCw size={18} />正在加载设置…</div></div>;
  if (!config) return <div className="settings-section ai-settings"><div className="settings-section-heading"><div><h2>AI 设置</h2><p>控制候选人文本是否发送到外部模型服务。</p></div></div><div className="llm-settings-load-error" role="alert"><AlertTriangle size={20} /><div><strong>设置加载失败</strong><p>{error}</p></div><button className="button secondary" type="button" onClick={() => controller.load()}>重试</button></div></div>;
  if (!editable) return <div className="settings-section ai-settings"><div className="settings-section-heading"><div><h2>AI 设置</h2><p>查看组织当前使用的模型配置。</p></div></div><ReadOnlyAiSettings config={config} /></div>;

  const providers = Object.keys(config.available_providers || {});
  const models = config.available_providers?.[draft.provider_id] || [];
  const testDisabledReason = getTestDisabledReason(viewState);
  const saveMissingKey = draft.enabled && config.key_configured !== true && !replacementKey;
  const saveDisabled = status === "saving" || status === "testing" || !dirty || !draft.provider_id || !draft.model || saveMissingKey;
  const scopeIds = Array.isArray(config.allowed_job_ids) ? config.allowed_job_ids : [];
  const lastTestFailed = config.last_test_status === "failed";
  const lastTestSucceeded = config.last_test_status === "succeeded";
  async function save() { if (await controller.save()) onNotify("AI 设置已保存"); }
  async function testConnection() { if (await controller.testConnection()) onNotify("LLM 连接测试成功"); }
  return <div className="settings-section ai-settings"><div className="settings-section-heading"><div><h2>AI 设置</h2><p>控制候选人文本是否发送到后端允许的模型服务。</p></div></div>{error && <div className="settings-error" role="alert"><AlertTriangle size={17} />{error}</div>}{message && <div className="llm-settings-message" role="status">{message}</div>}<section className="ai-governance"><ShieldCheck size={20} /><div><strong>数据外发控制</strong><p>Provider 地址由后端部署白名单管理；前端仅选择已允许的 Provider 与模型。</p></div><label className="llm-enabled-toggle"><input type="checkbox" checked={draft.enabled} onChange={(event) => controller.updateDraft({ enabled: event.target.checked })} />启用</label></section><div className="settings-form llm-settings-form"><label>Provider<select value={draft.provider_id} onChange={(event) => { const provider_id = event.target.value; controller.updateDraft({ provider_id, model: config.available_providers?.[provider_id]?.[0] || "" }); }}><option value="">请选择 Provider</option>{providers.map((provider) => <option key={provider} value={provider}>{provider}</option>)}</select></label><label>模型<select value={draft.model} disabled={!draft.provider_id || models.length === 0} onChange={(event) => controller.updateDraft({ model: event.target.value })}><option value="">请选择模型</option>{models.map((model) => <option key={model} value={model}>{model}</option>)}</select></label><div className="llm-key-field"><span className="llm-field-label">API Key</span><div className="masked-key"><KeyRound size={16} aria-hidden="true" /><span>{config.key_configured ? "已安全配置" : "尚未配置"}</span><button type="button" onClick={() => replacingKey ? controller.cancelKeyReplacement() : controller.startKeyReplacement()}>{replacingKey ? "取消替换" : config.key_configured ? "替换" : "添加"}</button></div>{replacingKey && <label className="llm-replacement-key">新的 API Key<input type="password" autoComplete="new-password" value={replacementKey} onChange={(event) => controller.setReplacementKey(event.target.value)} placeholder="保存后不会再次显示" /></label>}{saveMissingKey && <small className="llm-field-hint">启用模型前必须添加并保存 API Key。</small>}</div><div className="llm-scope-summary"><strong>允许使用的岗位</strong><p>{scopeIds.length === 0 ? "全部岗位（空列表表示不限制岗位）" : `已限制为 ${scopeIds.length} 个岗位`}</p>{scopeIds.length > 0 && <code>{scopeIds.join("、")}</code>}<small>岗位选择器尚未开放；保存时会原样保留当前岗位 ID。</small></div></div><section className={`llm-test-result ${lastTestSucceeded ? "success" : lastTestFailed ? "error" : "idle"}`} aria-live="polite"><div>{lastTestSucceeded ? <CheckCircle2 size={20} /> : lastTestFailed ? <AlertTriangle size={20} /> : <Bot size={20} />}<span><strong>{status === "testing" ? "正在测试已保存的配置" : lastTestSucceeded ? "最近一次连接成功" : lastTestFailed ? "最近一次连接失败" : "尚未测试已保存的配置"}</strong><small>{lastTestSucceeded ? `耗时 ${config.last_test_latency_ms ?? "—"} ms · ${formatTestTime(config.last_tested_at)}` : lastTestFailed ? `安全错误码：${config.last_test_error_code || "未知"} · ${formatTestTime(config.last_tested_at)}` : "测试只使用服务器中最后保存的 Provider、模型和 API Key。"}</small>{testDisabledReason && <small className="llm-test-explanation">{testDisabledReason}</small>}</span></div><button className="button secondary" type="button" disabled={Boolean(testDisabledReason)} onClick={testConnection}>{status === "testing" && <RefreshCw size={15} />}测试连接</button></section><div className="settings-sticky-actions"><span>{status === "saving" ? "正在保存…" : dirty ? "有尚未保存的修改" : "当前配置已保存"}</span>{dirty && <button className="button secondary" type="button" disabled={status === "saving" || status === "testing"} onClick={() => controller.discardDraft()}>取消修改</button>}<button className="button primary" type="button" disabled={saveDisabled} onClick={save}>{status === "saving" ? "保存中…" : "保存设置"}</button></div></div>;
}

function formatAuditTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN", { hour12: false });
}

function auditResourceLabel(resource) {
  if (!resource) return "授权范围外资源";
  return resource.label ? `${resource.label} · ${resource.type} · ${resource.id}` : `${resource.type} · ${resource.id}`;
}

function auditOutcomeLabel(outcome) {
  if (outcome === "success") return "成功";
  if (outcome === "denied") return "已拒绝";
  if (outcome === "failure") return "失败";
  return "未知";
}

function auditFilterDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

const deletionCountLabels = [
  ["contacts", "联系方式"], ["resumes", "简历记录"], ["applications", "职位申请"], ["screeningRecords", "筛选记录"], ["interviews", "面试"], ["feedbackRecords", "反馈记录"], ["talentMemberships", "人才库关系"], ["resumeObjects", "简历文件"], ["temporaryExports", "临时导出"],
];

function deletionStatusLabel(status) {
  return ({ requested: "待审批", approved: "已批准", executing: "执行中", completed: "已完成", failed: "失败" })[status] || "未知";
}

function GovernanceState({ title, message, onRetry, denied = false }) {
  return <div className={`governance-state${denied ? " denied" : ""}`} role={denied ? undefined : "alert"}>{denied ? <LockKeyhole size={22} /> : <AlertTriangle size={22} />}<div><strong>{title}</strong><p>{message}</p></div>{onRetry && <button className="button secondary" type="button" onClick={onRetry}>重试</button>}</div>;
}

function AuditSettings({ role, onNotify }) {
  const canViewAudit = canViewAuditSettings(role);
  const canViewRetention = canViewRetentionSettings(role);
  const editable = canEditRetentionSettings(role);
  const controller = useMemo(() => createGovernanceSettingsController(), [role]);
  const [viewState, setViewState] = useState(() => controller.getState());
  const [filters, setFilters] = useState({ from: "", to: "", eventType: "", outcome: "" });
  const [selected, setSelected] = useState(null);
  const [deletionFilter, setDeletionFilter] = useState("");
  const [approvalOpen, setApprovalOpen] = useState(false);
  const canApproveDeletion = canViewDeletionApprovalQueue(role);

  useEffect(() => {
    const unsubscribe = controller.subscribe(setViewState);
    if (canViewAudit) controller.loadAudit();
    if (canViewAudit) controller.loadDeletionRequests();
    if (canViewRetention) controller.loadRetention();
    return () => releaseGovernanceSettingsSubscription(controller, unsubscribe);
  }, [canViewAudit, canViewRetention, controller]);

  if (!canViewAudit || !canViewRetention) return <section className="settings-denied"><LockKeyhole size={31} /><h3>无审计与治理权限</h3><p>当前角色不能查看系统访问记录或候选人保留策略。</p></section>;

  const { audit, retention, deletionQueue } = viewState;
  const selectedStillVisible = selected && audit.rows.some((row) => row.id === selected.id);
  const activeSelected = selectedStillVisible ? selected : null;
  const retentionBusy = retention.status === "loading" || retention.status === "saving" || retention.status === "previewing";

  function applyFilters(event) {
    event.preventDefault();
    setSelected(null);
    controller.loadAudit({
      from: auditFilterDate(filters.from),
      to: auditFilterDate(filters.to),
      eventType: filters.eventType.trim(),
      outcome: filters.outcome,
    });
  }

  function changeRetention(key, value) {
    controller.updateRetentionDraft({ [key]: Number(value) });
  }

  async function saveRetention() {
    if (await controller.saveRetention()) onNotify("数据保留策略已保存");
  }

  async function confirmRetention() {
    if (await controller.confirmRetentionSave()) onNotify("数据保留策略已保存并记录审计");
  }

  async function confirmDeletionApproval() {
    const approved = await controller.approveDeletionRequest();
    setApprovalOpen(false);
    if (approved) onNotify("删除请求已批准并进入处理队列");
  }

  return <div className="settings-section governance-settings"><div className="settings-section-heading"><div><h2>审计与数据治理</h2><p>查询服务端授权的关键操作并管理候选人数据保留周期。</p></div></div>{!editable && <PermissionNotice>当前为只读模式；审计范围由服务端授权，保留策略仅系统管理员可修改。</PermissionNotice>}<form className="audit-toolbar governance-filters" onSubmit={applyFilters}><label>开始时间<input type="datetime-local" value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} /></label><label>结束时间<input type="datetime-local" value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} /></label><label>事件类型<input value={filters.eventType} onChange={(event) => setFilters({ ...filters, eventType: event.target.value })} placeholder="如 candidate.created" /></label><label>结果<select value={filters.outcome} onChange={(event) => setFilters({ ...filters, outcome: event.target.value })}><option value="">全部结果</option><option value="success">成功</option><option value="denied">已拒绝</option><option value="failure">失败</option></select></label><button className="button secondary" type="submit">查询</button><span>{audit.rows.length} 条已加载记录</span></form>{audit.status === "loading" && <div className="governance-loading" role="status"><RefreshCw size={18} />正在加载授权审计记录…</div>}{audit.status === "denied" && <GovernanceState denied title="无审计记录权限" message="服务端未授权当前账号查看审计记录。" />}{audit.status === "error" && <GovernanceState title="审计记录加载失败" message={audit.error} onRetry={() => controller.loadAudit(audit.filters)} />}{audit.status === "empty" && <div className="governance-empty" role="status"><FileClock size={22} /><strong>没有符合条件的审计记录</strong><span>请调整筛选条件后重试。</span></div>}{audit.rows.length > 0 && <><div className="settings-table audit-table"><div className="settings-table-head"><span>时间</span><span>操作者</span><span>事件</span><span>资源</span><span>结果</span><span /></div>{audit.rows.map((row) => <button type="button" className="settings-table-row" key={row.id} onClick={() => setSelected(row)}><span>{formatAuditTime(row.createdAt)}</span><span>{row.actor.displayName || "已删除用户"}</span><span>{row.summary || row.eventType || "—"}</span><span>{auditResourceLabel(row.resource)}</span><span className={row.outcome === "success" ? "status-ok" : "status-danger"}>{auditOutcomeLabel(row.outcome)}</span><span>详情</span></button>)}</div><div className="audit-pagination" aria-live="polite">{audit.error && <span role="alert">{audit.error}</span>}{audit.nextCursor && <button className="button secondary" type="button" disabled={audit.loadingMore} onClick={() => controller.loadMoreAudit()}>{audit.loadingMore ? "加载中…" : "加载更多"}</button>}</div></>}
  <section className="deletion-queue"><header><ShieldCheck size={21} /><div><h3>删除请求审批</h3><p>{canApproveDeletion ? "查看组织内请求并审批待处理或失败请求。" : "仅显示服务端授权返回的本人请求。"}</p></div></header><div className="deletion-queue-toolbar"><label>状态筛选<select value={deletionFilter} onChange={(event) => { const value = event.target.value; setDeletionFilter(value); controller.loadDeletionRequests(value); }}><option value="">全部状态</option><option value="requested">待审批</option><option value="approved">已批准</option><option value="executing">执行中</option><option value="completed">已完成</option><option value="failed">失败</option></select></label><span>{deletionQueue.rows.length} 条已加载请求</span></div>{deletionQueue.status === "loading" && <div className="governance-loading" role="status"><RefreshCw size={18} />正在加载删除请求…</div>}{deletionQueue.status === "denied" && <GovernanceState denied title="无删除请求权限" message="服务端未授权当前账号查看删除请求。" />}{deletionQueue.status === "error" && <GovernanceState title="删除请求加载失败" message={deletionQueue.error} onRetry={() => controller.loadDeletionRequests(deletionQueue.statusFilter)} />}{deletionQueue.status === "empty" && <div className="governance-empty" role="status"><Database size={22} /><strong>没有符合条件的删除请求</strong><span>可调整状态筛选后重试。</span></div>}{deletionQueue.rows.length > 0 && <div className="deletion-request-list">{deletionQueue.rows.map((row) => <button type="button" key={row.id} onClick={() => controller.loadDeletionRequest(row.id)}><span><strong>{row.id}</strong><small>{formatAuditTime(row.requestedAt)}</small></span><span className={row.status === "failed" ? "status-danger" : "status-muted"}>{deletionStatusLabel(row.status)}</span><ChevronDown size={15} /></button>)}</div>}{deletionQueue.nextCursor && <div className="audit-pagination"><button className="button secondary" type="button" disabled={deletionQueue.loadingMore} onClick={() => controller.loadMoreDeletionRequests()}>{deletionQueue.loadingMore ? "加载中…" : "加载更多"}</button></div>}</section>
  <section className="retention-policy"><header><Database size={21} /><div><h3>数据保留策略</h3><p>缩短任一周期必须先预览服务端影响并显式确认。</p></div></header>{retention.status === "loading" && !retention.policy && <div className="governance-loading" role="status"><RefreshCw size={18} />正在加载保留策略…</div>}{retention.status === "denied" && <GovernanceState denied title="无保留策略权限" message="服务端未授权当前账号查看保留策略。" />}{retention.status === "error" && !retention.policy && <GovernanceState title="保留策略加载失败" message={retention.error} onRetry={() => controller.loadRetention()} />}{retention.status !== "denied" && retention.policy && retention.draft && <>{retention.error && <div className="settings-error" role="alert"><AlertTriangle size={17} />{retention.error}</div>}{retention.message && <div className="llm-settings-message" role="status">{retention.message}</div>}<div><label>终态候选人保留天数<input type="number" min="30" max="3650" disabled={!editable || retentionBusy} value={retention.draft.terminalDays} onChange={(event) => changeRetention("terminalDays", event.target.value)} /></label><label>人才库保留天数<input type="number" min="30" max="3650" disabled={!editable || retentionBusy} value={retention.draft.talentPoolDays} onChange={(event) => changeRetention("talentPoolDays", event.target.value)} /></label><label>备份窗口天数<input type="number" min="30" max="3650" disabled={!editable || retentionBusy} value={retention.draft.backupWindowDays} onChange={(event) => changeRetention("backupWindowDays", event.target.value)} /></label>{editable && <button className="button primary" type="button" disabled={!retention.dirty || retentionBusy} onClick={saveRetention}>{retention.status === "previewing" ? "正在预览…" : retention.status === "saving" ? "保存中…" : "保存保留策略"}</button>}</div><small className="retention-version">当前版本 {retention.policy.version} · 最近更新 {formatAuditTime(retention.policy.updatedAt)}</small></>}</section>{activeSelected && <aside className="settings-drawer" aria-label="审计详情"><header><div><h2>审计详情</h2><p>{activeSelected.id} · {auditOutcomeLabel(activeSelected.outcome)}</p></div><button className="icon-button" type="button" aria-label="关闭" onClick={() => setSelected(null)}><X size={20} /></button></header><div className="settings-drawer-body"><dl><div><dt>时间</dt><dd>{formatAuditTime(activeSelected.createdAt)}</dd></div><div><dt>操作者</dt><dd>{activeSelected.actor.displayName || "已删除用户"}</dd></div><div><dt>事件摘要</dt><dd>{activeSelected.summary || activeSelected.eventType || "—"}</dd></div><div><dt>资源</dt><dd>{auditResourceLabel(activeSelected.resource)}</dd></div><div><dt>结果</dt><dd>{auditOutcomeLabel(activeSelected.outcome)}</dd></div><div><dt>网络标识</dt><dd>{activeSelected.networkRef || "—"}</dd></div><div><dt>Trace ID</dt><dd>{activeSelected.traceId || "—"}</dd></div></dl></div><footer><button className="button primary" type="button" onClick={() => setSelected(null)}>完成</button></footer></aside>}{retention.preview && <DangerDialog title="确认缩短数据保留周期" description={`服务端影响预览有效期至 ${formatAuditTime(retention.preview.expiresAt)}。`} impact={`预计 ${retention.preview.affectedCandidateCount} 位候选人受到影响。请核对后明确确认。`} confirmText={retention.status === "saving" ? "保存中…" : "确认缩短期限"} confirmDisabled={retention.status === "saving"} onCancel={() => controller.cancelRetentionPreview()} onConfirm={confirmRetention} />}{deletionQueue.selected && <aside className="settings-drawer deletion-request-drawer" role="dialog" aria-modal="true" aria-label="删除请求详情"><header><div><h2>删除请求详情</h2><p>{deletionQueue.selected.id} · {deletionStatusLabel(deletionQueue.selected.status)}</p></div><button className="icon-button" type="button" aria-label="关闭" disabled={deletionQueue.approving} onClick={() => controller.loadDeletionRequests(deletionQueue.statusFilter)}><X size={20} /></button></header><div className="settings-drawer-body">{deletionQueue.detailStatus === "loading" ? <div className="governance-loading" role="status"><RefreshCw size={18} />正在刷新请求…</div> : <><dl><div><dt>请求 ID</dt><dd>{deletionQueue.selected.id}</dd></div><div><dt>原因代码</dt><dd>{deletionQueue.selected.reasonCode || "—"}</dd></div><div><dt>状态</dt><dd>{deletionStatusLabel(deletionQueue.selected.status)}</dd></div><div><dt>版本</dt><dd>{deletionQueue.selected.version}</dd></div><div><dt>请求时间</dt><dd>{formatAuditTime(deletionQueue.selected.requestedAt)}</dd></div><div><dt>批准时间</dt><dd>{formatAuditTime(deletionQueue.selected.approvedAt)}</dd></div><div><dt>安全错误码</dt><dd>{deletionQueue.selected.safeErrorCode || "—"}</dd></div><div><dt>策略版本</dt><dd>{deletionQueue.selected.impact.policyVersion}</dd></div><div><dt>候选人版本</dt><dd>{deletionQueue.selected.impact.candidateVersion}</dd></div><div><dt>备份窗口</dt><dd>{formatAuditTime(deletionQueue.selected.impact.backupWindowEndsAt)}</dd></div></dl><div className="deletion-impact-grid">{deletionCountLabels.map(([key, label]) => <span key={key}>{label}<strong>{deletionQueue.selected.impact.counts[key]}</strong></span>)}</div>{deletionQueue.impactChanged && <div className="settings-error" role="alert"><AlertTriangle size={17} />影响已变化，请重新核对后再次确认。</div>}{deletionQueue.detailError && <div className="settings-error" role="alert"><AlertTriangle size={17} />{deletionQueue.detailError}</div>}</>}</div><footer><button className="button secondary" type="button" disabled={deletionQueue.approving} onClick={() => controller.loadDeletionRequests(deletionQueue.statusFilter)}>关闭</button>{canApproveDeletion && ["requested", "failed"].includes(deletionQueue.selected.status) && <button className="button danger" type="button" disabled={deletionQueue.approving || deletionQueue.detailStatus === "loading"} onClick={() => setApprovalOpen(true)}>批准删除</button>}</footer></aside>}{approvalOpen && deletionQueue.selected && <DangerDialog title="确认批准删除请求" description={`请求 ${deletionQueue.selected.id} 将进入删除处理队列。`} impact="请核对九类影响数量和备份窗口。批准后仍可能因影响变化而要求重新确认。" confirmText={deletionQueue.approving ? "批准中…" : "确认批准"} confirmDisabled={deletionQueue.approving} onCancel={() => setApprovalOpen(false)} onConfirm={confirmDeletionApproval} />}</div>;
}

export function SettingsWorkspace({ currentRole, onRoleChange, onNotify, section = "组织与权限", organizationTab = "成员", templateTab = "招聘流程", onRouteChange = () => {} }) {
  const [aiDirty, setAiDirty] = useState(false);
  const [pendingSection, setPendingSection] = useState(null);
  const allowedSettingsSections = getAllowedSettingsSections(currentRole);
  const visibleSettingsSections = settingsSections.filter(([label]) => allowedSettingsSections.includes(label));
  const activeSection = allowedSettingsSections.includes(section) ? section : allowedSettingsSections[0];
  const content = activeSection === "组织与权限" ? <OrganizationSettings role={currentRole} onNotify={onNotify} activeTab={organizationTab} onTabChange={(tab) => onRouteChange("组织与权限", tab)} /> : activeSection === "流程与评价模板" ? <TemplateSettings role={currentRole} onNotify={onNotify} activeTab={templateTab} onTabChange={(tab) => onRouteChange("流程与评价模板", tab)} /> : activeSection === "AI 设置" ? <AiSettings role={currentRole} onNotify={onNotify} onDirtyChange={setAiDirty} /> : activeSection === "审计与数据治理" ? <AuditSettings key={currentRole} role={currentRole} onNotify={onNotify} /> : <section className="settings-denied"><LockKeyhole size={31} /><h3>无设置权限</h3><p>当前账号未获得系统设置访问权限。</p></section>;
  function openSection(nextSection) {
    if (activeSection === "AI 设置" && aiDirty && nextSection !== activeSection) {
      setPendingSection(nextSection);
      return;
    }
    onRouteChange(nextSection, settingsDefaultTabs[nextSection]);
  }
  function leaveAiSettings() {
    setAiDirty(false);
    onRouteChange(pendingSection, settingsDefaultTabs[pendingSection]);
    setPendingSection(null);
  }
  return <div className="settings-page"><div className="settings-heading"><div><h2>设置</h2><p>管理招聘组织、流程、AI 和数据治理。</p></div><RoleSwitch value={currentRole} onChange={onRoleChange} /></div><div className="settings-layout"><nav className="settings-subnav" aria-label="设置导航">{visibleSettingsSections.map(([label, Icon]) => <button type="button" key={label} className={activeSection === label ? "active" : ""} onClick={() => openSection(label)}><Icon size={17} />{label}</button>)}</nav><main className="settings-content">{content}</main></div>{pendingSection && <div className="ux07-dialog-backdrop"><section className="ux07-dialog" role="dialog" aria-modal="true" aria-label="AI 设置尚未保存"><header><div><h3>AI 设置尚未保存</h3><p>离开将放弃尚未保存的配置修改。</p></div><button className="icon-button" type="button" aria-label="关闭" onClick={() => setPendingSection(null)}><X size={19} /></button></header><div className="ux07-danger-impact"><AlertTriangle size={22} /><span>未保存的 Provider、模型和 API Key 替换内容都会被清除。</span></div><footer><button className="button secondary" type="button" onClick={() => setPendingSection(null)}>继续编辑</button><button className="button danger" type="button" onClick={leaveAiSettings}>放弃修改并离开</button></footer></section></div>}</div>;
}
