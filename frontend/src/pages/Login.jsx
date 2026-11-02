import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { homeFor, useAuth } from "../auth.jsx";
import { Field } from "../components/ui.jsx";

const DEMO = ["admin", "seller1", "seller2", "seller3", "customer1", "customer2", "customer3", "warehouse1", "support1"];

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    try {
      const u = await login(username, password);
      nav(loc.state?.from || homeFor(u.role), { replace: true });
    } catch (err) { setError(err.message); }
  };
  return (
    <div className="login-wrap">
      <form className="panel login" onSubmit={submit} aria-labelledby="login-title">
        <h1 id="login-title">Sign in</h1>
        {error && <p className="alert alert-error" role="alert" data-testid="login-error">{error}</p>}
        <Field label="Username" id="login-username"><input id="login-username" data-testid="login-username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required /></Field>
        <Field label="Password" id="login-password"><input id="login-password" data-testid="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></Field>
        <button className="btn btn-primary block" type="submit" data-testid="login-submit">Sign in</button>
        <p className="muted small">Demo accounts (password <code>GuardSLM2026!</code>):</p>
        <div className="chips">
          {DEMO.map((d) => <button type="button" key={d} className="chip" data-testid={`demo-${d}`} onClick={() => { setUsername(d); setPassword("GuardSLM2026!"); }}>{d}</button>)}
        </div>
      </form>
    </div>
  );
}
