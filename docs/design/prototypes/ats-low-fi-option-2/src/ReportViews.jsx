import { useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, BarChart3, CalendarRange, ChevronDown, Clock3, FileCheck2, FilterX, LockKeyhole, MessageSquareText, RefreshCw, UsersRound } from "lucide-react";
import { buildReportMetrics, filterReportCandidates, getRoleCapabilities } from "./ux07Domain.js";

const stageDurations = [
  { stage: "新简历", days: 1.2, overdue: 2 },
  { stage: "待复核", days: 1.8, overdue: 3 },
  { stage: "待沟通", days: 2.6, overdue: 6 },
  { stage: "待安排", days: 2.1, overdue: 4 },
  { stage: "面试中", days: 5.4, overdue: 2 },
  { stage: "待决策", days: 1.6, overdue: 1 },
];

function RoleSwitch({ value, onChange }) {
  return <div className="role-switch" aria-label="当前角色">{["招聘管理员", "HR", "面试官"].map((role) => <button type="button" key={role} className={value === role ? "active" : ""} onClick={() => onChange(role)}>{role}</button>)}</div>;
}

function NoPermission({ onNotify }) {
  return <section className="ux07-permission"><LockKeyhole size={34} /><h2>暂无报表查看权限</h2><p>面试官只能查看与自己相关的面试任务和评价模板，招聘数据不会在此页面暴露。</p><button className="button primary" type="button" onClick={() => onNotify("权限申请已发送给招聘管理员")}>申请报表权限</button></section>;
}

function MetricCard({ label, value, unit, note, icon: Icon }) {
  return <section className="report-metric"><div><span>{label}</span><Icon size={18} /></div><strong>{value ?? "—"}<small>{value == null ? "" : unit}</small></strong><p>{value == null ? "尚无筛选任务数据" : note}</p></section>;
}

export function ReportWorkspace({ candidates, positions, screeningSummary, currentRole, onRoleChange, onDrillDown, onNotify }) {
  const [filters, setFilters] = useState({ period: "近 30 天", position: "全部职位", department: "全部部门", owner: "全部负责人" });
  const [demoState, setDemoState] = useState("默认");
  const [errorDismissed, setErrorDismissed] = useState(false);
  const capabilities = getRoleCapabilities(currentRole);
  const visiblePositions = positions.filter((item) => currentRole !== "HR" || item.owner === "张小北");
  const candidateScope = currentRole === "HR" ? candidates.filter((item) => item.owner === "张小北") : candidates;
  const departmentPositions = filters.department === "全部部门" ? null : new Set(positions.filter((item) => item.department === filters.department).map((item) => item.name));
  const filtered = useMemo(() => {
    const base = filterReportCandidates(candidateScope, filters);
    return departmentPositions ? base.filter((item) => departmentPositions.has(item.position)) : base;
  }, [candidateScope, departmentPositions, filters]);
  const data = demoState === "空数据" ? [] : filtered;
  const metrics = buildReportMetrics(data, screeningSummary);
  const applied = Object.entries(filters).filter(([, value]) => !value.startsWith("全部") && value !== "近 30 天");
  const update = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  const clear = () => setFilters({ period: "近 30 天", position: "全部职位", department: "全部部门", owner: "全部负责人" });

  if (!capabilities.reportsView) return <div className="report-page"><div className="report-heading"><div><h2>基础招聘报表</h2><p>招聘漏斗、筛选质量和面试效率。</p></div></div><NoPermission onNotify={onNotify} /></div>;

  return <div className="report-page">
    <div className="report-heading"><div><h2>基础招聘报表</h2><p>{currentRole === "HR" ? "当前仅展示你负责的职位和候选人。" : "统一查看招聘漏斗、筛选质量和面试效率。"}</p></div>{currentRole === "招聘管理员" && <RoleSwitch value={currentRole} onChange={onRoleChange} />}</div>
    <section className="report-filter-panel"><div className="report-filters"><label><CalendarRange size={16} /><select aria-label="时间范围" value={filters.period} onChange={(event) => update("period", event.target.value)}><option>近 7 天</option><option>近 30 天</option><option>本季度</option></select><ChevronDown size={14} /></label><label><select aria-label="报表职位" value={filters.position} onChange={(event) => update("position", event.target.value)}><option>全部职位</option>{visiblePositions.map((item) => <option key={item.id}>{item.name}</option>)}</select><ChevronDown size={14} /></label><label><select aria-label="报表部门" value={filters.department} onChange={(event) => update("department", event.target.value)}><option>全部部门</option>{[...new Set(visiblePositions.map((item) => item.department))].map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={14} /></label><label><select aria-label="报表负责人" value={filters.owner} onChange={(event) => update("owner", event.target.value)}><option>全部负责人</option>{[...new Set(candidateScope.map((item) => item.owner))].map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={14} /></label><label className="demo-state"><select aria-label="报表演示状态" value={demoState} onChange={(event) => { setDemoState(event.target.value); setErrorDismissed(false); }}><option>默认</option><option>加载中</option><option>空数据</option><option>模块错误</option></select><ChevronDown size={14} /></label></div>{applied.length > 0 && <div className="applied-filters"><span>已应用：</span>{applied.map(([key, value]) => <button type="button" key={key} onClick={() => update(key, key === "position" ? "全部职位" : key === "department" ? "全部部门" : "全部负责人")}>{value} ×</button>)}<button className="clear-all" type="button" onClick={clear}><FilterX size={14} />清空全部</button></div>}</section>

    {demoState === "加载中" ? <div className="report-skeleton" aria-label="报表加载中">{Array.from({ length: 8 }, (_, index) => <span key={index} />)}</div> : data.length === 0 ? <section className="report-empty"><BarChart3 size={32} /><h3>当前筛选暂无招聘数据</h3><p>调整筛选范围或清空条件后重新查看。</p><button className="button primary" type="button" onClick={() => { clear(); setDemoState("默认"); }}>清除筛选</button></section> : <>
      <div className="report-metrics"><MetricCard label="招聘申请" value={metrics.applicationCount} unit="份" note={`${metrics.candidateCount} 位候选人`} icon={UsersRound} /><MetricCard label="平均招聘周期" value={metrics.averageCycleDays} unit="天" note="从申请到终态" icon={Clock3} /><MetricCard label="简历解析成功率" value={metrics.parseSuccessRate} unit="%" note="来自当前筛选任务" icon={FileCheck2} /><MetricCard label="面试反馈完成率" value={metrics.feedbackCompletionRate} unit="%" note={`${metrics.interviews.feedbackCount}/${metrics.interviews.count || 0} 份已完成`} icon={MessageSquareText} /></div>
      <div className="report-grid"><section className="report-panel funnel-panel"><header><div><h3>招聘漏斗</h3><p>点击阶段查看对应候选人</p></div><span>{filters.period}</span></header><div className="report-funnel">{metrics.funnel.map((item, index) => <button type="button" key={item.stage} onClick={() => onDrillDown({ position: filters.position, stage: item.stage })} style={{ "--funnel-width": `${Math.max(38, 100 - index * 9)}%` }}><span>{item.stage}</span><strong>{item.count}</strong><small>{index === 0 ? "100%" : `${Math.round((item.count / metrics.funnel[0].count) * 100)}%`}</small><ArrowRight size={15} /></button>)}</div><table><thead><tr><th>阶段</th><th>人数</th><th>占首阶段</th></tr></thead><tbody>{metrics.funnel.map((item) => <tr key={item.stage}><td>{item.stage}</td><td>{item.count}</td><td>{Math.round((item.count / metrics.funnel[0].count) * 100)}%</td></tr>)}</tbody></table></section>
        <section className="report-panel duration-panel"><header><div><h3>阶段平均停留</h3><p>识别流程中的等待瓶颈</p></div></header><div className="duration-bars">{stageDurations.map((item) => <div key={item.stage}><span>{item.stage}</span><div><i style={{ width: `${item.days / 6 * 100}%` }} /></div><strong>{item.days} 天</strong><small>{item.overdue} 人超期</small></div>)}</div></section>
        <section className="report-panel quality-panel">
          <header><div><h3>筛选质量</h3><p>解析、规则和 LLM 独立统计</p></div></header>
          {demoState === "模块错误" && !errorDismissed ? <div className="module-error"><AlertTriangle size={21} /><strong>LLM 指标加载失败</strong><p>其他筛选指标不受影响。Trace ID：rep_07_llm_429</p><button type="button" onClick={() => setErrorDismissed(true)}><RefreshCw size={14} />重试模块</button></div> : <div className="quality-rates">{Object.entries({ "解析成功率": metrics.screening.parseSuccessRate, "规则通过率": metrics.screening.rulePassRate, "LLM 成功率": metrics.screening.llmSuccessRate }).map(([label, value]) => <div key={label}><span>{label}</span><strong>{value == null ? "—" : `${value}%`}</strong><div><i style={{ width: `${value ?? 0}%` }} /></div></div>)}</div>}
          <table><thead><tr><th>指标</th><th>成功率</th><th>口径</th></tr></thead><tbody><tr><td>解析成功率</td><td>{metrics.screening.parseSuccessRate == null ? "—" : `${metrics.screening.parseSuccessRate}%`}</td><td>成功解析 / 导入</td></tr><tr><td>规则通过率</td><td>{metrics.screening.rulePassRate}%</td><td>规则 ≥ 60</td></tr><tr><td>LLM 成功率</td><td>{metrics.screening.llmSuccessRate}%</td><td>返回有效评分</td></tr></tbody></table>
        </section>
        <section className="report-panel interview-report"><header><div><h3>面试效率</h3><p>场次、反馈和反馈时效</p></div></header><div><section><span>面试场次</span><strong>{metrics.interviews.count}</strong></section><section><span>完成反馈</span><strong>{metrics.interviews.feedbackCount}</strong></section><section><span>平均反馈时效</span><strong>{metrics.interviews.averageFeedbackHours}h</strong></section></div><p>反馈完成率 {metrics.feedbackCompletionRate}% · 目标 90%</p></section></div>
    </>}
  </div>;
}
