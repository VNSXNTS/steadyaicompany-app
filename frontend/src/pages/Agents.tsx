import { useState, type FormEvent } from "react";
import { api, type Agent, type AgentStat, type Task, type ToolInfo } from "../lib/api";
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
  const tools = useApi(() => api.get<ToolInfo[]>("/agent-tools"));
  const [tool, setTool] = useState("");
  const [inputText, setInputText] = useState("");
  const [inputError, setInputError] = useState("");
  const agentTools = tools.data?.filter((t) => t.agent_key === target?.key) ?? [];
  const closeModal = () => { setTarget(null); setText(""); setPriority(3); setTool(""); setInputText(""); setInputError(""); };

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
    let input: Record<string, unknown> = {};
    if (inputText.trim()) {
      try {
        const parsed: unknown = JSON.parse(inputText);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("não é um objeto");
        input = parsed as Record<string, unknown>;
      } catch {
        setInputError("Entrada inválida: informe um objeto JSON, por exemplo {\"product_task_id\": 3}.");
        return;
      }
    }
    setInputError("");
    if (tool) input = { ...input, tool };
    setBusy(true);
    try {
      const t = await api.post<Task>("/tasks", { agent_key: target.key, description: text, priority, input });
      toast(`Tarefa #${t.id} criada para ${target.name}.`);
      closeModal();
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
            <Field label="Ferramenta (opcional)">
              <select className="input" value={tool} onChange={(e) => setTool(e.target.value)}>
                <option value="">Nenhuma: o agente usa o modelo de IA</option>
                {agentTools.map((t) => <option key={t.tool} value={t.tool}>{t.tool}: {t.summary}</option>)}
              </select>
            </Field>
            {tools.error && <ErrorNote message={tools.error} onRetry={tools.reload} />}
            {tool && <p className="text-sm text-muted m-0">Ferramenta roda por regras fixas, sem IA e sem custo; não executa ações de risco.</p>}
            {tool && <Field label="Entrada da ferramenta (JSON, opcional)"><textarea className="input num" rows={3} value={inputText} onChange={(e) => setInputText(e.target.value)} placeholder='{"product_task_id": 3}' /></Field>}
            {inputError && <ErrorNote message={inputError} />}
            <Field label="Prioridade (1 = urgente, 5 = baixa)">
              <select className="input" value={priority} onChange={(e) => setPriority(Number(e.target.value))}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</select>
            </Field>
            <div className="flex gap-2 justify-end">
              <button type="button" className="btn" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" disabled={busy}>{busy ? "Criando…" : "Criar tarefa"}</button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
