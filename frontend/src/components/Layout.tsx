import { useState, type ReactNode } from "react";
import { api, type Dashboard } from "../lib/api";
import { useApi, useRoute } from "../lib/hooks";

const NAV = [
  { to: "/", label: "Visão geral" },
  { to: "/agentes", label: "Agentes" },
  { to: "/tarefas", label: "Tarefas" },
  { to: "/comunicacao", label: "Comunicação" },
  { to: "/experimentos", label: "Experimentos" },
  { to: "/aprovacoes", label: "Aprovações" },
  { to: "/produtos", label: "Produtos" },
  { to: "/financeiro", label: "Financeiro" },
  { to: "/configuracoes", label: "Configurações" },
];

export function Layout({ children, onLogout }: { children: ReactNode; onLogout: () => Promise<void> }) {
  const [logoutError, setLogoutError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const { path } = useRoute();
  const { data } = useApi(() => api.get<Dashboard>("/dashboard"), [path]);
  const pending = data?.approvals_needed ?? 0;
  async function logout() {
    setLoggingOut(true);
    setLogoutError("");
    try {
      await onLogout();
    } catch (err) {
      setLogoutError((err as Error).message);
    } finally {
      setLoggingOut(false);
    }
  }
  return (
    <div className="min-h-screen md:grid md:grid-cols-[15rem_1fr]">
      <nav aria-label="Principal" className="md:sticky md:top-0 md:h-screen md:border-r border-b md:border-b-0 border-line px-4 py-4 md:py-8 flex md:flex-col gap-1 overflow-x-auto">
        <div className="display text-xl md:mb-8 pr-4 md:pr-0 whitespace-nowrap">Steady AI Company</div>
        {NAV.map((n) => {
          const active = path === n.to;
          return (
            <a
              key={n.to}
              href={`#${n.to}`}
              aria-current={active ? "page" : undefined}
              className="px-3 py-2 rounded-md whitespace-nowrap flex items-center justify-between gap-3 no-underline"
              style={{ color: active ? "var(--color-fg)" : "var(--color-muted)", background: active ? "var(--color-raised)" : undefined, boxShadow: active ? "inset 2px 0 0 var(--color-brass)" : undefined }}
            >
              {n.label}
              {n.to === "/aprovacoes" && pending > 0 && (
                <span className="num text-xs px-1.5 rounded" style={{ background: "var(--color-brass)", color: "var(--color-brass-ink)" }}>{pending}</span>
              )}
            </a>
          );
        })}
        {logoutError && <p role="alert" className="text-sm">{logoutError}</p>}
        <button className="btn btn-small md:mt-auto whitespace-nowrap" disabled={loggingOut} onClick={logout}>{loggingOut ? "Saindo…" : "Sair"}</button>
      </nav>
      <main className="px-5 md:px-10 py-8 max-w-6xl w-full">{children}</main>
    </div>
  );
}
