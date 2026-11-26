// Cliente da API do backend. A sessão de autenticação é um cookie HttpOnly.

export type Agent = {
  key: string; name: string; department: string; role: string; status: string;
  model: string; can_spend: boolean; last_run_at: string | null;
};
export type AgentStat = {
  agent_key: string; pending: number; running: number; awaiting_approval: number;
  completed: number; failed: number; cancelled: number;
};
export type Task = {
  id: number; agent_key: string; department: string; description: string; priority: number;
  status: string; action: string | null; requires_approval: boolean; depends_on: number[];
  output: TaskOutput | null;
  input?: Record<string, unknown>;
  error: string | null; attempts: number; created_at: string; due_at: string | null;
};
export type TaskFile = { path: string; bytes: number; sha256: string };
export type TaskOutput = {
  text?: string; provider?: string; model?: string;
  tool?: string; result?: Record<string, unknown>; notes?: string[]; files?: TaskFile[];
};
export type ToolInfo = { agent_key: string; tool: string; summary: string };
export type Pipeline = { key: string; label: string; uses_tools: boolean; steps: { agent_key: string; risky: boolean }[] };
export type AgentMessage = {
  id: number; created_at: string; kind: string; from_agent: string; to_agent: string; subject: string; body: string;
  task_id: number | null; handoff_task_id: number | null; parent_id: number | null; hop: number;
};
export type ExperimentMetrics = {
  spend_cents: number; sales_count: number; gross_cents: number; fees_cents: number; refunded_cents: number;
  net_revenue_cents: number; profit_cents: number; roi_percent: number | null; cpa_cents: number | null;
  break_even_cpa_cents: number; budget_used_percent: number; days_to_event: number | null;
  launch_blockers: string[]; warnings: string[]; action: string; reason: string;
};
export type Experiment = {
  id: number; name: string; product_id: number | null; market: string; currency: string; price_cents: number;
  fee_bps: number; fee_fixed_cents: number; budget_cap_cents: number; max_spend_without_sale_cents: number;
  min_sales_to_decide: number; status: string; outcome: string | null; outcome_note: string; created_at: string;
  stage: string; parent_experiment_id: number | null; event_name: string | null; event_date: string | null;
  creative_angles: { angle: string; hook: string }[]; launch_checklist: Record<string, boolean>;
  metrics: ExperimentMetrics | null;
};
export type LaunchChecklist = { items: Record<string, string>; min_creative_angles: number };
export type TaskLog = { id: number; event: string; message: string; created_at: string };
export type Approval = {
  id: number; task_id: number | null; action: string; details: Record<string, unknown>;
  consequences: string; status: string; decision_note: string; created_at: string; decided_at: string | null;
};
export type Product = { id: number; name: string; niche: string; description: string; price_cents: number; status: string };
export type Dashboard = {
  agents_active: number; agents_total: number; tasks_running: number; tasks_pending: number;
  approvals_needed: number; products_developed: number; products_published: number; sales_count: number;
  gross_revenue_cents: number; fees_cents: number; refunds_cents: number; net_revenue_cents: number;
  expenses_cents: number; profit_cents: number; margin_percent: number | null; roi_percent: number | null;
  recent_activity: { task_id: number; event: string; message: string; at: string }[];
};
export type SeriesDay = { date: string; net_revenue_cents: number; expenses_cents: number; tasks_completed: number };
export type Costs = {
  month_start: string; calls: number; failed_calls: number; prompt_tokens: number; completion_tokens: number;
  spend_usd: number; budget_usd: number; budget_used_percent: number | null; paid_providers_allowed: boolean;
  by_provider: { provider: string; calls: number; prompt_tokens: number; completion_tokens: number; spend_usd: number }[];
  manual_ai_expenses_cents: number;
  remaining_usd: number | null;
  by_model: { provider: string; model: string; calls: number; spend_usd: number }[];
  daily: { date: string; calls: number; spend_usd: number }[];
};
export type ProviderStatus = { provider: string; model: string; ok: boolean; detail: string; paid?: boolean };
export type AppSettings = {
  llm_provider: string; llm_fallback_provider?: string | null; ollama_url: string; ollama_model: string; max_task_attempts: number;
  ai_monthly_budget_usd: number; database_dialect: string;   admin_key_configured: boolean; owner_account_configured: boolean;
  integrations: Record<string, string>;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

export function describeDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const where = Array.isArray(d?.loc) ? d.loc.filter((p: unknown) => p !== "body").join(".") : "";
        return where ? `${where}: ${d?.msg ?? "valor inválido"}` : String(d?.msg ?? "valor inválido");
      })
      .join("; ");
  }
  return "Erro inesperado";
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Não foi possível falar com o servidor. Confira se o backend está rodando.");
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* resposta sem JSON */
    }
    if (res.status === 401) window.dispatchEvent(new Event("steady:unauthorized"));
    throw new ApiError(res.status, describeDetail(detail));
  }
  return (await res.json()) as T;
}

export const api = {
  put: <T,>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
};
