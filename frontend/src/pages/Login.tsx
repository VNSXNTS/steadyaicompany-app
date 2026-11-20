import { useState, type FormEvent } from "react";
import { ApiError, request } from "../lib/api";
import { Field } from "../components/ui";

export function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await request<{ ok: boolean }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "E-mail ou senha inválidos." : (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center px-5">
      <form onSubmit={submit} className="w-full max-w-sm grid gap-4">
        <h1 className="display text-4xl font-medium m-0">Steady AI Company</h1>
        <p className="text-muted m-0">Entre com a conta do proprietário configurada no servidor.</p>
        <Field label="E-mail">
          <input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required />
        </Field>
        <Field label="Senha">
          <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        {error && <p role="alert" className="m-0" style={{ color: "var(--color-down)" }}>{error}</p>}
        <button className="btn btn-primary" disabled={busy || !email.trim() || !password}>{busy ? "Verificando…" : "Entrar"}</button>
      </form>
    </main>
  );
}
