# Changelog

## Unreleased
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
