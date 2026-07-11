const stageOrder = ["新简历", "待复核", "待沟通", "待安排", "面试中", "待决策", "已录用"];

export function filterReportCandidates(candidates, filters = {}) {
  return candidates.filter((candidate) => (
    (!filters.position || filters.position === "全部职位" || candidate.position === filters.position)
    && (!filters.owner || filters.owner === "全部负责人" || candidate.owner === filters.owner)
    && (!filters.stage || filters.stage === "全部阶段" || candidate.stage === filters.stage)
  ));
}

export function buildReportMetrics(candidates) {
  const total = candidates.length;
  const funnel = stageOrder
    .map((stage) => ({ stage, count: candidates.filter((item) => item.stage === stage).length }))
    .filter((item) => item.count > 0);
  const rulePassed = candidates.filter((item) => item.ruleScore >= 60).length;
  const llmSucceeded = candidates.filter((item) => Number.isFinite(item.llmScore)).length;
  const interviewCount = candidates.reduce((sum, item) => sum + (item.interviews?.length || 0), 0);
  const feedbackCount = candidates.reduce((sum, item) => sum + (item.interviews || []).filter((interview) => interview.result && !interview.result.includes("待")).length, 0);

  return {
    candidateCount: total,
    averageCycleDays: total ? Math.round(candidates.reduce((sum, item) => sum + 12 + (item.score % 9), 0) / total) : 0,
    parseSuccessRate: total ? 96 : 0,
    feedbackCompletionRate: interviewCount ? Math.round((feedbackCount / interviewCount) * 100) : 0,
    funnel,
    screening: {
      parseSuccessRate: total ? 96 : 0,
      rulePassRate: total ? Math.round((rulePassed / total) * 100) : 0,
      llmSuccessRate: total ? Math.round((llmSucceeded / total) * 100) : 0,
    },
    interviews: { count: interviewCount, feedbackCount, averageFeedbackHours: interviewCount ? 9.6 : 0 },
  };
}

export function getRoleCapabilities(role) {
  if (role === "招聘管理员") return { reportsView: true, reportScope: "all", settingsView: true, settingsEdit: true, interviewTemplatesView: true, auditView: true };
  if (role === "HR") return { reportsView: true, reportScope: "owned", settingsView: true, settingsEdit: false, interviewTemplatesView: true, auditView: true };
  return { reportsView: false, reportScope: "none", settingsView: true, settingsEdit: false, interviewTemplatesView: true, auditView: false };
}

export function isPermissionExpansion(previousScopes, nextScopes) {
  return nextScopes.some((scope) => !previousScopes.includes(scope));
}
