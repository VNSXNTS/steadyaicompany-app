# Workflows n8n

`market-hunter-mineracao.json`: minera a Biblioteca de Anúncios dos EUA via Apify, ranqueia por sinais
de escala e gera rascunhos de criativos com a API do Claude. Importe em Workflows > Import from file.
Requer APIFY_TOKEN, ANTHROPIC_API_KEY e uma planilha Google (veja a nota dentro do workflow).

Fase 10: `relatorio-diario`, `aprovacoes-pendentes`, `criativos-enfileirar` e `ofertas-para-comparacao` chamam
APENAS os webhooks `/webhooks/n8n/*` do backend, com a credencial Header Auth `Steady Webhook` (`X-Webhook-Secret`).
Passo a passo, rotas e limites em `docs/N8N.md`. Nenhum deles usa o `X-API-Key` do painel nem consegue aprovar algo.
Ainda NÃO existem: Telegram (Fase 12), workflow de erro global e mineração ligada à fila do backend.
