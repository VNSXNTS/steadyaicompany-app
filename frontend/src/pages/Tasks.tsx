import { useState, type FormEvent } from "react";
import { api, type Pipeline, type Task, type TaskLog } from "../lib/api";
import { useApi, useToast } from "../lib/hooks";
import { dateTime, eventLabel, taskStatusLabel } from "../lib/format";
import { ToolOutput } from "../components/ToolOutput";
import { Empty, ErrorNote, Field, Loading, PageHeader, Section, Status } from "../components/ui";

const STATUSES = Object.keys(taskStatusLabel);

function Detail({ task, onChanged }: { task: Task; onChanged: () => void }) {
  const toast = useToast();
  const logs = useApi(() => api.get<TaskLog[]>(`/tasks/${task.id}/logs`), [task.id, task.status]);
  const [busy, setBusy] = useState(false);
  async function act(path: string, ok: string) {
    setBusy(true);
    try { await api.post<Task>(`/tasks/${task.id}/${path}`); toast(ok); }
    catch (e) { toast((e as Error).message, "erro"); }
    finally { setBusy(false); onChanged(); }
  }
  const canRun = task.status === "pending" || task.status === "failed";
  const canCancel = ["pending", "failed", "awaiting_approval"].includes(task.status);
  return (
    <div className="bg-panel border border-line rounded-md p-5 grid gap-4">
      <div className="flex flex-wrap justify-between gap-3">
        <h3 className="display text-lg m-0">Tarefa #{task.id}</h3>
        <div className="flex gap-2">
          <button className="btn btn-small btn-primary" disabled={!canRun || busy} onClick={() => act("run", "Tarefa executada.")}>Executar</button>
          <button className="btn btn-small btn-danger" disabled={!canCancel || busy} onClick={() => act("cancel", "Tarefa cancelada.")}>Cancelar</button>
        </div>
      </div>
      <p className="m-0">{task.description}</p>
      {task.error && <ErrorNote message={task.error} />}
      <ToolOutput task={task} />
      {task.output?.text && (
        <div>
          <div className="text-muted text-sm mb-1">Resultado ({task.output.provider}{task.output.model ? ` · ${task.output.model}` : ""})</div>
          <pre className="whitespace-pre-wrap bg-raised rounded-md p-3 m-0 text-sm max-h-80 overflow-auto">{task.output.text}</pre>
        </div>
      )}
      <div>
        <div className="text-muted text-sm mb-1">Histórico</div>
        {logs.loading && !logs.data ? <Loading what="histórico" /> : logs.error ? <ErrorNote message={logs.error} /> : (
          <ul className="m-0 pl-0 list-none grid gap-1 text-sm">
            {logs.data?.map((l) => <li key={l.id}><span className="num text-muted">{dateTime(l.created_at)}</span> {eventLabel[l.event] ?? l.event}{l.message ? ` — ${l.message}` : ""}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

export function Tasks({ params }: { params: URLSearchParams }) {
  const toast = useToast();
  const agent = params.get("agente") ?? "";
  const [status, setStatus] = useState("");
  const selectedId = Number(params.get("id")) || null;
  const list = useApi(() => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (agent) q.set("agent_key", agent);
    return api.get<Task[]>(`/tasks${q.size ? `?${q}` : ""}`);
  }, [status, agent]);
  const pipelines = useApi(() => api.get<Pipeline[]>("/ceo/pipelines"));
  const [pipeline, setPipeline] = useState("new_product");
  const chosen = pipelines.data?.find((p) => p.key === pipeline);
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);

  async function plan(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const t = await api.post<Task[]>("/ceo/plan", { goal, pipeline });
      toast(`O CEO criou ${t.length} tarefas.`);
      setGoal(""); list.reload();
    } catch (err) { toast((err as Error).message, "erro"); }
    finally { setBusy(false); }
  }
  async function runAll() {
    setBusy(true);
    try {
      const r = await api.post<Task[]>("/ceo/run-all");
      toast(r.length ? `${r.length} tarefas executadas. A fila para onde precisa de aprovação, falha ou ainda não há tarefa liberada.` : "Nenhuma tarefa pronta para executar.");
    } catch (err) { toast((err as Error).message, "erro"); }
    finally { setBusy(false); list.reload(); }
  }
  const selected = list.data?.find((t) => t.id === selectedId) ?? null;

  return (
    <>
      <PageHeader title="Tarefas" intro="Fila de trabalho dos agentes. Ações de risco param em “Aguardando aprovação” até você decidir."
        actions={<button className="btn btn-primary" onClick={runAll} disabled={busy}>Executar fila</button>} />
      <form onSubmit={plan} className="flex flex-wrap items-end gap-3 pb-6">
        <div className="grow min-w-64 max-w-xl"><Field label="Objetivo para o CEO"><input className="input" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Ex.: planilha de quitação de dívidas para o mercado dos EUA" minLength={3} maxLength={500} required /></Field></div>
        <div className="min-w-64 max-w-md"><Field label="Roteiro">
          <select className="input" value={pipeline} onChange={(e) => setPipeline(e.target.value)} disabled={!pipelines.data}>
            {(pipelines.data ?? [{ key: "new_product", label: "Novo produto" } as Pipeline]).map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select></Field></div>
        <button className="btn" disabled={busy}>Criar plano</button>
      </form>
      {pipelines.error && <ErrorNote message={pipelines.error} onRetry={pipelines.reload} />}
      {chosen?.steps.some((st) => st.risky) && <p className="text-sm text-muted m-0 pb-4">Este roteiro tem uma etapa de risco: ela fica em “Aguardando aprovação” até você decidir.</p>}
      <Section title="Fila" actions={
        <div className="flex gap-3 items-end">
          {agent && <a href="#/tarefas" className="text-sm">Limpar filtro de agente ({agent})</a>}
          <Field label="Estado"><select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Todos</option>{STATUSES.map((s) => <option key={s} value={s}>{taskStatusLabel[s]}</option>)}</select></Field>
        </div>}>
        {list.loading && !list.data && <Loading what="tarefas" />}
        {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
        {list.data && list.data.length === 0 && <Empty title="Nenhuma tarefa" hint="Peça um plano ao CEO acima ou crie uma tarefa em Agentes." />}
        {list.data && list.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>#</th><th>Descrição</th><th>Agente</th><th>Prior.</th><th>Estado</th><th>Criada</th></tr></thead>
              <tbody>
                {list.data.map((t) => (
                  <tr key={t.id} aria-selected={t.id === selectedId}>
                    <td className="num"><a href={`#/tarefas?${new URLSearchParams({ ...(agent ? { agente: agent } : {}), id: String(t.id) })}`}>{t.id}</a></td>
                    <td className="max-w-md">{t.description}</td>
                    <td>{t.agent_key}</td>
                    <td className="num">{t.priority}</td>
                    <td><Status value={t.status} label={taskStatusLabel[t.status] ?? t.status} /></td>
                    <td className="num text-muted whitespace-nowrap">{dateTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      {selected && <Detail task={selected} onChanged={list.reload} />}
    </>
  );
}
