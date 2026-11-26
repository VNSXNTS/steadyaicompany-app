import { API_BASE, type Task } from "../lib/api";

const kb = (n: number) => (n < 1024 ? `${n} B` : `${(n / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} KB`);

/** Saída de uma ferramenta: resultado, avisos e arquivos. O download passa pelo backend, que confere o SHA-256. */
export function ToolOutput({ task }: { task: Task }) {
  const out = task.output;
  if (!out?.tool) return null;
  return (
    <div className="grid gap-3">
      <div className="text-muted text-sm">Ferramenta: <span className="num">{out.tool}</span> (regras fixas: sem IA, sem rede, sem custo)</div>
      {out.notes && out.notes.length > 0 && (
        <ul aria-label="Avisos da ferramenta" className="m-0 pl-5 text-sm grid gap-1">
          {out.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
      {out.files && out.files.length > 0 && (
        <ul aria-label="Arquivos gerados" className="m-0 pl-0 list-none grid gap-1 text-sm">
          {out.files.map((f, i) => (
            <li key={f.sha256 + i}>
              <a href={`${API_BASE}/tasks/${task.id}/files/${i}`} download>Baixar {f.path.split("/").pop()}</a>{" "}
              <span className="text-muted num">{kb(f.bytes)} · SHA-256 {f.sha256.slice(0, 12)}…</span>
            </li>
          ))}
        </ul>
      )}
      {out.result && (
        <details>
          <summary className="cursor-pointer text-sm text-muted">Resultado completo (JSON)</summary>
          <pre className="whitespace-pre-wrap bg-raised rounded-md p-3 m-0 mt-2 text-sm max-h-80 overflow-auto">{JSON.stringify(out.result, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
