import { useEffect, useState, type FormEvent } from "react";
import { api, type Experiment, type LaunchChecklist } from "../lib/api";
import { useApi, useToast } from "../lib/hooks";
import { dateTime, int, percent, toCents, usd } from "../lib/format";
import { Empty, ErrorNote, Field, Loading, PageHeader, Section, Status } from "../components/ui";

export const experimentStatusLabel: Record<string, string> = {
  draft: "Rascunho", pending_approval: "Aguardando aprovação", approved: "Aprovado", rejected: "Rejeitado", closed: "Encerrado",
};
const actionLabel: Record<string, string> = {
  not_started: "Não iniciado", continue: "Continuar", stop: "Parar", validated_candidate: "Candidato a validado", closed: "Encerrado",
};

function Metrics({ x }: { x: Experiment }) {
  const m = x.metrics;
  if (!m) return null;
  const rows: [string, string][] = [
    ["Gasto", usd(m.spend_cents)], ["Vendas", int(m.sales_count)], ["Receita líquida", usd(m.net_revenue_cents)],
    ["Lucro", usd(m.profit_cents)], ["ROI", percent(m.roi_percent)],
    ["CPA", m.cpa_cents === null ? "—" : usd(m.cpa_cents)], ["CPA de equilíbrio", usd(m.break_even_cpa_cents)],
    ["Teto usado", percent(m.budget_used_percent)],
  ];
  return (
    <div className="grid gap-3">
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 m-0">
        {rows.map(([k, v]) => <div key={k}><dt className="text-muted text-sm">{k}</dt><dd className="num m-0">{v}</dd></div>)}
      </dl>
      <p className="m-0"><strong>{actionLabel[m.action] ?? m.action}.</strong> {m.reason} <span className="text-muted text-sm">(regra fixa sobre dados registrados; não garante lucro)</span></p>
      {m.warnings.length > 0 && <ul aria-label="Alertas" className="m-0 pl-5 text-sm grid gap-1">{m.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
    </div>
  );
}

function LaunchPlan({ x, onSaved }: { x: Experiment; onSaved: () => void }) {
  const toast = useToast();
  const list = useApi(() => api.get<LaunchChecklist>("/experiments/launch-checklist"));
  const [angles, setAngles] = useState<{ angle: string; hook: string }[]>(x.creative_angles);
  const [done, setDone] = useState<Record<string, boolean>>(x.launch_checklist);
  useEffect(() => { setAngles(x.creative_angles); setDone(x.launch_checklist); }, [x.id, x.creative_angles, x.launch_checklist]);
  const editable = x.status === "draft";
  async function save() {
    try {
      await api.put<Experiment>(`/experiments/${x.id}/launch-plan`, { creative_angles: angles.filter((a) => a.angle.trim() || a.hook.trim()), checklist: done });
      toast("Plano de lançamento salvo.");
      onSaved();
    } catch (e) { toast((e as Error).message, "erro"); }
  }
  if (list.loading && !list.data) return <Loading what="checklist" />;
  if (list.error) return <ErrorNote message={list.error} onRetry={list.reload} />;
  if (!list.data) return null;
  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted m-0">O sistema não consegue conferir estes itens fora daqui: é você quem atesta que fez cada um.</p>
      <fieldset className="border-0 p-0 m-0 grid gap-2">
        <legend className="text-sm text-muted mb-1">Checklist</legend>
        {Object.entries(list.data.items).map(([k, text]) => (
          <label key={k} className="flex gap-2 items-start text-sm">
            <input type="checkbox" checked={done[k] === true} disabled={!editable} onChange={(e) => setDone({ ...done, [k]: e.target.checked })} />
            {text}
          </label>
        ))}
      </fieldset>
      <div className="grid gap-2">
        <div className="text-sm text-muted">Ângulos de criativo (mínimo {list.data.min_creative_angles}, distintos, cada um com gancho). O texto é seu; o sistema não gera nem publica anúncio.</div>
        {angles.map((a, i) => (
          <div key={i} className="grid sm:grid-cols-[12rem_1fr_auto] gap-2 items-end">
            <Field label={`Ângulo ${i + 1}`}><input className="input" value={a.angle} maxLength={60} disabled={!editable} onChange={(e) => setAngles(angles.map((y, j) => (j === i ? { ...y, angle: e.target.value } : y)))} /></Field>
            <Field label="Gancho"><input className="input" value={a.hook} maxLength={300} disabled={!editable} onChange={(e) => setAngles(angles.map((y, j) => (j === i ? { ...y, hook: e.target.value } : y)))} /></Field>
            {editable && <button type="button" className="btn btn-small" onClick={() => setAngles(angles.filter((_, j) => j !== i))}>Remover</button>}
          </div>
        ))}
        {editable && angles.length < 10 && <div><button type="button" className="btn btn-small" onClick={() => setAngles([...angles, { angle: "", hook: "" }])}>Adicionar ângulo</button></div>}
      </div>
      {editable && <div><button className="btn" onClick={save}>Salvar plano</button></div>}
    </div>
  );
}

function Detail({ x, onChanged }: { x: Experiment; onChanged: () => void }) {
  const toast = useToast();
  const [spend, setSpend] = useState("");
  const [sale, setSale] = useState({ gross: "", fee: "", refund: "" });
  const [note, setNote] = useState("");
  const [scale, setScale] = useState({ name: "", budget: "", nosale: "", min: "" });
  const [busy, setBusy] = useState(false);
  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try { await fn(); toast(ok); }
    catch (e) { toast((e as Error).message, "erro"); }
    finally { setBusy(false); onChanged(); }
  }
  const post = (path: string, body?: unknown) => api.post(`/experiments/${x.id}/${path}`, body);
  function recordSpend(e: FormEvent) {
    e.preventDefault();
    const c = toCents(spend);
    if (!c) return toast("Informe um valor de gasto válido, maior que zero.", "erro");
    run(async () => { await post("spend", { amount_cents: c }); setSpend(""); }, "Gasto registrado.");
  }
  function recordSale(e: FormEvent) {
    e.preventDefault();
    const gross = toCents(sale.gross), fee = sale.fee ? toCents(sale.fee) : 0, refund = sale.refund ? toCents(sale.refund) : 0;
    if (!gross || fee === null || refund === null) return toast("Informe valores válidos (bruto maior que zero).", "erro");
    run(async () => { await post("sales", { gross_cents: gross, fee_cents: fee, refunded_cents: refund }); setSale({ gross: "", fee: "", refund: "" }); }, "Venda registrada.");
  }
  function createScale(e: FormEvent) {
    e.preventDefault();
    const b = toCents(scale.budget), n = toCents(scale.nosale), m = Number(scale.min);
    if (!scale.name.trim() || !b || !n || !Number.isInteger(m) || m < 1) return toast("Preencha nome, valores e mínimo de vendas.", "erro");
    run(async () => { await post("scale", { name: scale.name, budget_cap_cents: b, max_spend_without_sale_cents: n, min_sales_to_decide: m }); }, "Etapa de escala criada em rascunho.");
  }
  const blockers = x.metrics?.launch_blockers ?? [];
  return (
    <div className="bg-panel border border-line rounded-md p-5 grid gap-5">
      <div className="flex flex-wrap justify-between gap-3">
        <h3 className="display text-lg m-0">#{x.id} {x.name}</h3>
        <Status value={x.status} label={experimentStatusLabel[x.status] ?? x.status} />
      </div>
      <p className="m-0 text-sm text-muted">{x.market} · {x.currency} · preço {usd(x.price_cents)} · teto {usd(x.budget_cap_cents)} · parar sem venda em {usd(x.max_spend_without_sale_cents)} · decide com {x.min_sales_to_decide} venda(s) · etapa {x.stage}{x.event_name ? ` · evento ${x.event_name} (${x.event_date ?? "sem data"})` : ""}</p>
      <Metrics x={x} />
      {x.outcome && <p className="m-0">Resultado: <strong>{x.outcome === "validated" ? "validado" : "encerrado sem validar"}</strong>{x.outcome_note ? ` — ${x.outcome_note}` : ""}</p>}
      <div><h4 className="display m-0 mb-2">Plano de lançamento</h4><LaunchPlan x={x} onSaved={onChanged} /></div>
      {x.status === "draft" && (
        <div className="grid gap-2">
          {blockers.length > 0 && <><div className="text-sm text-muted">Falta para pedir aprovação:</div><ul className="m-0 pl-5 text-sm grid gap-1">{blockers.map((b, i) => <li key={i}>{b}</li>)}</ul></>}
          <div><button className="btn btn-primary" disabled={busy || blockers.length > 0} onClick={() => run(() => post("request-approval"), "Aprovação pedida. Decida em Aprovações.")}>Pedir aprovação</button></div>
          <p className="text-sm text-muted m-0">Sem aprovação, o experimento não autoriza nenhum gasto. Salve o plano antes de pedir.</p>
        </div>
      )}
      {x.status === "pending_approval" && <p className="m-0">Aguardando você decidir em <a href="#/aprovacoes">Aprovações</a>.</p>}
      {x.status === "approved" && (
        <div className="grid gap-4">
          <p className="text-sm text-muted m-0">Registre aqui o que aconteceu de verdade (feito por você na plataforma de anúncios e no checkout). Este sistema não gasta nem publica nada.</p>
          <form onSubmit={recordSpend} className="flex flex-wrap items-end gap-3"><Field label="Gasto (US$)"><input className="input" inputMode="decimal" value={spend} onChange={(e) => setSpend(e.target.value)} placeholder="25,00" /></Field><button className="btn" disabled={busy}>Registrar gasto</button></form>
          <form onSubmit={recordSale} className="flex flex-wrap items-end gap-3">
            <Field label="Venda bruta (US$)"><input className="input" inputMode="decimal" value={sale.gross} onChange={(e) => setSale({ ...sale, gross: e.target.value })} /></Field>
            <Field label="Taxas (US$)"><input className="input" inputMode="decimal" value={sale.fee} onChange={(e) => setSale({ ...sale, fee: e.target.value })} /></Field>
            <Field label="Reembolso (US$)"><input className="input" inputMode="decimal" value={sale.refund} onChange={(e) => setSale({ ...sale, refund: e.target.value })} /></Field>
            <button className="btn" disabled={busy}>Registrar venda</button>
          </form>
        </div>
      )}
      {x.status === "approved" && (
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Nota de encerramento"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} /></Field>
          <button className="btn btn-danger" disabled={busy} onClick={() => run(() => post("close", { outcome: "killed", note }), "Experimento encerrado.")}>Encerrar sem validar</button>
          <button className="btn" disabled={busy} onClick={() => run(() => post("close", { outcome: "validated", note }), "Experimento validado.")}>Marcar como validado</button>
        </div>
      )}
      {x.status === "closed" && x.outcome === "validated" && (
        <form onSubmit={createScale} className="grid gap-3">
          <h4 className="display m-0">Criar etapa de escala</h4>
          <p className="text-sm text-muted m-0">Cria um rascunho novo: precisa de checklist e de nova aprovação. Não gasta nada.</p>
          <div className="grid sm:grid-cols-4 gap-3">
            <Field label="Nome"><input className="input" value={scale.name} onChange={(e) => setScale({ ...scale, name: e.target.value })} maxLength={150} /></Field>
            <Field label="Teto (US$)"><input className="input" inputMode="decimal" value={scale.budget} onChange={(e) => setScale({ ...scale, budget: e.target.value })} /></Field>
            <Field label="Parar sem venda em (US$)"><input className="input" inputMode="decimal" value={scale.nosale} onChange={(e) => setScale({ ...scale, nosale: e.target.value })} /></Field>
            <Field label="Mín. de vendas"><input className="input" inputMode="numeric" value={scale.min} onChange={(e) => setScale({ ...scale, min: e.target.value })} /></Field>
          </div>
          <div><button className="btn" disabled={busy}>Criar etapa de escala</button></div>
        </form>
      )}
    </div>
  );
}

const EMPTY = { name: "", market: "", currency: "", price: "", fee_bps: "0", fee_fixed: "0", budget: "", nosale: "", min: "" };

export function Experiments() {
  const toast = useToast();
  const list = useApi(() => api.get<Experiment[]>("/experiments"));
  const [openId, setOpenId] = useState<number | null>(null);
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const selected = list.data?.find((e) => e.id === openId) ?? null;

  async function create(e: FormEvent) {
    e.preventDefault();
    const price = toCents(f.price), budget = toCents(f.budget), nosale = toCents(f.nosale), fixed = toCents(f.fee_fixed);
    const bps = Number(f.fee_bps), min = Number(f.min);
    if (!price || !budget || !nosale || fixed === null || !Number.isInteger(bps) || bps < 0 || bps > 10000 || !Number.isInteger(min) || min < 1)
      return toast("Confira os valores: preço, teto e limite sem venda maiores que zero; taxa em pontos-base (0 a 10000); mínimo de vendas inteiro.", "erro");
    setBusy(true);
    try {
      const x = await api.post<Experiment>("/experiments", {
        name: f.name, market: f.market.toUpperCase(), currency: f.currency.toUpperCase(), price_cents: price,
        fee_bps: bps, fee_fixed_cents: fixed, budget_cap_cents: budget, max_spend_without_sale_cents: nosale, min_sales_to_decide: min,
      });
      toast(`Experimento #${x.id} criado em rascunho.`);
      setF(EMPTY); setOpenId(x.id); list.reload();
    } catch (err) { toast((err as Error).message, "erro"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Experimentos" intro="Teste de oferta com teto de gasto. Nada é gasto por este sistema: você registra o que aconteceu, e começar o teste exige a sua aprovação." />
      <Section title="Lista">
        {list.loading && !list.data && <Loading what="experimentos" />}
        {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
        {list.data && list.data.length === 0 && <Empty title="Nenhum experimento" hint="Crie o primeiro abaixo. Mercado e moeda são decisão sua e não têm padrão." />}
        {list.data && list.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>#</th><th>Nome</th><th>Estado</th><th>Etapa</th><th className="text-right">Gasto</th><th className="text-right">Vendas</th><th>Criado</th></tr></thead>
              <tbody>
                {list.data.map((x) => (
                  <tr key={x.id} aria-selected={x.id === openId}>
                    <td className="num"><button className="btn btn-small" onClick={() => setOpenId(x.id === openId ? null : x.id)}>{x.id}</button></td>
                    <td>{x.name}</td>
                    <td><Status value={x.status} label={experimentStatusLabel[x.status] ?? x.status} /></td>
                    <td>{x.stage}</td>
                    <td className="num text-right">{usd(x.metrics?.spend_cents ?? 0)}</td>
                    <td className="num text-right">{int(x.metrics?.sales_count ?? 0)}</td>
                    <td className="num text-muted whitespace-nowrap">{dateTime(x.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      {selected && <Detail x={selected} onChanged={list.reload} />}
      <Section title="Novo experimento">
        <form onSubmit={create} className="grid gap-3 max-w-2xl">
          <Field label="Nome"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={150} required /></Field>
          <div className="grid sm:grid-cols-3 gap-3">
            <Field label="Mercado (2 letras, ex.: US)"><input className="input" value={f.market} onChange={(e) => setF({ ...f, market: e.target.value })} pattern="[A-Za-z]{2}" required /></Field>
            <Field label="Moeda (3 letras, ex.: USD)"><input className="input" value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })} pattern="[A-Za-z]{3}" required /></Field>
            <Field label="Preço (US$)"><input className="input" inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} required /></Field>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Taxa percentual (pontos-base; 290 = 2,9%)"><input className="input" inputMode="numeric" value={f.fee_bps} onChange={(e) => setF({ ...f, fee_bps: e.target.value })} /></Field>
            <Field label="Taxa fixa por venda (US$)"><input className="input" inputMode="decimal" value={f.fee_fixed} onChange={(e) => setF({ ...f, fee_fixed: e.target.value })} /></Field>
          </div>
          <div className="grid sm:grid-cols-3 gap-3">
            <Field label="Teto de gasto (US$)"><input className="input" inputMode="decimal" value={f.budget} onChange={(e) => setF({ ...f, budget: e.target.value })} required /></Field>
            <Field label="Parar se gastar sem vender (US$)"><input className="input" inputMode="decimal" value={f.nosale} onChange={(e) => setF({ ...f, nosale: e.target.value })} required /></Field>
            <Field label="Vendas mínimas para decidir"><input className="input" inputMode="numeric" value={f.min} onChange={(e) => setF({ ...f, min: e.target.value })} required /></Field>
          </div>
          <div><button className="btn btn-primary" disabled={busy}>Criar experimento</button></div>
        </form>
      </Section>
    </>
  );
}
