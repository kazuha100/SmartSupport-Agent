import { FormEvent, useState } from "react";
import { Headphones, LockKeyhole, LogIn, UserPlus, UserRound } from "lucide-react";
import { AuthUser, login, register } from "../lib/api";

type Portal = "employee" | "storefront";

export default function LoginScreen({ onLogin, portal = "employee" }: { onLogin: (user: AuthUser) => void; portal?: Portal }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canRegister = portal === "storefront";

  async function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (mode === "register") {
      if (!/^[A-Za-z0-9_]{4,32}$/.test(username.trim())) {
        setError("用户名须为 4–32 位字母、数字或下划线"); return;
      }
      if (password.length < 8 || password.length > 72) {
        setError("密码须为 8–72 位，且包含字母和数字"); return;
      }
      if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
        setError("密码必须同时包含字母和数字"); return;
      }
    }
    setBusy(true);
    try {
      const user = mode === "register"
        ? await register(username.trim(), username.trim(), password)
        : await login(username.trim(), password);
      if (portal === "storefront" && user.role !== "customer") throw new Error("请使用顾客账号登录商城");
      if (portal === "employee" && user.role === "customer") throw new Error("顾客账号请前往商城登录");
      onLogin(user);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败"); }
    finally { setBusy(false); }
  }

  return <main className="login-screen"><section className="login-panel">
    <div className="login-brand"><span><Headphones size={22} /></span><div><strong>{portal === "storefront" ? "星云商城" : "SmartSupport"}</strong><small>{portal === "storefront" ? "3C 数码与智能家电" : "企业级客服工作台"}</small></div></div>
    <div className="login-heading"><h1>{mode === "register" ? "创建商城账户" : portal === "storefront" ? "登录商城" : "员工登录"}</h1><span>{mode === "register" ? "注册后即可咨询，无需先下单" : "使用您的账户继续"}</span></div>
    {canRegister && <div className="account-selector"><button type="button" disabled={busy} className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(""); }}>登录</button><button type="button" disabled={busy} className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(""); }}>注册</button></div>}
    <form onSubmit={submit}>
      <label><span>用户名</span><div><UserRound size={16} /><input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} placeholder="4–32 位字母、数字或下划线" required /></div></label>
      <label><span>密码</span><div><LockKeyhole size={16} /><input type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} value={password} onChange={e => setPassword(e.target.value)} placeholder="至少 8 位，包含字母和数字" required /></div></label>
      {mode === "register" && <small>用户名为 4–32 位字母、数字或下划线；密码为 8–72 位，须包含字母和数字。</small>}
      {error && <p className="login-error" role="alert">{error}</p>}
      <button className="login-button" disabled={busy} type="submit">{mode === "register" ? <UserPlus size={17} /> : <LogIn size={17} />}{busy ? "处理中" : mode === "register" ? "注册并登录" : "登录"}</button>
    </form>
  </section></main>;
}
