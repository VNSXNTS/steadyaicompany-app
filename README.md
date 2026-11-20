# Steady AI Company

Painel + backend que coordenam uma equipe de 13 agentes de IA (CEO + especialistas) para criar e vender produtos digitais, **com você aprovando toda ação de risco**. Estado real do projeto em `PROJECT_STATUS.md`.

## Rodar em desenvolvimento
Requisitos: Python 3.12+, Node 22+.

```bash
cp .env.example .env            # defina ADMIN_API_KEY
# backend
cd backend
pip install -r requirements.txt
ADMIN_API_KEY=sua-chave python -m uvicorn app.main:app --port 8000
# painel (outro terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173, proxy para :8000
```
Para servir o painel pelo backend: `npm run build` e abra http://localhost:8000. Entre com a `ADMIN_API_KEY`.

## Com Docker (PostgreSQL)
Preencha `.env` (ADMIN_API_KEY, POSTGRES_PASSWORD) e rode `docker compose up --build`. Painel em http://localhost:8000. *(Não executado durante o desenvolvimento.)*

## IA e custos
- `LLM_PROVIDER=mock` (padrão): não chama modelo; saída marcada `[MOCK]`.
- `LLM_PROVIDER=ollama`: modelo local gratuito (`OLLAMA_URL`, `OLLAMA_MODEL`).
- Provedores pagos ficam bloqueados enquanto `AI_MONTHLY_BUDGET_USD=0`.
- Se o provedor cair, o sistema entra em modo reduzido: tarefas de IA ficam pendentes e o resto funciona.

## Testes
```bash
cd backend && python -m pytest -q
cd frontend && npm test && npm run build
```

## Observabilidade
Logs JSON no stdout com `request_id`; `GET /health` (público) informa banco e provedor.

## Limitações atuais
Sem Telegram, sem Claude/Gemini, só 1 workflow n8n, sem login com usuários, sem migrações. Não há promessa de funcionamento 24h: isso depende da infraestrutura onde você hospedar.

Workflows n8n: `workflows/n8n/`.
