import { shortDay, usd } from "../lib/format";
import type { SeriesDay } from "../lib/api";

/** Receita líquida e despesas por dia. Dados reais do banco; sem dados, mostra um aviso e nenhuma barra. */
export function DailyBars({ days }: { days: SeriesDay[] }) {
  const max = Math.max(1, ...days.flatMap((d) => [d.net_revenue_cents, d.expenses_cents]));
  const hasData = days.some((d) => d.net_revenue_cents !== 0 || d.expenses_cents !== 0);
  const W = 640, H = 220, padL = 8, padB = 24, padT = 8;
  const innerW = W - padL, innerH = H - padB - padT;
  const slot = innerW / Math.max(1, days.length);
  const bar = Math.max(2, Math.min(10, slot / 2.6));
  const y = (v: number) => padT + innerH - (Math.max(0, v) / max) * innerH;

  return (
    <figure className="m-0">
      <div className="flex gap-5 text-sm text-muted mb-2">
        <span className="inline-flex items-center gap-2"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--color-up)" }} />Receita líquida</span>
        <span className="inline-flex items-center gap-2"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--color-warn)" }} />Despesas</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Receita líquida e despesas por dia nos últimos 30 dias" className="w-full h-auto">
        <line x1={padL} x2={W} y1={padT + innerH} y2={padT + innerH} stroke="var(--color-line)" />
        {hasData &&
          days.map((d, i) => {
            const cx = padL + slot * i + slot / 2;
            const rev = y(d.net_revenue_cents), exp = y(d.expenses_cents);
            return (
              <g key={d.date}>
                <title>{`${shortDay(d.date)}: receita líquida ${usd(d.net_revenue_cents)}, despesas ${usd(d.expenses_cents)}`}</title>
                {d.net_revenue_cents > 0 && <rect className="rise" x={cx - bar - 1} width={bar} y={rev} height={padT + innerH - rev} rx={1.5} fill="var(--color-up)" />}
                {d.expenses_cents > 0 && <rect className="rise" x={cx + 1} width={bar} y={exp} height={padT + innerH - exp} rx={1.5} fill="var(--color-warn)" />}
              </g>
            );
          })}
        {days.length > 0 && (
          <>
            <text x={padL} y={H - 6} fontSize="12" fill="var(--color-muted)">{shortDay(days[0].date)}</text>
            <text x={W} y={H - 6} fontSize="12" fill="var(--color-muted)" textAnchor="end">{shortDay(days[days.length - 1].date)}</text>
          </>
        )}
      </svg>
      {!hasData && <figcaption className="text-muted text-sm mt-1">Nenhuma venda nem despesa nos últimos {days.length} dias.</figcaption>}
    </figure>
  );
}
