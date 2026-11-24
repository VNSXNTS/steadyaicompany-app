import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Login } from "../pages/Login";
import { Dashboard } from "../pages/Dashboard";
import { Approvals } from "../pages/Approvals";
import { Finance } from "../pages/Finance";
import { ToastProvider } from "../lib/hooks";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

const emptyDash = { agents_active: 13, agents_total: 13, tasks_running: 0, tasks_pending: 0, approvals_needed: 0, products_developed: 0, products_published: 0, sales_count: 0, gross_revenue_cents: 0, fees_cents: 0, refunds_cents: 0, net_revenue_cents: 0, expenses_cents: 0, profit_cents: 0, margin_percent: null, roi_percent: null, recent_activity: [] };
// mesmo formato que o backend devolve em GET /dashboard/series
const emptySeries = { days: Array.from({ length: 30 }, (_, i) => ({ date: `2026-11-${String(i + 1).padStart(2, "0")}`, net_revenue_cents: 0, expenses_cents: 0, tasks_completed: 0 })) };

describe("Login", () => {
  it("mostra erro com senha errada e não guarda a senha no navegador", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "x" }, 401)));
    const done = vi.fn();
    render(<Login onDone={done} />);
    await userEvent.type(screen.getByLabelText(/e-mail/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/senha/i), "errada");
    await userEvent.click(screen.getByRole("button", { name: /entrar/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha inválidos");
    expect(done).not.toHaveBeenCalled();
    expect(sessionStorage.length).toBe(0);
  });
  it("envia credenciais e entra quando o servidor aceita", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ ok: true }));
    vi.stubGlobal("fetch", fetch);
    const done = vi.fn();
    render(<Login onDone={done} />);
    await userEvent.type(screen.getByLabelText(/e-mail/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/senha/i), "correta");
    await userEvent.click(screen.getByRole("button", { name: /entrar/i }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ email: "owner@example.com", password: "correta" });
    expect(fetch.mock.calls[0][1].credentials).toBe("same-origin");
    expect(sessionStorage.length).toBe(0);
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

describe("Finance: painel de consumo de IA", () => {
  const base = { month_start: "2026-11-01", calls: 0, failed_calls: 0, prompt_tokens: 0, completion_tokens: 0, spend_usd: 0, budget_usd: 0, budget_used_percent: null, paid_providers_allowed: false, manual_ai_expenses_cents: 0, remaining_usd: null, by_provider: [], by_model: [], daily: [] };
  const serve = (costs: unknown) => vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url.includes("/costs")) return Promise.resolve(json(costs));
    if (url.includes("/products")) return Promise.resolve(json([]));
    return Promise.resolve(json(emptyDash));
  }));

  it("sem orçamento nem chamadas: restante em traço e aviso de vazio, sem inventar valores", async () => {
    serve(base);
    render(<ToastProvider><Finance /></ToastProvider>);
    expect(await screen.findByText(/Nenhuma chamada de IA registrada neste mês/)).toBeInTheDocument();
    expect(screen.getByText("Restante no mês").nextElementSibling).toHaveTextContent("—");
    expect(screen.getByText(/Provedores pagos: bloqueados/)).toBeInTheDocument();
  });

  it("mostra gasto por modelo, restante do orçamento e o detalhe por dia", async () => {
    serve({ ...base, calls: 2, spend_usd: 0.0021, budget_usd: 5, remaining_usd: 4.9979, paid_providers_allowed: true,
      by_model: [{ provider: "claude", model: "m-1", calls: 2, spend_usd: 0.0021 }], daily: [{ date: "2026-11-24", calls: 2, spend_usd: 0.0021 }] });
    render(<ToastProvider><Finance /></ToastProvider>);
    expect(await screen.findByText("claude / m-1")).toBeInTheDocument();
    expect(screen.getByText(/permitidos dentro do orçamento/)).toBeInTheDocument();
    expect(screen.getByText("2026-11-24")).toBeInTheDocument();
    expect(screen.getByText("Restante no mês").nextElementSibling).not.toHaveTextContent("—");
  });
});
