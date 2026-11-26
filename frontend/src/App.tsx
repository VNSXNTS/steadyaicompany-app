import { useEffect, useState } from "react";
import { api } from "./lib/api";
import { ToastProvider, useRoute } from "./lib/hooks";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Agents } from "./pages/Agents";
import { Tasks } from "./pages/Tasks";
import { Approvals } from "./pages/Approvals";
import { Products } from "./pages/Products";
import { Finance } from "./pages/Finance";
import { Communication } from "./pages/Communication";
import { Experiments } from "./pages/Experiments";
import { Settings } from "./pages/Settings";

function Routes() {
  const { path, params } = useRoute();
  switch (path) {
    case "/agentes": return <Agents />;
    case "/tarefas": return <Tasks params={params} />;
    case "/comunicacao": return <Communication />;
    case "/experimentos": return <Experiments />;
    case "/aprovacoes": return <Approvals />;
    case "/produtos": return <Products />;
    case "/financeiro": return <Finance />;
    case "/configuracoes": return <Settings />;
    default: return <Dashboard />;
  }
}

export function App() {
  const [authed, setAuthed] = useState(false);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    const out = () => setAuthed(false);
    window.addEventListener("steady:unauthorized", out);
    api.get<{ email: string }>("/auth/me")
      .then(() => setAuthed(true))
      .catch(() => setAuthed(false))
      .finally(() => setChecking(false));
    return () => window.removeEventListener("steady:unauthorized", out);
  }, []);
  async function logout() {
    await api.post<{ ok: boolean }>("/auth/logout");
    setAuthed(false);
  }
  return (
    <ToastProvider>
      {checking ? (
        <main className="min-h-screen grid place-items-center text-muted">Verificando sessão…</main>
      ) : authed ? (
        <Layout onLogout={logout}>
          <Routes />
        </Layout>
      ) : (
        <Login onDone={() => setAuthed(true)} />
      )}
    </ToastProvider>
  );
}
