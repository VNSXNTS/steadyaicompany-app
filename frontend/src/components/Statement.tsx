import type { Dashboard } from "../lib/api";
import { percent, usd } from "../lib/format";

type Row = { label: string; cents: number; minus?: boolean; total?: boolean; final?: boolean };

/** Demonstrativo no formato contábil: faturamento bruto não é lucro, e a ordem das linhas mostra por quê. */
export function Statement({ d }: { d: Dashboard }) {
  const rows: Row[] = [
    { label: "Receita bruta", cents: d.gross_revenue_cents },
    { label: "Taxas", cents: d.fees_cents, minus: true },
    { label: "Reembolsos", cents: d.refunds_cents, minus: true },
    { label: "Receita líquida", cents: d.net_revenue_cents, total: true },
    { label: "Despesas", cents: d.expenses_cents, minus: true },
    { label: "Lucro", cents: d.profit_cents, final: true },
  ];
  return (
    <div>
      <table className="w-full border-collapse num" aria-label="Demonstrativo de resultado">
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className={r.total ? "border-t border-line" : ""}>
              <th scope="row" className={`text-left py-2 pr-4 ${r.final ? "display text-2xl font-medium pt-4" : r.total ? "font-semibold" : "font-normal text-muted"}`}>
                {r.minus && <span aria-hidden className="mr-2">−</span>}
                {r.label}
              </th>
              <td
                className={`text-right py-2 ${r.final ? "display text-3xl font-medium pt-4" : r.total ? "font-semibold" : ""}`}
                style={r.final ? { color: r.cents < 0 ? "var(--color-down)" : "var(--color-fg)", borderTop: "3px double var(--color-brass)" } : undefined}
              >
                {usd(r.cents)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-muted text-sm mt-4 mb-0">
        Margem {percent(d.margin_percent)} sobre a receita líquida. Retorno sobre despesas {percent(d.roi_percent)}.
        {d.margin_percent === null && " A margem aparece quando houver receita líquida."}
        {d.roi_percent === null && " O retorno aparece quando houver despesas."}
      </p>
    </div>
  );
}
