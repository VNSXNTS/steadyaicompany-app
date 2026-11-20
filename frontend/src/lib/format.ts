// Valores monetários chegam em centavos de dólar (o produto vende nos EUA).
const usdFmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" });

export const usd = (cents: number) => usdFmt.format(cents / 100);
export const usdFromDollars = (dollars: number) => usdFmt.format(dollars);
export const percent = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
export const int = (n: number) => n.toLocaleString("pt-BR");

export const dateTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

export const shortDay = (iso: string) =>
  new Date(iso + "T12:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });

/** Converte "12,50" ou "12.50" em centavos. Retorna null se não for um valor válido. */
export function toCents(input: string): number | null {
  const s = input.trim().replace(/\s/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return null;
  return Math.round(parseFloat(s) * 100);
}

export const taskStatusLabel: Record<string, string> = {
  pending: "Pendente",
  running: "Em execução",
  awaiting_approval: "Aguardando aprovação",
  completed: "Concluída",
  failed: "Falhou",
  cancelled: "Cancelada",
};

export const productStatusLabel: Record<string, string> = {
  draft: "Rascunho", in_review: "Em revisão", approved: "Aprovado", published: "Publicado",
};

export const actionLabel: Record<string, string> = {
  spend_money: "Gastar dinheiro",
  publish_paid_ads: "Publicar anúncios pagos",
  activate_campaign: "Ativar campanha",
  make_payment: "Fazer pagamento",
  change_price: "Alterar preço",
  issue_refund: "Emitir reembolso",
  send_sensitive_communication: "Enviar comunicação sensível",
  publish_commercial_change: "Publicar alteração comercial",
  delete_data: "Excluir dados",
  irreversible_action: "Executar ação irreversível",
};

export const eventLabel: Record<string, string> = {
  created: "criada",
  started: "iniciada",
  completed: "concluída",
  failed: "falhou",
  retry_scheduled: "nova tentativa agendada",
  awaiting_approval: "aguardando aprovação",
  approved: "aprovada",
  rejected: "rejeitada",
  changes_requested: "alterações solicitadas",
};

export const departmentLabel: Record<string, string> = {
  executive: "Direção", research: "Pesquisa", strategy: "Estratégia", product: "Produto",
  quality: "Qualidade", growth: "Crescimento", creative: "Criação", sales: "Vendas",
  support: "Atendimento", finance: "Finanças",
};
