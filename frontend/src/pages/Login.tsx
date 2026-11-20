import { useState, type FormEvent } from "react";
import { ApiError, auth, request, type Dashboard } from "../lib/api";
import { Field } from "../components/ui";

export function Login({ onDone }: { onDone: () => void }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await request<Dashboard>("/dashboard", {}, key.trim());
      auth.set(key.trim());
      onDone();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Chave de acesso incorreta." : (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center px-5">
      <form onSubmit={submit} className="w-full max-w-sm grid gap-4">
        <h1 className="display text-4xl font-medium m-0">Steady AI Company</h1>
        <p className="text-muted m-0">Informe a chave de acesso do administrador (variável ADMIN_API_KEY do servidor).</p>
        <Field label="Chave de acesso">
          <input className="input" type="password" autoComplete="current-password" value={key} onChange={(e) => setKey(e.target.value)} autoFocus required />
        </Field>
        {error && <p role="alert" className="m-0" style={{ color: "var(--color-down)" }}>{error}</p>}
        <button className="btn btn-primary" disabled={busy || !key.trim()}>{busy ? "Verificando…" : "Entrar"}</button>
      </form>
    </main>
  );
}
