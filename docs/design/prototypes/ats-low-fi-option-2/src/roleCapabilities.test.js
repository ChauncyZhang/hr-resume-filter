import test from "node:test";
import assert from "node:assert/strict";
import {
  canAccessNav,
  canEditAiSettings,
  canEditAuditSettings,
  canEditOrganizationSettings,
  canPerformAction,
  getAllowedNavItems,
  getAllowedSettingsSections,
  getDefaultNavItem,
  getRoleIdentity,
  getSettingsAccess,
} from "./roleCapabilities.js";

const fullRecruitingNav = ["工作台", "职位", "候选人", "面试", "人才库", "报表", "设置"];

test("系统管理员只能进入设置且没有招聘操作", () => {
  assert.deepEqual(getAllowedNavItems("系统管理员"), ["设置"]);
  assert.equal(getDefaultNavItem("系统管理员"), "设置");
  assert.equal(getSettingsAccess("系统管理员"), "完整");
  for (const action of ["导入简历", "新建职位", "候选人搜索", "查看报表"]) {
    assert.equal(canPerformAction("系统管理员", action), false);
  }
  assert.equal(canAccessNav("系统管理员", "工作台"), false);
  assert.deepEqual(getAllowedSettingsSections("系统管理员"), ["组织与权限", "AI 设置", "审计与数据治理"]);
  assert.equal(canEditOrganizationSettings("系统管理员"), true);
  assert.equal(canEditAuditSettings("系统管理员"), true);
});

test("只有系统管理员可以编辑 AI 设置", () => {
  assert.equal(canEditAiSettings("系统管理员"), true);
  assert.equal(canEditAiSettings("招聘管理员"), false);
  assert.equal(canEditAiSettings("HR 招聘专员"), false);
  assert.equal(canEditAiSettings("面试官"), false);
});

test("招聘管理员拥有完整招聘导航和设置能力", () => {
  assert.deepEqual(getAllowedNavItems("招聘管理员"), fullRecruitingNav);
  assert.equal(getDefaultNavItem("招聘管理员"), "工作台");
  assert.equal(getSettingsAccess("招聘管理员"), "完整");
  assert.equal(canPerformAction("招聘管理员", "导入简历"), true);
  assert.deepEqual(getAllowedSettingsSections("招聘管理员"), ["组织与权限", "流程与评价模板", "AI 设置", "审计与数据治理"]);
  assert.equal(canEditOrganizationSettings("招聘管理员"), true);
  assert.equal(canEditAuditSettings("招聘管理员"), false);
});

test("HR 招聘专员拥有招聘导航但设置能力有限", () => {
  assert.deepEqual(getAllowedNavItems("HR 招聘专员"), fullRecruitingNav);
  assert.equal(getSettingsAccess("HR 招聘专员"), "有限");
  assert.equal(canPerformAction("HR 招聘专员", "导入简历"), true);
});

test("面试官只能访问工作台和面试", () => {
  assert.deepEqual(getAllowedNavItems("面试官"), ["工作台", "面试"]);
  for (const item of ["职位", "候选人", "人才库", "报表", "设置"]) {
    assert.equal(canAccessNav("面试官", item), false);
  }
  assert.equal(canAccessNav("面试官", "面试"), true);
});

test("面试官不能搜索候选人或导入简历", () => {
  assert.equal(canPerformAction("面试官", "候选人搜索"), false);
  assert.equal(canPerformAction("面试官", "导入简历"), false);
  assert.equal(canPerformAction("面试官", "提交面试反馈"), true);
});

test("用人经理只访问被授权招聘协作页面且不能执行 HR 管理动作", () => {
  assert.deepEqual(getAllowedNavItems("用人经理"), ["工作台", "职位", "候选人", "面试", "报表"]);
  assert.equal(canPerformAction("用人经理", "候选人搜索"), true);
  assert.equal(canPerformAction("用人经理", "提交面试反馈"), true);
  assert.equal(canPerformAction("用人经理", "新建职位"), false);
  assert.equal(canPerformAction("用人经理", "导入简历"), false);
  assert.equal(canPerformAction("用人经理", "推进候选人"), false);
  assert.equal(getSettingsAccess("用人经理"), "无");
});

test("角色身份映射包含姓名和职务且不会暴露可变内部状态", () => {
  assert.deepEqual(getRoleIdentity("招聘管理员"), { name: "周明", title: "招聘管理员" });
  assert.deepEqual(getRoleIdentity("HR 招聘专员"), { name: "张小北", title: "HR 招聘专员" });
  assert.deepEqual(getRoleIdentity("面试官"), { name: "王磊", title: "技术面试官" });

  const identity = getRoleIdentity("面试官");
  identity.name = "被修改";
  assert.equal(getRoleIdentity("面试官").name, "王磊");
});

test("未知角色、导航和操作默认拒绝", () => {
  assert.deepEqual(getAllowedNavItems("未知角色"), []);
  assert.equal(canAccessNav("未知角色", "工作台"), false);
  assert.equal(canAccessNav("招聘管理员", "不存在的导航"), false);
  assert.equal(canPerformAction("招聘管理员", "不存在的操作"), false);
  assert.equal(getRoleIdentity("未知角色"), null);
  assert.equal(getSettingsAccess("未知角色"), "无");
  assert.deepEqual(getAllowedSettingsSections("未知角色"), []);
  assert.equal(canEditOrganizationSettings("未知角色"), false);
  assert.equal(canEditAuditSettings("未知角色"), false);
});
