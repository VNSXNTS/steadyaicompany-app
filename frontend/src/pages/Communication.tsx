import { useState, type FormEvent } from "react";
import { api, type Agent, type AgentMessage, type Task } from "../lib/api";
import { useApi, useToast } from "../lib/hooks";
import { dateTime } from "../lib/format";
import { Empty, ErrorNote, Field, Loading, PageHeader, Section } from "../components/ui";

const kindLabel: Record<string, string> = { message: "Mensagem", handoff: "Passagem de tarefa" };

export function Communication() {
  const toast = useToast();
  const agents = useApi(() => api.get<Agent[]>("/agents"));
  const completed = useApi(() => api.get<Task[]>("/tasks?status=completed"));
  const [filter, setFilter] = useState("");
  const msgs = useApi(() => api.get<AgentMessage[]>(`/agent-messages${filter ? `?agent=${filter}` : ""}`), [filter]);
  const [busy, setBusy] = useState(false);
  const [m, setM] = useState({ from_agent: "", to_agent: "", subject: "", body: "" });
  const [h, setH] = useState({ from_task_id: "", to_agent: "", description: "" });
  const name = (k: string) => agents.data?.find((a) => a.key === k)?.name ?? k;
  const options = agents.data?.map((a) => <option key={a.key} value={a.key}>{a.name}</option>);

  async function send(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post<AgentMessage>("/agent-messages", { ...m, body: m.body });
      toast("Mensagem registrada.");
      setM({ ...m, subject: "", body: "" });
      msgs.reload();
    } catch (err) { toast((err as Error).message, "erro"); }
    finally { setBusy(false); }
  }
  async function handoff(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.post<AgentMessage>("/handoffs", { from_task_id: Number(h.from_task_id), to_agent: h.to_agent, description: h.description });
      toast(`Tarefa #${r.handoff_task_id} criada para ${name(h.to_agent)}.`);
      setH({ ...h, description: "" });
      msgs.reload();
    } catch (err) { toast((err as Error).message, "erro"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Comunicação" intro="Mensagens e passagens de tarefa entre agentes, todas registradas. Uma passagem nunca concede ação de risco e não pode voltar a um agente que já está na cadeia." />
      <Section title="Registro">
        <div className="max-w-xs pb-4">
          <Field label="Filtrar por agente"><select className="input" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="">Todos</option>{options}</select></Field>
        </div>
        {msgs.loading && !msgs.data && <Loading what="mensagens" />}
        {msgs.error && <ErrorNote message={msgs.error} onRetry={msgs.reload} />}
        {msgs.data && msgs.data.length === 0 && <Empty title="Nenhuma mensagem" hint="Envie uma mensagem ou faça uma passagem de tarefa abaixo." />}
        {msgs.data && msgs.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Quando</th><th>Tipo</th><th>De</th><th>Para</th><th>Assunto</th><th>Tarefa</th></tr></thead>
              <tbody>
                {msgs.data.map((x) => (
                  <tr key={x.id}>
                    <td className="num text-muted whitespace-nowrap">{dateTime(x.created_at)}</td>
                    <td>{kindLabel[x.kind] ?? x.kind}{x.hop > 0 ? ` (etapa ${x.hop})` : ""}</td>
                    <td>{name(x.from_agent)}</td><td>{name(x.to_agent)}</td>
                    <td className="max-w-md">{x.subject}{x.body && <div className="text-muted text-sm">{x.body}</div>}</td>
                    <td className="num">{x.handoff_task_id ? <a href={`#/tarefas?id=${x.handoff_task_id}`}>#{x.handoff_task_id}</a> : x.task_id ? `#${x.task_id}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <Section title="Enviar mensagem" note="Só registra e audita; não cria tarefa.">
        <form onSubmit={send} className="grid gap-3 max-w-xl">
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="De"><select className="input" value={m.from_agent} onChange={(e) => setM({ ...m, from_agent: e.target.value })} required><option value="">Escolha…</option>{options}</select></Field>
            <Field label="Para"><select className="input" value={m.to_agent} onChange={(e) => setM({ ...m, to_agent: e.target.value })} required><option value="">Escolha…</option>{options}</select></Field>
          </div>
          <Field label="Assunto"><input className="input" value={m.subject} onChange={(e) => setM({ ...m, subject: e.target.value })} maxLength={150} required /></Field>
          <Field label="Mensagem"><textarea className="input" rows={3} value={m.body} onChange={(e) => setM({ ...m, body: e.target.value })} maxLength={4000} /></Field>
          <div><button className="btn" disabled={busy}>Enviar mensagem</button></div>
        </form>
      </Section>
      <Section title="Passar uma tarefa concluída a outro agente" note="Só tarefas concluídas podem originar uma passagem.">
        {completed.data && completed.data.length === 0 ? <Empty title="Nenhuma tarefa concluída" hint="Execute uma tarefa antes de passá-la adiante." /> : (
          <form onSubmit={handoff} className="grid gap-3 max-w-xl">
            <Field label="Tarefa de origem"><select className="input" value={h.from_task_id} onChange={(e) => setH({ ...h, from_task_id: e.target.value })} required><option value="">Escolha…</option>{completed.data?.map((t) => <option key={t.id} value={t.id}>#{t.id} · {name(t.agent_key)} · {t.description.slice(0, 50)}</option>)}</select></Field>
            <Field label="Agente que recebe"><select className="input" value={h.to_agent} onChange={(e) => setH({ ...h, to_agent: e.target.value })} required><option value="">Escolha…</option>{options}</select></Field>
            <Field label="O que ele deve fazer"><textarea className="input" rows={3} value={h.description} onChange={(e) => setH({ ...h, description: e.target.value })} minLength={3} maxLength={4000} required /></Field>
            <div><button className="btn btn-primary" disabled={busy}>Passar tarefa</button></div>
          </form>
        )}
        {completed.error && <ErrorNote message={completed.error} onRetry={completed.reload} />}
      </Section>
    </>
  );
}
