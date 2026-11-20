import { useState } from "react";
import { api, type Approval } from "../lib/api";
import { useApi, useToast } from "../lib/hooks";
import { actionLabel, dateTime } from "../lib/format";
import { Empty, ErrorNote, Field, Loading, PageHeader, Section, Status } from "../components/ui";

const decisionLabel: Record<string, string> = { approved: "Aprovada", rejected: "Rejeitada", changes_requested: "Alterações pedidas", pending: "Pendente" };

function Card({ a, onDone }: { a: Approval; onDone: () => void }) {
  const toast = useToast();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function decide(decision: "approved" | "rejected" | "changes_requested") {
    setBusy(true);
    try {
      await api.post(`/approvals/${a.id}/decide`, { decision, note });
      toast(`Aprovação #${a.id}: ${decisionLabel[decision].toLowerCase()}.`);
      onDone();
    } catch (e) { toast((e as Error).message, "erro"); setBusy(false); }
  }
  return (
    <article className="bg-panel border border-line rounded-md p-5 grid gap-3">
      <header className="flex flex-wrap justify-between gap-2">
        <h3 className="display text-lg m-0">{actionLabel[a.action] ?? a.action}</h3>
        <span className="num text-muted text-sm">#{a.id} · {dateTime(a.created_at)}{a.task_id ? <> · <a href={`#/tarefas?id=${a.task_id}`}>tarefa #{a.task_id}</a></> : null}</span>
      </header>
      <p className="m-0"><strong>Consequência:</strong> {a.consequences || "Não informada."}</p>
      <pre className="whitespace-pre-wrap bg-raised rounded-md p-3 m-0 text-sm overflow-auto">{JSON.stringify(a.details, null, 2)}</pre>
      <Field label="Observação (opcional)"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <div className="flex flex-wrap gap-2">
        <button className="btn btn-primary" disabled={busy} onClick={() => decide("approved")}>Aprovar</button>
        <button className="btn" disabled={busy} onClick={() => decide("changes_requested")}>Pedir alterações</button>
        <button className="btn btn-danger" disabled={busy} onClick={() => decide("rejected")}>Rejeitar</button>
      </div>
    </article>
  );
}

export function Approvals() {
  const pending = useApi(() => api.get<Approval[]>("/approvals?status=pending"));
  const all = useApi(() => api.get<Approval[]>("/approvals?status="));
  const reload = () => { pending.reload(); all.reload(); };
  const history = all.data?.filter((a) => a.status !== "pending") ?? [];
  return (
    <>
      <PageHeader title="Aprovações" intro="Nenhuma ação de risco (gastar, publicar, cobrar, apagar) acontece sem a sua decisão." />
      {pending.loading && !pending.data && <Loading what="aprovações" />}
      {pending.error && <ErrorNote message={pending.error} onRetry={pending.reload} />}
      {pending.data && pending.data.length === 0 && <Empty title="Nada esperando por você" hint="Quando um agente pedir para gastar ou publicar, o pedido aparece aqui." />}
      <div className="grid gap-4">{pending.data?.map((a) => <Card key={a.id} a={a} onDone={reload} />)}</div>
      <Section title="Histórico">
        {history.length === 0 ? <p className="text-muted m-0">Nenhuma decisão registrada ainda.</p> : (
          <div className="overflow-x-auto"><table className="tbl">
            <thead><tr><th>#</th><th>Ação</th><th>Decisão</th><th>Observação</th><th>Decidida em</th></tr></thead>
            <tbody>{history.map((a) => (
              <tr key={a.id}><td className="num">{a.id}</td><td>{actionLabel[a.action] ?? a.action}</td><td><Status value={a.status} label={decisionLabel[a.status] ?? a.status} /></td><td className="text-muted">{a.decision_note || "—"}</td><td className="num text-muted whitespace-nowrap">{dateTime(a.decided_at)}</td></tr>
            ))}</tbody>
          </table></div>
        )}
      </Section>
    </>
  );
}
