import { useState, type FormEvent } from "react";
import { api, type Product } from "../lib/api";
import { useApi, useToast } from "../lib/hooks";
import { productStatusLabel, toCents, usd } from "../lib/format";
import { Empty, ErrorNote, Field, Loading, PageHeader, Section, Status } from "../components/ui";

export function Products() {
  const toast = useToast();
  const list = useApi(() => api.get<Product[]>("/products"));
  const [f, setF] = useState({ name: "", niche: "", description: "", price: "" });
  const [busy, setBusy] = useState(false);

  async function create(e: FormEvent) {
    e.preventDefault();
    const cents = f.price.trim() === "" ? 0 : toCents(f.price);
    if (cents === null) { toast("Preço inválido. Use o formato 19,90.", "erro"); return; }
    setBusy(true);
    try {
      await api.post("/products", { name: f.name, niche: f.niche, description: f.description, price_cents: cents });
      toast("Produto criado como rascunho.");
      setF({ name: "", niche: "", description: "", price: "" }); list.reload();
    } catch (err) { toast((err as Error).message, "erro"); }
    finally { setBusy(false); }
  }
  async function publish(p: Product) {
    try { await api.post(`/products/${p.id}/publish`); toast("Pedido de publicação enviado. Decida em Aprovações."); }
    catch (err) { toast((err as Error).message, "erro"); }
    finally { list.reload(); }
  }

  return (
    <>
      <PageHeader title="Produtos" intro="Publicar um produto sempre passa pela sua aprovação." />
      {list.loading && !list.data && <Loading what="produtos" />}
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {list.data && list.data.length === 0 && <Empty title="Nenhum produto ainda" hint="Cadastre abaixo ou peça um plano ao CEO em Tarefas." />}
      {list.data && list.data.length > 0 && (
        <div className="overflow-x-auto"><table className="tbl">
          <thead><tr><th>Produto</th><th>Nicho</th><th className="text-right">Preço</th><th>Estado</th><th></th></tr></thead>
          <tbody>{list.data.map((p) => (
            <tr key={p.id}>
              <td><div className="font-medium">{p.name}</div><div className="text-muted text-sm max-w-md">{p.description}</div></td>
              <td>{p.niche || "—"}</td><td className="num text-right">{usd(p.price_cents)}</td>
              <td><Status value={p.status} label={productStatusLabel[p.status] ?? p.status} /></td>
              <td className="text-right"><button className="btn btn-small" disabled={p.status === "published" || p.status === "in_review"} onClick={() => publish(p)}>Pedir publicação</button></td>
            </tr>))}</tbody>
        </table></div>
      )}
      <Section title="Novo produto">
        <form onSubmit={create} className="grid gap-4 max-w-xl">
          <Field label="Nome"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={150} required /></Field>
          <Field label="Nicho"><input className="input" value={f.niche} onChange={(e) => setF({ ...f, niche: e.target.value })} /></Field>
          <Field label="Descrição"><textarea className="input" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <Field label="Preço em dólares (ex.: 19,90)"><input className="input num" inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field>
          <div><button className="btn btn-primary" disabled={busy}>Criar produto</button></div>
        </form>
      </Section>
    </>
  );
}
