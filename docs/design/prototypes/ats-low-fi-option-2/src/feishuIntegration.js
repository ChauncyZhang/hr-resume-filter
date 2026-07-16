function safeString(value) {
  return typeof value === "string" ? value : "";
}

export function normalizeFeishuConfig(value = {}) {
  return {
    configured: value.configured === true,
    appId: safeString(value.app_id),
    redirectUri: safeString(value.redirect_uri),
    calendarId: safeString(value.calendar_id),
    enabled: value.enabled === true,
    appSecretConfigured: value.app_secret_configured === true,
    verificationTokenConfigured: value.verification_token_configured === true,
    encryptKeyConfigured: value.encrypt_key_configured === true,
    version: Number.isInteger(value.version) ? value.version : 0,
    lastTestStatus: safeString(value.last_test_status),
    lastTestedAt: safeString(value.last_tested_at),
    lastTestErrorCode: safeString(value.last_test_error_code),
  };
}

export function normalizeFeishuBinding(value = {}) {
  if (value.bound !== true) return { bound: false, unionId: "", openId: "" };
  return { bound: true, unionId: safeString(value.union_id), openId: safeString(value.open_id) };
}

export function getFeishuLoginErrorMessage(error) {
  if (error?.code === "feishu_disabled") {
    return "当前组织尚未启用飞书登录，请联系管理员前往“设置 → 飞书集成”完成配置并启用。";
  }
  return "飞书登录服务暂时不可用，请稍后重试。";
}

export async function startFeishuAuthorization(authorize, navigate = (url) => window.location.assign(url)) {
  const result = await authorize();
  const authorizationUrl = new URL(result?.authorization_url || "");
  if (authorizationUrl.protocol !== "https:" || authorizationUrl.hostname !== "accounts.feishu.cn") {
    throw new Error("invalid_feishu_authorization_url");
  }
  navigate(authorizationUrl.toString());
  return authorizationUrl.toString();
}
