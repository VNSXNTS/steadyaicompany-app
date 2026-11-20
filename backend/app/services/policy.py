"""Política de autonomia. Ações de risco SEMPRE exigem aprovação humana.

O flag requires_approval não pode ser desligado por quem cria a tarefa:
se a ação está nesta lista, a aprovação é obrigatória.
"""

RISKY_ACTIONS: dict[str, str] = {
    "spend_money": "Gasta dinheiro real.",
    "publish_paid_ads": "Publica anúncios pagos e começa a gastar verba.",
    "activate_campaign": "Ativa uma campanha e começa a gastar verba.",
    "make_payment": "Realiza um pagamento.",
    "change_price": "Altera o preço de um produto à venda.",
    "issue_refund": "Devolve dinheiro a um cliente.",
    "send_sensitive_communication": "Envia comunicação sensível a clientes ou terceiros.",
    "publish_commercial_change": "Publica uma alteração comercial importante.",
    "delete_data": "Exclui dados.",
    "irreversible_action": "Executa uma ação irreversível.",
}


def is_risky(action: str | None) -> bool:
    return bool(action) and action in RISKY_ACTIONS


def consequences_for(action: str) -> str:
    return RISKY_ACTIONS.get(action, "Ação sujeita a aprovação.")
