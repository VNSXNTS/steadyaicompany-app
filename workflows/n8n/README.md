# Workflows n8n

`market-hunter-mineracao.json`: minera a Biblioteca de Anúncios dos EUA via Apify, ranqueia por sinais
de escala e gera rascunhos de criativos com a API do Claude. Importe em Workflows > Import from file.
Requer APIFY_TOKEN, ANTHROPIC_API_KEY e uma planilha Google (veja a nota dentro do workflow).

Os demais workflows do prompt (CEO, Strategy, Product Studio, CFO, Telegram, Error Handler) ainda NÃO existem.
Quando forem criados, devem chamar a API do backend (`/tasks`, `/approvals`) com o header `X-API-Key`.
