import { useState, type FormEvent } from "react";
import { api, type Agent, type AgentStat, type Task } from "../lib/api";
import { useApi, useToast } from "../lib/hooks";
import { dateTime, departmentLabel, int } from "../lib/format";
import { Empty, ErrorNote, Field, Loading, PageHeader, Status } from "../components/ui";

export function Agents() {
  const toast = useToast();
  const agents = useApi(() => api.get<Agent[]>("/agents"));
  const stats = useApi(() => api.get<AgentStat[]>("/agents-stats"));
  const [target, setTarget] = useState<Agent | null>(null);
  const [text, setText] = useState("");
  const [priority, setPriority] = useState(3);
  const [busy, setBusy] = useState(false);

  async function toggle(a: Agent) {
    try {
      await api.post<Agent>(`/agents/${a.key}/${a.status === "active" ? "pause" : "activate"}`);
      toast(a.status === "active" ? `${a.name} pausado.` : `${a.name} ativado.`);
      agents.reload();
    } catch (e) { toast((e as Error).message, "erro"); }
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!target) return;
    setBusy(true);
    try {
      const t = await api.post<Task>("/tasks", { agent_key: target.key, description: text, priority });
      toast(`Tarefa #${t.id} criada para ${target.name}.`);
      setTarget(null); setText(""); setPriority(3);
      stats.reload();
    } catch (err) { toast((err as Error).message, "erro"); }
    finally { setBusy(false); }
  }

  const stat = (k: string) => stats.data?.find((s) => s.agent_key === k);

  return (
    <>
      <PageHeader title="Agentes" intro="O CEO coordena os especialistas. Um agente pausado não recebe nem executa tarefas." />
      {agents.loading && !agents.data && <Loading what="agentes" />}
      {agents.error && <ErrorNote message={agents.error} onRetry={agents.reload} />}
      {agents.data && agents.data.length === 0 && <Empty title="Nenhum agente cadastrado" hint="Os agentes são criados ao iniciar o servidor." />}
      {agents.data && agents.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="tbl">
            <thead><tr><th>Agente</th><th>Departamento</th><th>Estado</th><th className="text-right">Pendentes</th><th className="text-right">Concluídas</th><th className="text-right">Falhas</th><th>Última execução</th><th></th></tr></thead>
            <tbody>
              {agents.data.map((a) => {
                const s = stat(a.key);
                return (
                  <tr key={a.key}>
                    <td><div className="font-medium">{a.name}</div><div className="text-muted text-sm max-w-xs">{a.role}</div></td>
                    <td>{departmentLabel[a.department] ?? a.department}</td>
                    <td><Status value={a.status} label={a.status === "active" ? "Ativo" : "Pausado"} /></td>
                    <td className="num text-right">{int((s?.pending ?? 0) + (s?.awaiting_approval ?? 0))}</td>
                    <td className="num text-right">{int(s?.completed ?? 0)}</td>
                    <td className="num text-right">{int(s?.failed ?? 0)}</td>
                    <td className="num text-muted whitespace-nowrap">{dateTime(a.last_run_at)}</td>
                    <td className="whitespace-nowrap">
                      <div className="flex gap-2 justify-end">
                        <button className="btn btn-small" onClick={() => setTarget(a)} disabled={a.status !== "active"}>Nova tarefa</button>
                        <a className="btn btn-small no-underline" href={`#/tarefas?agente=${a.key}`}>Histórico</a>
                        <button className="btn btn-small" onClick={() => toggle(a)}>{a.status === "active" ? "Pausar" : "Ativar"}</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {target && (
        <div role="dialog" aria-modal="true" aria-label={`Nova tarefa para ${target.name}`} className="fixed inset-0 z-40 grid place-items-center px-4" style={{ background: "rgb(0 0 0 / .6)" }}>
          <form onSubmit={create} className="bg-panel border border-line rounded-md p-6 w-full max-w-lg grid gap-4">
            <h2 className="display text-xl m-0">Nova tarefa para {target.name}</h2>
            <Field label="O que o agente deve fazer"><textarea className="input" rows={4} value={text} onChange={(e) => setText(e.target.value)} minLength={3} maxLength={4000} required autoFocus /></Field>
            <Field label="Prioridade (1 = urgente, 5 = baixa)">
              <select className="input" value={priority} onChange={(e) => setPriority(Number(e.target.value))}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</select>
            </Field>
            <div className="flex gap-2 justify-end">
              <button type="button" className="btn" onClick={() => setTarget(null)}>Cancelar</button>
              <button className="btn btn-primary" disabled={busy}>{busy ? "Criando…" : "Criar tarefa"}</button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
