import { api, type Dashboard as D, type ProviderStatus, type SeriesDay } from "../lib/api";
import { useApi } from "../lib/hooks";
import { dateTime, eventLabel, int } from "../lib/format";
import { Statement } from "../components/Statement";
import { DailyBars } from "../components/Charts";
import { ErrorNote, Loading, PageHeader, Section } from "../components/ui";

export function Dashboard() {
  const d = useApi(() => api.get<D>("/dashboard"));
  const s = useApi(() => api.get<{ days: SeriesDay[] }>("/dashboard/series"));
  const p = useApi(() => api.get<ProviderStatus>("/providers/status"));

  return (
    <>
      <PageHeader title="Visão geral" intro="Números reais do banco de dados. Onde não há registro, o painel mostra zero ou um traço, nunca um valor inventado." />
      {p.data && !p.data.ok && (
        <div role="alert" className="border-l-2 pl-4 py-1 mb-6" style={{ borderColor: "var(--color-warn)" }}>
          <strong>Modo reduzido.</strong> O provedor de IA “{p.data.provider}” não está disponível: {p.data.detail} Tarefas de IA ficam pendentes; o resto do sistema continua funcionando.
        </div>
      )}
      {p.data?.ok && p.data.provider === "mock" && (
        <p className="text-muted mt-0 mb-6">Provedor de IA em modo de teste (mock): as respostas dos agentes são marcadas como [MOCK] e nenhum modelo é chamado.</p>
      )}
      {d.loading && !d.data && <Loading />}
      {d.error && <ErrorNote message={d.error} onRetry={d.reload} />}
      {d.data && (
        <>
          <Section title="Resultado" note="Receita bruta não é lucro: taxas, reembolsos e despesas saem antes.">
            <div className="grid gap-10 lg:grid-cols-[minmax(0,26rem)_1fr] items-start">
              <Statement d={d.data} />
              <div>{s.data ? <DailyBars days={s.data.days} /> : s.error ? <ErrorNote message={s.error} onRetry={s.reload} /> : <Loading what="gráfico" />}</div>
            </div>
          </Section>
          <Section title="Operação">
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-6 m-0">
              {[
                ["Agentes ativos", `${int(d.data.agents_active)} de ${int(d.data.agents_total)}`],
                ["Tarefas em execução", int(d.data.tasks_running)],
                ["Tarefas pendentes", int(d.data.tasks_pending)],
                ["Aprovações esperando você", int(d.data.approvals_needed)],
                ["Produtos desenvolvidos", int(d.data.products_developed)],
                ["Produtos publicados", int(d.data.products_published)],
                ["Vendas registradas", int(d.data.sales_count)],
              ].map(([k, v]) => (
                <div key={k as string}>
                  <dt className="text-muted text-sm">{k}</dt>
                  <dd className="num display text-2xl m-0">{v}</dd>
                </div>
              ))}
            </dl>
          </Section>
          <Section title="Atividade recente">
            {d.data.recent_activity.length === 0 ? (
              <p className="text-muted m-0">Ainda não há atividade. Crie uma tarefa em Agentes ou peça um plano ao CEO em Tarefas.</p>
            ) : (
              <table className="tbl">
                <tbody>
                  {d.data.recent_activity.map((a, i) => (
                    <tr key={i}>
                      <td className="num text-muted whitespace-nowrap">{dateTime(a.at)}</td>
                      <td><a href={`#/tarefas?id=${a.task_id}`}>Tarefa #{a.task_id}</a> {eventLabel[a.event] ?? a.event}</td>
                      <td className="text-muted">{a.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>
        </>
      )}
    </>
  );
}
