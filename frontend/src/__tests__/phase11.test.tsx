import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tasks } from "../pages/Tasks";
import { Agents } from "../pages/Agents";
import { Experiments } from "../pages/Experiments";
import { Communication } from "../pages/Communication";
import { ToastProvider } from "../lib/hooks";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
afterEach(() => vi.unstubAllGlobals());
const wrap = (ui: React.ReactElement) => render(<ToastProvider>{ui}</ToastProvider>);

const task = (o = {}) => ({ id: 7, agent_key: "product_creator", department: "product", description: "Gerar planilha", priority: 3, status: "completed",
  action: null, requires_approval: false, depends_on: [], error: null, attempts: 1, created_at: "2026-11-25T10:00:00", due_at: null,
  output: { tool: "steady_payoff_xlsx", result: { note: "x" }, notes: ["Planilha com dados de EXEMPLO"], files: [{ path: "task-7/Steady.xlsx", bytes: 2048, sha256: "a".repeat(64) }] }, ...o });
const pipelines = [
  { key: "new_product", label: "Novo produto", uses_tools: false, steps: [{ agent_key: "growth_strategist", risky: true }] },
  { key: "steady_payoff_build", label: "Steady Payoff", uses_tools: true, steps: [{ agent_key: "cfo", risky: false }] },
];

describe("Tarefas", () => {
  it("mostra arquivos da ferramenta com link de download pelo backend e avisos", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.includes("/ceo/pipelines") ? json(pipelines) : url.includes("/logs") ? json([]) : json([task()]))));
    window.location.hash = "#/tarefas?id=7";
    wrap(<Tasks params={new URLSearchParams("id=7")} />);
    const link = await screen.findByRole("link", { name: /Baixar Steady.xlsx/ });
    expect(link).toHaveAttribute("href", "/tasks/7/files/0");
    expect(screen.getByText(/dados de EXEMPLO/)).toBeInTheDocument();
  });
  it("envia o roteiro escolhido ao pedir plano ao CEO e avisa da etapa de risco", async () => {
    const fetch = vi.fn((url: string, init?: RequestInit) => Promise.resolve(
      url.includes("/ceo/pipelines") ? json(pipelines) : url.includes("/ceo/plan") && init?.method === "POST" ? json([task()], 201) : json([])));
    vi.stubGlobal("fetch", fetch);
    wrap(<Tasks params={new URLSearchParams()} />);
    expect(await screen.findByText(/etapa de risco/)).toBeInTheDocument();
    await userEvent.selectOptions(await screen.findByLabelText(/Roteiro/), "steady_payoff_build");
    expect(screen.queryByText(/etapa de risco/)).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Objetivo/), "planilha de dívidas");
    await userEvent.click(screen.getByRole("button", { name: /criar plano/i }));
    await waitFor(() => {
      const call = fetch.mock.calls.find((c) => String(c[0]).includes("/ceo/plan"))!;
      expect(JSON.parse(call[1]!.body as string)).toEqual({ goal: "planilha de dívidas", pipeline: "steady_payoff_build" });
    });
  });
});

describe("Agentes", () => {
  const agent = { key: "cfo", name: "CFO", department: "finance", role: "r", status: "active", model: "m", can_spend: false, last_run_at: null };
  it("cria tarefa com a ferramenta escolhida e rejeita JSON inválido sem chamar a API", async () => {
    const fetch = vi.fn((url: string, init?: RequestInit) => Promise.resolve(
      url.includes("/agent-tools") ? json([{ agent_key: "cfo", tool: "financial_summary", summary: "Resumo" }, { agent_key: "x", tool: "outra", summary: "y" }])
      : url.includes("/agents-stats") ? json([]) : url.endsWith("/agents") ? json([agent])
      : init?.method === "POST" ? json(task({ id: 9 }), 201) : json([])));
    vi.stubGlobal("fetch", fetch);
    wrap(<Agents />);
    await userEvent.click(await screen.findByRole("button", { name: /nova tarefa/i }));
    await userEvent.type(screen.getByLabelText(/O que o agente/), "resumo do mês");
    const sel = screen.getByLabelText(/Ferramenta \(opcional\)/);
    expect(screen.queryByRole("option", { name: /outra/ })).not.toBeInTheDocument(); // só ferramentas deste agente
    await userEvent.selectOptions(sel, "financial_summary");
    await userEvent.type(screen.getByLabelText(/Entrada da ferramenta/), "[[1,2]");
    await userEvent.click(screen.getByRole("button", { name: /criar tarefa/i }));
    expect(await screen.findByText(/Entrada inválida/)).toBeInTheDocument();
    expect(fetch.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "POST")).toBe(false);
    const box = screen.getByLabelText(/Entrada da ferramenta/);
    await userEvent.clear(box);
    await userEvent.click(screen.getByRole("button", { name: /criar tarefa/i }));
    await waitFor(() => {
      const c = fetch.mock.calls.find((x) => (x[1] as RequestInit | undefined)?.method === "POST")!;
      expect(JSON.parse(c[1]!.body as string)).toMatchObject({ agent_key: "cfo", input: { tool: "financial_summary" } });
    });
  });
});

const exp = (o = {}) => ({ id: 1, name: "Teste A", product_id: null, market: "US", currency: "USD", price_cents: 1900, fee_bps: 290, fee_fixed_cents: 30,
  budget_cap_cents: 5000, max_spend_without_sale_cents: 2000, min_sales_to_decide: 3, status: "draft", outcome: null, outcome_note: "", created_at: "2026-11-25T10:00:00",
  stage: "test", parent_experiment_id: null, event_name: null, event_date: null, creative_angles: [], launch_checklist: {},
  metrics: { spend_cents: 0, sales_count: 0, gross_cents: 0, fees_cents: 0, refunded_cents: 0, net_revenue_cents: 0, profit_cents: 0, roi_percent: null, cpa_cents: null,
    break_even_cpa_cents: 1500, budget_used_percent: 0, days_to_event: null, launch_blockers: ["Checklist pendente: Fiz uma compra de teste"], warnings: [], action: "not_started", reason: "Aguardando aprovação." }, ...o });
const checklist = { items: { checkout_tested: "Fiz uma compra de teste no checkout." }, min_creative_angles: 3 };

describe("Experimentos", () => {
  it("rascunho com pendências: ROI em traço, bloqueios visíveis e botão de pedir aprovação desligado", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.includes("launch-checklist") ? json(checklist) : json([exp()]))));
    wrap(<Experiments />);
    await userEvent.click(await screen.findByRole("button", { name: "1" }));
    expect(await screen.findByText(/Falta para pedir aprovação/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pedir aprovação/i })).toBeDisabled();
    expect(screen.getByText("ROI").nextSibling).toHaveTextContent("—");
    expect(await screen.findByLabelText(/Fiz uma compra de teste/)).toBeInTheDocument();
  });
  it("salva o plano com PUT e envia só o que foi atestado", async () => {
    const fetch = vi.fn((url: string, init?: RequestInit) => Promise.resolve(
      url.includes("launch-checklist") ? json(checklist) : init?.method === "PUT" ? json(exp()) : json([exp()])));
    vi.stubGlobal("fetch", fetch);
    wrap(<Experiments />);
    await userEvent.click(await screen.findByRole("button", { name: "1" }));
    await userEvent.click(await screen.findByLabelText(/Fiz uma compra de teste/));
    await userEvent.click(screen.getByRole("button", { name: /adicionar ângulo/i }));
    await userEvent.type(screen.getByLabelText("Ângulo 1"), "dor");
    await userEvent.type(screen.getByLabelText("Gancho"), "Pare de pagar juros");
    await userEvent.click(screen.getByRole("button", { name: /salvar plano/i }));
    await waitFor(() => {
      const c = fetch.mock.calls.find((x) => (x[1] as RequestInit | undefined)?.method === "PUT")!;
      expect(String(c[0])).toContain("/experiments/1/launch-plan");
      expect(JSON.parse(c[1]!.body as string)).toEqual({ creative_angles: [{ angle: "dor", hook: "Pare de pagar juros" }], checklist: { checkout_tested: true } });
    });
  });
  it("registro de gasto converte dólares em centavos e valor inválido não chama a API", async () => {
    const fetch = vi.fn((url: string, init?: RequestInit) => Promise.resolve(
      url.includes("launch-checklist") ? json(checklist) : init?.method === "POST" ? json({ id: 1, metrics: {} }, 201) : json([exp({ status: "approved" })])));
    vi.stubGlobal("fetch", fetch);
    wrap(<Experiments />);
    await userEvent.click(await screen.findByRole("button", { name: "1" }));
    const posts = () => fetch.mock.calls.filter((x) => (x[1] as RequestInit | undefined)?.method === "POST");
    await userEvent.type(await screen.findByLabelText(/Gasto \(US\$\)/), "abc");
    await userEvent.click(screen.getByRole("button", { name: /registrar gasto/i }));
    expect(posts()).toHaveLength(0);
    await userEvent.clear(screen.getByLabelText(/Gasto \(US\$\)/));
    await userEvent.type(screen.getByLabelText(/Gasto \(US\$\)/), "12,50");
    await userEvent.click(screen.getByRole("button", { name: /registrar gasto/i }));
    await waitFor(() => expect(JSON.parse(posts()[0][1]!.body as string)).toEqual({ amount_cents: 1250 }));
  });
});

describe("Comunicação", () => {
  it("lista vazia mostra orientação e passagem só oferece tarefas concluídas", async () => {
    const fetch = vi.fn((url: string) => Promise.resolve(url.includes("/agents") && !url.includes("messages") ? json([]) : url.includes("status=completed") ? json([]) : json([])));
    vi.stubGlobal("fetch", fetch);
    wrap(<Communication />);
    expect(await screen.findByText("Nenhuma mensagem")).toBeInTheDocument();
    expect(await screen.findByText("Nenhuma tarefa concluída")).toBeInTheDocument();
    expect(fetch.mock.calls.some((c) => String(c[0]).includes("status=completed"))).toBe(true);
  });
  it("passagem chama /handoffs com tarefa de origem e agente", async () => {
    const ag = (k: string) => ({ key: k, name: k.toUpperCase(), department: "x", role: "r", status: "active", model: "m", can_spend: false, last_run_at: null });
    const fetch = vi.fn((url: string, init?: RequestInit) => Promise.resolve(
      init?.method === "POST" ? json({ id: 1, handoff_task_id: 12 }, 201)
      : url.includes("status=completed") ? json([task()]) : url.includes("agent-messages") ? json([]) : json([ag("cfo"), ag("product_creator")])));
    vi.stubGlobal("fetch", fetch);
    wrap(<Communication />);
    await userEvent.selectOptions(await screen.findByLabelText("Tarefa de origem"), "7");
    await userEvent.selectOptions(screen.getByLabelText("Agente que recebe"), "cfo");
    await userEvent.type(screen.getByLabelText(/O que ele deve fazer/), "conferir os números");
    await userEvent.click(screen.getByRole("button", { name: /passar tarefa/i }));
    await waitFor(() => {
      const c = fetch.mock.calls.find((x) => String(x[0]).includes("/handoffs"))!;
      expect(JSON.parse(c[1]!.body as string)).toEqual({ from_task_id: 7, to_agent: "cfo", description: "conferir os números" });
    });
  });
});
