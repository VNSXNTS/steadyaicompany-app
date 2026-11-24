import { useState, type FormEvent } from "react";
import { api, type Costs, type Dashboard, type Product } from "../lib/api";
import { useApi, useToast } from "../lib/hooks";
import { int, toCents, usd, usdFromDollars } from "../lib/format";
import { Statement } from "../components/Statement";
import { ErrorNote, Field, Loading, PageHeader, Section } from "../components/ui";

export function Finance() {
  const toast = useToast();
  const d = useApi(() => api.get<Dashboard>("/dashboard"));
  const c = useApi(() => api.get<Costs>("/costs"));
  const products = useApi(() => api.get<Product[]>("/products"));
  const [sale, setSale] = useState({ product_id: "", gross: "", fee: "", refunded: "" });
  const [exp, setExp] = useState({ category: "ads", description: "", amount: "" });
  const reload = () => { d.reload(); c.reload(); };

  async function addSale(e: FormEvent) {
    e.preventDefault();
    const gross = toCents(sale.gross), fee = sale.fee ? toCents(sale.fee) : 0, ref = sale.refunded ? toCents(sale.refunded) : 0;
    if (gross === null || fee === null || ref === null) { toast("Valor inválido. Use o formato 19,90.", "erro"); return; }
    try {
      await api.post("/sales", { product_id: sale.product_id ? Number(sale.product_id) : null, gross_cents: gross, fee_cents: fee, refunded_cents: ref });
      toast("Venda registrada."); setSale({ product_id: "", gross: "", fee: "", refunded: "" }); reload();
    } catch (err) { toast((err as Error).message, "erro"); }
  }
  async function addExpense(e: FormEvent) {
    e.preventDefault();
    const cents = toCents(exp.amount);
    if (cents === null) { toast("Valor inválido. Use o formato 19,90.", "erro"); return; }
    try {
      await api.post("/expenses", { category: exp.category, description: exp.description, amount_cents: cents });
      toast("Despesa registrada."); setExp({ category: "ads", description: "", amount: "" }); reload();
    } catch (err) { toast((err as Error).message, "erro"); }
  }

  return (
    <>
      <PageHeader title="Financeiro" intro="Vendas e despesas são registradas por você. Os agentes não movimentam dinheiro." />
      <Section title="Demonstrativo">
        {d.loading && !d.data && <Loading />}
        {d.error && <ErrorNote message={d.error} onRetry={d.reload} />}
        {d.data && <div className="max-w-md"><Statement d={d.data} /></div>}
      </Section>
      <Section title="Custo de IA" note="Provedores gratuitos (Ollama local) custam zero. Provedores pagos ficam bloqueados enquanto o orçamento mensal for zero.">
        {c.error && <ErrorNote message={c.error} onRetry={c.reload} />}
        {c.data && (
          <>
            <dl className="grid grid-cols-2 md:grid-cols-5 gap-6 m-0">
              {[["Chamadas no mês", int(c.data.calls)], ["Chamadas com falha", int(c.data.failed_calls)], ["Gasto no mês", usdFromDollars(c.data.spend_usd)], ["Orçamento mensal", usdFromDollars(c.data.budget_usd)], ["Restante no mês", c.data.remaining_usd === null ? "—" : usdFromDollars(c.data.remaining_usd)]].map(([k, v]) => (
                <div key={k}><dt className="text-muted text-sm">{k}</dt><dd className="num display text-2xl m-0">{v}</dd></div>))}
            </dl>
            <p className="text-muted text-sm">Tokens: {int(c.data.prompt_tokens)} de entrada, {int(c.data.completion_tokens)} de saída. Provedores pagos: {c.data.paid_providers_allowed ? "permitidos dentro do orçamento" : "bloqueados"}.</p>
            {c.data.by_model.length === 0 ? (
              <p className="text-muted text-sm">Nenhuma chamada de IA registrada neste mês.</p>
            ) : (
              <table className="w-full text-sm">
                <thead><tr className="text-muted text-left"><th className="font-normal py-1">Provedor / modelo</th><th className="font-normal text-right">Chamadas</th><th className="font-normal text-right">Gasto</th></tr></thead>
                <tbody>{c.data.by_model.map((m) => (
                  <tr key={`${m.provider}/${m.model}`}><td className="py-1">{m.provider} / {m.model}</td><td className="num text-right">{int(m.calls)}</td><td className="num text-right">{usdFromDollars(m.spend_usd)}</td></tr>))}</tbody>
              </table>
            )}
            {c.data.daily.length > 0 && (
              <details className="text-sm"><summary className="cursor-pointer text-muted">Por dia (últimos 30 dias)</summary>
                <table className="w-full mt-2"><tbody>{c.data.daily.map((x) => (
                  <tr key={x.date}><td className="py-0.5">{x.date}</td><td className="num text-right">{int(x.calls)} chamadas</td><td className="num text-right">{usdFromDollars(x.spend_usd)}</td></tr>))}</tbody></table>
              </details>
            )}
          </>
        )}
      </Section>
      <div className="grid md:grid-cols-2 gap-10">
        <Section title="Registrar venda">
          <form onSubmit={addSale} className="grid gap-4">
            <Field label="Produto (opcional)"><select className="input" value={sale.product_id} onChange={(e) => setSale({ ...sale, product_id: e.target.value })}><option value="">—</option>{products.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
            <Field label="Valor bruto (US$)"><input className="input num" inputMode="decimal" value={sale.gross} onChange={(e) => setSale({ ...sale, gross: e.target.value })} required /></Field>
            <Field label="Taxas (US$)"><input className="input num" inputMode="decimal" value={sale.fee} onChange={(e) => setSale({ ...sale, fee: e.target.value })} /></Field>
            <Field label="Reembolsado (US$)"><input className="input num" inputMode="decimal" value={sale.refunded} onChange={(e) => setSale({ ...sale, refunded: e.target.value })} /></Field>
            <div><button className="btn btn-primary">Registrar venda</button></div>
          </form>
        </Section>
        <Section title="Registrar despesa">
          <form onSubmit={addExpense} className="grid gap-4">
            <Field label="Categoria"><select className="input" value={exp.category} onChange={(e) => setExp({ ...exp, category: e.target.value })}>{[["ads", "Anúncios"], ["hosting", "Hospedagem"], ["ai", "IA"], ["tools", "Ferramentas"], ["other", "Outros"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Descrição"><input className="input" value={exp.description} onChange={(e) => setExp({ ...exp, description: e.target.value })} /></Field>
            <Field label="Valor (US$)"><input className="input num" inputMode="decimal" value={exp.amount} onChange={(e) => setExp({ ...exp, amount: e.target.value })} required /></Field>
            <div><button className="btn btn-primary">Registrar despesa</button></div>
          </form>
        </Section>
      </div>
      {d.data && <p className="text-muted text-sm">Total de despesas já registradas: {usd(d.data.expenses_cents)}.</p>}
    </>
  );
}
