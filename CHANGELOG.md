# Changelog

## Unreleased
### Correções da revisão do PR nº 1
- **M3** Senhas com **Argon2id** (`argon2-cffi`). Hashes PBKDF2 antigos continuam válidos e são regravados no próximo login correto; hashes Argon2 com parâmetros desatualizados também. Nova dependência: `argon2-cffi`.
- **B5** Senha com no máximo 128 caracteres: acima disso é recusada (422), nunca truncada; verificações de hash simultâneas limitadas a 4 para não esgotar memória.
- **M1** Bloqueio de login por conta (temporário e progressivo, 30 s até 15 min, vale de qualquer IP) e por IP (20 falhas/15 min). Tentativas contadas antes da verificação, com atualização atômica. Nova tabela `account_login_attempts` (criada pelo `create_all`). `X-Forwarded-For` só é lido quando o proxy está em `TRUSTED_PROXIES`.
- **M2** `APP_ENV=production` exige `AUTH_COOKIE_SECURE=true`; sem isso o servidor não inicia, com mensagem clara. Desenvolvimento em HTTP local continua funcionando.
- **B1** `/docs`, `/redoc` e `/openapi.json` desligados em produção; ligados em desenvolvimento.
- **B2** CSRF: cabeçalho `X-CSRF-Token` (derivado da sessão) obrigatório em requisições que alteram dados com cookie, mais checagem de `Origin` (`ALLOWED_ORIGINS`); login e logout incluídos. Novo `GET /auth/csrf`; o login devolve `csrf_token`. O painel envia o token automaticamente (guardado só em memória).
- `create_app()` em `app/main.py`; novas variáveis em `.env.example` e `docker-compose.yml`: `APP_ENV`, `TRUSTED_PROXIES`, `ALLOWED_ORIGINS`.
- Testes: backend 98 (eram 56; +42 em `test_auth_hardening.py`), frontend 13 (eram 11). 5 testes antigos adaptados ao novo comportamento, nenhum removido.
- Pendências futuras (não feitas): CLI segura da conta proprietária, limpeza de sessões expiradas, retenção da auditoria, teste manual em navegador real.

### Autenticação (PR nº 1, versão original)
- Autenticação real do proprietário: contas persistidas, senha com hash PBKDF2-HMAC-SHA256, sessão em cookie HttpOnly com validade de 12 horas, logout e bloqueio de login após cinco falhas em 15 minutos.
- Login do painel por e-mail e senha; a sessão não é mais armazenada no `sessionStorage`.
- `OWNER_EMAIL` e `OWNER_PASSWORD` inicializam a conta proprietária; `ADMIN_API_KEY` continua disponível para clientes de API legados.
- Cookie de sessão agora é `SameSite=Strict` (antes `Lax`).
- Auditoria de autenticação (`auth.login_success`, `auth.login_failed`, `auth.login_blocked`, `auth.logout`) sem senha e, em falhas, sem o e-mail digitado.
- `.env.example`: `ADMIN_API_KEY` e `POSTGRES_PASSWORD` agora vazios (os placeholders anteriores viravam senha padrão); documentados `OWNER_EMAIL`, `OWNER_PASSWORD`, `AUTH_COOKIE_SECURE`.
- Testes: `backend/tests/test_auth_security.py` (17 testes). Backend 56 passam (eram 39 no início do PR); frontend 11 passam.

## 0.2.0 — 2026-11-19
- Painel administrativo (React 19 + TypeScript + Vite + Tailwind): login, visão geral, agentes, tarefas, aprovações, produtos, financeiro, configurações. Servido pelo próprio backend quando `frontend/dist` existe.
- Controle de custo de IA: tabela `ai_usage`, orçamento mensal (`AI_MONTHLY_BUDGET_USD`, padrão 0), provedores pagos bloqueados sem orçamento.
- Modo reduzido: se o provedor de IA cai, tarefas de IA ficam pendentes/falham com mensagem; o resto do sistema segue.
- Provedor Ollama real (`/api/generate`, contagem de tokens, verificação do modelo instalado).
- Logs JSON estruturados com `X-Request-ID`; `/health` público.
- Novos endpoints: `/dashboard/series`, `/agents-stats`, `/costs`, `/providers/status`, `/settings`.
- Dockerfile multi-stage (build do painel + backend) na raiz.
- Testes: 36 no backend, 11 no frontend.
- Corrigido: o painel esperava `/dashboard/series` como lista, mas a API devolve `{days: [...]}` (tela em branco, achado ao rodar de verdade).

## 0.1.0
- Backend FastAPI: 13 agentes, fila de tarefas (prioridade, dependências, tentativas), aprovações obrigatórias para ações de risco, CEO Agent com pipeline `new_product`, financeiro em centavos, autenticação por chave que falha fechada.
- Workflow n8n de mineração (Meta Ads Library via Apify).
