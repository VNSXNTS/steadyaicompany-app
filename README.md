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
- A primeira inicialização cria a conta proprietária a partir de `OWNER_EMAIL` e `OWNER_PASSWORD` (12 a 128 caracteres); usuários e hashes ficam no banco. O hash é **Argon2id** (`argon2-cffi`). Hashes PBKDF2 antigos continuam valendo e são regravados em Argon2id no próximo login correto; o mesmo vale se os parâmetros Argon2 mudarem. Senhas acima de 128 caracteres são recusadas (nunca truncadas).
- O login usa sessão opaca em cookie `HttpOnly`, `SameSite=Strict`, com validade de 12 horas; o token só existe em hash no banco e o logout o apaga no servidor. `AUTH_COOKIE_SECURE=true` deve ser usado atrás de HTTPS.
- **CSRF:** requisições que alteram dados com cookie de sessão exigem o cabeçalho `X-CSRF-Token` (devolvido no login e em `GET /auth/csrf`; derivado da sessão) e, se o navegador mandar `Origin`, ela deve ser o próprio host ou estar em `ALLOWED_ORIGINS`. O painel faz isso sozinho. `X-API-Key` (quando habilitada) não usa cookie e não precisa de token.
- Login, falha, bloqueio e logout são gravados na auditoria (`audit_logs`, ações `auth.*`). A senha nunca é gravada; em falhas nem o e-mail digitado é gravado.
- **Bloqueio de login:** por conta (após 5 tentativas, bloqueio temporário progressivo: 30 s, 60 s, 120 s… no máximo 15 min, valendo de qualquer IP) e por IP (20 falhas em 15 min, bloqueio de até 15 min). As tentativas são contadas antes de verificar a senha, com atualização atômica, então requisições simultâneas não passam do limite. Nenhum bloqueio é permanente. Limite conhecido: quem souber o e-mail do proprietário pode mantê-lo bloqueado por até 15 min por vez. `X-Forwarded-For` só é lido se o proxy estiver em `TRUSTED_PROXIES`.
- **Produção:** `APP_ENV=production` exige `AUTH_COOKIE_SECURE=true` (senão o servidor não inicia, com mensagem clara) e desliga `/docs`, `/redoc` e `/openapi.json`. Em desenvolvimento (padrão) HTTP local continua funcionando.
- `ADMIN_API_KEY` é opcional e vem **vazia** (`X-API-Key` desligada). Só preencha se uma integração precisar dela; o painel não usa. Sem conta proprietária e sem chave de integração, endpoints protegidos falham fechados.
- Todos os segredos do `.env.example` ficam vazios de propósito. Não existe senha padrão.
- **Ainda não existe** (ver `PROJECT_STATUS.md`): CLI segura para criar/recuperar a conta proprietária, limpeza automática de sessões expiradas e de tentativas de login antigas, política de retenção da auditoria, teste manual completo em navegador real.
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
