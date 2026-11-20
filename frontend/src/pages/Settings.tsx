import { api, type AppSettings, type ProviderStatus } from "../lib/api";
import { useApi } from "../lib/hooks";
import { usdFromDollars } from "../lib/format";
import { ErrorNote, Loading, PageHeader, Section, Status } from "../components/ui";

export function Settings() {
  const s = useApi(() => api.get<AppSettings>("/settings"));
  const p = useApi(() => api.get<ProviderStatus>("/providers/status"));
  return (
    <>
      <PageHeader title="Configurações" intro="Somente leitura. Os valores vêm das variáveis de ambiente do servidor (.env); chaves e senhas nunca são exibidas." />
      <Section title="Provedor de IA" actions={<button className="btn btn-small" onClick={p.reload}>Testar agora</button>}>
        {p.loading && !p.data && <Loading />}
        {p.error && <ErrorNote message={p.error} onRetry={p.reload} />}
        {p.data && (
          <p className="m-0"><Status value={p.data.ok ? "completed" : "failed"} label={p.data.ok ? "Disponível" : "Indisponível"} /> — {p.data.provider} / {p.data.model}. {p.data.detail}</p>
        )}
      </Section>
      {s.loading && !s.data && <Loading />}
      {s.error && <ErrorNote message={s.error} onRetry={s.reload} />}
      {s.data && (
        <>
          <Section title="Servidor">
            <dl className="grid grid-cols-[max-content_1fr] gap-x-8 gap-y-2 m-0">
              {[
                ["Provedor de IA", s.data.llm_provider], ["Ollama (URL)", s.data.ollama_url], ["Ollama (modelo)", s.data.ollama_model],
                ["Tentativas por tarefa", String(s.data.max_task_attempts)], ["Orçamento mensal de IA", usdFromDollars(s.data.ai_monthly_budget_usd)],
                ["Banco de dados", s.data.database_dialect], ["Chave de administrador configurada", s.data.admin_key_configured ? "sim" : "não"],
              ].map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="m-0 num">{v}</dd></div>))}
            </dl>
          </Section>
          <Section title="Integrações" note="Estado real de cada integração. “Não implementado” significa que ainda não existe código para ela.">
            <dl className="grid grid-cols-[max-content_1fr] gap-x-8 gap-y-2 m-0">
              {Object.entries(s.data.integrations).map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="m-0">{v}</dd></div>))}
            </dl>
          </Section>
        </>
      )}
    </>
  );
}
