import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Login } from "../pages/Login";
import { Dashboard } from "../pages/Dashboard";
import { Approvals } from "../pages/Approvals";
import { ToastProvider } from "../lib/hooks";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

const emptyDash = { agents_active: 13, agents_total: 13, tasks_running: 0, tasks_pending: 0, approvals_needed: 0, products_developed: 0, products_published: 0, sales_count: 0, gross_revenue_cents: 0, fees_cents: 0, refunds_cents: 0, net_revenue_cents: 0, expenses_cents: 0, profit_cents: 0, margin_percent: null, roi_percent: null, recent_activity: [] };
// mesmo formato que o backend devolve em GET /dashboard/series
const emptySeries = { days: Array.from({ length: 30 }, (_, i) => ({ date: `2026-11-${String(i + 1).padStart(2, "0")}`, net_revenue_cents: 0, expenses_cents: 0, tasks_completed: 0 })) };

describe("Login", () => {
  it("mostra erro com chave errada e não guarda a chave", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "x" }, 401)));
    const done = vi.fn();
    render(<Login onDone={done} />);
    await userEvent.type(screen.getByLabelText(/chave de acesso/i), "errada");
    await userEvent.click(screen.getByRole("button", { name: /entrar/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chave de acesso incorreta");
    expect(done).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("steady_admin_key")).toBeNull();
  });
  it("guarda a chave quando o servidor aceita", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(emptyDash)));
    const done = vi.fn();
    render(<Login onDone={done} />);
    await userEvent.type(screen.getByLabelText(/chave de acesso/i), "certa");
    await userEvent.click(screen.getByRole("button", { name: /entrar/i }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(sessionStorage.getItem("steady_admin_key")).toBe("certa");
  });
});

describe("Dashboard", () => {
  it("sem dados não inventa números: margem em traço e aviso de gráfico vazio", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/dashboard/series")) return Promise.resolve(json(emptySeries));
      if (url.includes("/providers/status")) return Promise.resolve(json({ provider: "ollama", model: "llama3", ok: false, detail: "Ollama inacessível." }));
      return Promise.resolve(json(emptyDash));
    }));
    render(<ToastProvider><Dashboard /></ToastProvider>);
    expect(await screen.findByText(/Nenhuma venda nem despesa/)).toBeInTheDocument();
    expect(screen.getByText(/Margem —/)).toBeInTheDocument();
    expect(await screen.findByText(/Modo reduzido/)).toBeInTheDocument();
    expect(screen.getByText(/Ainda não há atividade/)).toBeInTheDocument();
  });
});

describe("Approvals", () => {
  it("aprovar chama o endpoint com a decisão e a observação", async () => {
    const approval = { id: 7, task_id: 3, action: "spend_money", details: { amount: 10 }, consequences: "Gasta US$ 10", status: "pending", decision_note: "", created_at: "2026-11-19T10:00:00", decided_at: null };
    const f = vi.fn((url: string, _init?: RequestInit) => {
      if (url.includes("/decide")) return Promise.resolve(json({ ...approval, status: "approved" }));
      return Promise.resolve(json([approval]));
    });
    vi.stubGlobal("fetch", f);
    sessionStorage.setItem("steady_admin_key", "k");
    render(<ToastProvider><Approvals /></ToastProvider>);
    await userEvent.type(await screen.findByLabelText(/observação/i), "ok pode");
    await userEvent.click(screen.getByRole("button", { name: "Aprovar" }));
    await waitFor(() => {
      const call = (f.mock.calls as unknown as [string, RequestInit][]).find(([u]) => u.includes("/approvals/7/decide"));
      expect(call).toBeTruthy();
      expect(JSON.parse(call![1].body as string)).toEqual({ decision: "approved", note: "ok pode" });
    });
  });
});
