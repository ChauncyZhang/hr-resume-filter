import { useState } from "react";
import { Building2, LoaderCircle, LockKeyhole, LogIn, LogOut, Mail, ShieldX } from "lucide-react";
import { getSessionMessage } from "./session.js";

export function SessionLoadingView() {
  return (
    <main className="session-loading" aria-busy="true" aria-live="polite">
      <LoaderCircle className="spin" size={24} aria-hidden="true" />
      <span>正在确认登录状态…</span>
    </main>
  );
}

export function AccessDeniedView({ displayName, error, loggingOut, onLogout }) {
  const message = getSessionMessage(error);
  return (
    <main className="access-denied-page">
      <section className="access-denied-card" aria-labelledby="access-denied-title">
        <span className="access-denied-icon" aria-hidden="true"><ShieldX size={25} /></span>
        <p className="access-denied-identity">{displayName}</p>
        <h1 id="access-denied-title">当前账号暂无访问权限</h1>
        <p>你的账号已完成验证，但尚未分配可使用的系统角色。请联系组织管理员处理。</p>
        {message && <div className="access-denied-error" role="alert">{message}</div>}
        <button className="button secondary" type="button" disabled={loggingOut} onClick={() => { void onLogout().catch(() => {}); }}>
          {loggingOut ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <LogOut size={17} aria-hidden="true" />}
          {loggingOut ? "正在退出…" : "退出登录"}
        </button>
      </section>
    </main>
  );
}

export function LoginView({ error, submitting, onLogin }) {
  const [form, setForm] = useState({ organization_slug: "", email: "", password: "" });
  const message = getSessionMessage(error);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    try {
      await onLogin(form);
    } catch {
      // The session controller exposes only a safe, categorized error to this view.
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <header className="login-heading">
          <div className="login-mark" aria-hidden="true">招</div>
          <div>
            <p>招聘协同平台</p>
            <h1 id="login-title">登录工作台</h1>
          </div>
        </header>
        <p className="login-intro">使用所属组织与工作账号继续。</p>

        <form className="login-form" onSubmit={submit} aria-busy={submitting}>
          <label>
            <span>组织标识</span>
            <div className="login-input">
              <Building2 size={17} aria-hidden="true" />
              <input
                name="organization_slug"
                value={form.organization_slug}
                onChange={(event) => update("organization_slug", event.target.value)}
                autoComplete="organization"
                placeholder="例如：acme"
                required
                disabled={submitting}
              />
            </div>
          </label>
          <label>
            <span>工作邮箱</span>
            <div className="login-input">
              <Mail size={17} aria-hidden="true" />
              <input
                name="email"
                type="email"
                value={form.email}
                onChange={(event) => update("email", event.target.value)}
                autoComplete="username"
                placeholder="name@company.com"
                required
                disabled={submitting}
              />
            </div>
          </label>
          <label>
            <span>密码</span>
            <div className="login-input">
              <LockKeyhole size={17} aria-hidden="true" />
              <input
                name="password"
                type="password"
                value={form.password}
                onChange={(event) => update("password", event.target.value)}
                autoComplete="current-password"
                placeholder="请输入密码"
                required
                disabled={submitting}
              />
            </div>
          </label>

          <div className="login-message" role={message ? "alert" : "status"} aria-live="polite">
            {message}
          </div>
          <button className="button primary login-submit" type="submit" disabled={submitting}>
            {submitting ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <LogIn size={17} aria-hidden="true" />}
            {submitting ? "正在登录…" : "登录"}
          </button>
        </form>
      </section>
      <p className="login-footnote">账号权限由组织管理员统一配置</p>
    </main>
  );
}
