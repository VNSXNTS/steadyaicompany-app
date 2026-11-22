# Steady AI Company

Painel + backend que coordenam uma equipe de 13 agentes de IA (CEO + especialistas) para criar e vender produtos digitais, **com você aprovando toda ação de risco**. Estado real do projeto em `PROJECT_STATUS.md`.

## Rodar em desenvolvimento
Requisitos: Python 3.12+, Node 22+.

```bash
# backend
cd backend
pip install -r requirements.txt
OWNER_EMAIL=owner@example.com OWNER_PASSWORD='use-uma-senha-com-12-ou-mais-caracteres' python -m uvicorn app.main:app --port 8000
# painel (outro terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173, proxy para :8000
```
Para servir o painel pelo backend: `npm run build` e abra http://localhost:8000. Entre com a conta do proprietário.

## Com Docker (PostgreSQL)
Defina `OWNER_EMAIL`, `OWNER_PASSWORD` (mínimo 12 caracteres) e `POSTGRES_PASSWORD` no `.env` e rode `docker compose up --build`. Painel em http://localhost:8000.

## Autenticação
- A primeira inicialização cria a conta proprietária a partir de `OWNER_EMAIL` e `OWNER_PASSWORD`; usuários e hashes de senha ficam no banco. O hash usa PBKDF2-HMAC-SHA256.
- O login usa sessão opaca em cookie `HttpOnly`, `SameSite=Strict`, com validade de 12 horas; o token só existe em hash no banco e o logout o apaga no servidor. `AUTH_COOKIE_SECURE=true` deve ser usado atrás de HTTPS.
- Login, falha, bloqueio e logout são gravados na auditoria (`audit_logs`, ações `auth.*`). A senha nunca é gravada; em falhas nem o e-mail digitado é gravado.
- Após cinco falhas de login do mesmo IP em 15 minutos, novos logins são bloqueados por 15 minutos. O contador é persistido no banco.
- `ADMIN_API_KEY` é opcional e vem **vazia** (`X-API-Key` desligada). Só preencha se uma integração precisar dela; o painel não usa. Sem conta proprietária e sem chave de integração, endpoints protegidos falham fechados.
- Todos os segredos do `.env.example` ficam vazios de propósito. Não existe senha padrão.
- **Ainda não existe** (ver `PROJECT_STATUS.md`): CLI para criar usuários, bloqueio por usuário (hoje só por IP), token CSRF, hash argon2/bcrypt (hoje PBKDF2, 260.000 rodadas).
- A senha inicial é criada apenas quando a conta não existe; para trocar credenciais, atualize o banco por procedimento administrativo seguro antes de alterar/remover os valores de bootstrap.

## IA e custos
- `LLM_PROVIDER=mock` (padrão): não chama modelo; saída marcada `[MOCK]`.
- `LLM_PROVIDER=ollama`: modelo local gratuito (`OLLAMA_URL`, `OLLAMA_MODEL`).
- Provedores pagos ficam bloqueados enquanto `AI_MONTHLY_BUDGET_USD=0`.
- Se o provedor cair, o sistema entra em modo reduzido: tarefas de IA ficam pendentes e o resto funciona.

## Testes
```bash
cd backend && python -m pytest -q          # 56 testes (última execução: Linux, Python 3.13)
cd frontend && npm ci && npm test && npm run build   # 11 testes + tsc + vite build
```
Se `npm test` acusar "no tests" ou erros de carregamento, apague `node_modules` e rode `npm ci`. No Windows, se o pytest quebrar com `module 'collections' has no attribute 'Callable'`, rode `pip uninstall -y pyreadline`.

## Observabilidade
Logs JSON no stdout com `request_id`; `GET /health` (público) informa banco e provedor.

## Limitações atuais
Sem Telegram, sem Claude/Gemini, só 1 workflow n8n, sem gerenciamento de usuários no painel, sem migrações. Não há promessa de funcionamento 24h: isso depende da infraestrutura onde você hospedar.

Workflows n8n: `workflows/n8n/`.
