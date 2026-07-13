import test from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "./apiClient.js";
import { createSessionController, getSessionIdentity, getSessionMessage, mapServerRoles } from "./session.js";

const user = { display_name: "林岚", roles: ["recruiter"] };

test("会话从 bootstrapping 开始，/me 的 401 转为 anonymous", async () => {
  const controller = createSessionController({
    getMe: async () => { throw new ApiError({ status: 401, code: "authentication_required" }); },
  });

  assert.equal(controller.getSnapshot().status, "bootstrapping");
  await controller.bootstrap();
  assert.deepEqual(controller.getSnapshot(), {
    status: "anonymous",
    user: null,
    role: null,
    submitting: false,
    loggingOut: false,
    error: null,
  });
});

test("bootstrap 使用 /me 身份并进入 authenticated", async () => {
  const controller = createSessionController({ getMe: async () => user });

  await controller.bootstrap();

  assert.equal(controller.getSnapshot().status, "authenticated");
  assert.equal(controller.getSnapshot().user.display_name, "林岚");
  assert.equal(controller.getSnapshot().role, "HR 招聘专员");
});

test("/me 返回未知或缺失角色时保留身份并进入 forbidden", async () => {
  for (const roles of [["future_role"], [], undefined]) {
    const deniedUser = { display_name: "受限用户", ...(roles === undefined ? {} : { roles }) };
    const controller = createSessionController({ getMe: async () => deniedUser });

    await controller.bootstrap();

    assert.equal(controller.getSnapshot().status, "forbidden");
    assert.equal(controller.getSnapshot().user, deniedUser);
    assert.equal(controller.getSnapshot().role, null);
  }
});

test("登录按 login 再 /me 的顺序执行并只保存 /me 用户", async () => {
  const calls = [];
  const controller = createSessionController({
    login: async (credentials) => calls.push(["login", credentials]),
    getMe: async () => { calls.push(["me"]); return user; },
  });

  await controller.login({ organization_slug: "acme", email: "hr@example.test", password: "secret" });

  assert.deepEqual(calls, [
    ["login", { organization_slug: "acme", email: "hr@example.test", password: "secret" }],
    ["me"],
  ]);
  assert.equal(controller.getSnapshot().status, "authenticated");
  assert.equal(controller.getSnapshot().user, user);
});

test("登录失败区分通用认证失败与服务不可用", async () => {
  const auth = createSessionController({ login: async () => { throw new ApiError({ status: 401 }); } });
  const unavailable = createSessionController({ login: async () => { throw new ApiError({ kind: "unavailable" }); } });

  await assert.rejects(auth.login({}));
  await assert.rejects(unavailable.login({}));

  assert.equal(auth.getSnapshot().error, "authentication");
  assert.equal(unavailable.getSnapshot().error, "unavailable");
});

test("退出请求失败时保留认证身份和 CSRF 并显示安全错误", async () => {
  let cleared = false;
  const controller = createSessionController({
    getMe: async () => user,
    logout: async () => { throw new ApiError({ status: 503 }); },
    clearCsrf: () => { cleared = true; },
  });
  await controller.bootstrap();

  await assert.rejects(controller.logout());

  assert.equal(cleared, false);
  assert.equal(controller.getSnapshot().status, "authenticated");
  assert.equal(controller.getSnapshot().user, user);
  assert.equal(controller.getSnapshot().loggingOut, false);
  assert.equal(controller.getSnapshot().error, "logout_failed");
  assert.equal(getSessionMessage(controller.getSnapshot().error), "退出失败，请稍后重试。");
});

test("成功退出后才清除认证身份和内存 CSRF", async () => {
  let cleared = false;
  const controller = createSessionController({
    getMe: async () => user,
    logout: async () => {},
    clearCsrf: () => { cleared = true; },
  });
  await controller.bootstrap();

  await controller.logout();

  assert.equal(cleared, true);
  assert.equal(controller.getSnapshot().status, "anonymous");
  assert.equal(controller.getSnapshot().user, null);
});

test("forbidden 会话仍可成功退出", async () => {
  let logoutCalls = 0;
  let cleared = false;
  const deniedUser = { display_name: "受限用户", roles: ["future_role"] };
  const controller = createSessionController({
    getMe: async () => deniedUser,
    logout: async () => { logoutCalls += 1; },
    clearCsrf: () => { cleared = true; },
  });
  await controller.bootstrap();

  await controller.logout();

  assert.equal(logoutCalls, 1);
  assert.equal(cleared, true);
  assert.equal(controller.getSnapshot().status, "anonymous");
});

test("服务端角色仅映射到现有三个原型角色", () => {
  assert.equal(mapServerRoles(["system_admin"]), "系统管理员");
  assert.equal(mapServerRoles(["recruiting_admin"]), "招聘管理员");
  assert.equal(mapServerRoles(["recruiter"]), "HR 招聘专员");
  assert.equal(mapServerRoles(["hiring_manager"]), "面试官");
  assert.equal(mapServerRoles(["interviewer"]), "面试官");
  assert.equal(mapServerRoles(["unknown_role"]), null);
  assert.equal(mapServerRoles(["interviewer", "recruiting_admin"]), "招聘管理员");
  assert.equal(mapServerRoles(["system_admin", "recruiting_admin"]), "系统管理员");
});

test("登录界面只显示安全的通用状态文案", () => {
  assert.equal(getSessionMessage("authentication"), "登录信息不正确或账号暂不可用，请核对后重试。");
  assert.equal(getSessionMessage("unavailable"), "服务暂时无法连接，请稍后重试。");
  assert.equal(getSessionMessage("internal trace detail"), "");
});

test("认证身份使用 /me 显示名而不是原型角色夹具", () => {
  assert.deepEqual(getSessionIdentity({ display_name: " 林岚 " }, "HR 招聘专员"), {
    name: "林岚",
    title: "HR 招聘专员",
  });
  assert.deepEqual(getSessionIdentity({}, null), { name: "当前用户", title: "未配置角色" });
});
