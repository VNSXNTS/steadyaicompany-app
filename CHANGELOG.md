# Changelog

## Unreleased
### Fase 12 — Telegram
- `app/services/telegram_bot.py`: bot por long polling (`python -m app.services.telegram_bot`), avisos de aprovação pendente (uma vez por aprovação) e comandos `/pendentes /ver /aprovar /confirmar /rejeitar /alterar /id`. Aprovar exige código de uso único (2 min, preso a usuário e aprovação); usa o mesmo `decide_approval` do painel.
- Falha fechada: sem token o bot não roda; sem `TELEGRAM_ALLOWED_USER_IDS` ignora todos; só conversa privada. Token fora de log, erro e auditoria. `/settings` mostra o estado sem segredos. `docs/TELEGRAM.md`.
- Testes: +45 em `test_telegram.py`.
### Fase 11 — Painel completo
- Backend: `GET /agent-tools`, `GET /ceo/pipelines` (com flag `risky` por etapa), `GET /tasks/{id}/files/{index}` (caminho só do registro da tarefa; recusa com 409 arquivo ausente, fora de `ARTIFACTS_DIR` ou com SHA-256 diferente), `GET /experiments/launch-checklist`. Três ferramentas ganharam descrição.
- Painel: resultado de ferramenta e download na tarefa; ferramenta e entrada JSON ao criar tarefa; seletor de roteiro do CEO; telas Comunicação e Experimentos.
- Testes: +13 backend, +10 frontend.
### Fase 10 — n8n: webhooks autenticados e workflows
- Migração `0005` (tabela `webhook_receipts`), `app/api/webhooks.py`: `POST /webhooks/n8n/tasks`, `GET /webhooks/n8n/tasks/{id}`, `GET /webhooks/n8n/report`, `GET /webhooks/n8n/approvals/pending`.
- Segredo próprio `N8N_WEBHOOK_SECRET` (32+ caracteres, comparação em tempo constante; sem ele os webhooks respondem 503). O `X-API-Key`, o cookie do painel e o segredo do n8n não se substituem.
- Idempotência por `Idempotency-Key` (chave única no banco): reenvio do n8n não duplica tarefa. Sem `action` (recusada com 422), campo reservado `handoff` removido, `input` limitado a 20.000 caracteres, n8n só enxerga tarefas criadas por webhook.
- 4 workflows importáveis em `workflows/n8n/` (relatório diário, aviso de aprovações, criativos, ofertas), `docs/N8N.md`.
- Testes: +23 de webhooks e migração, +28 de validação dos workflows.
### Fase 9 — Provedores de IA, guarda de orçamento e painel de consumo
- `ClaudeProvider` e `GeminiProvider` (pagos). Só rodam com chave, modelo e preços por milhão de tokens informados; custo = tokens × preço, arredondado para cima; chave só em cabeçalho, nunca em URL, log, erro ou tarefa.
- Guarda de orçamento reforçada: além de "gasto >= orçamento", bloqueia a chamada cujo PIOR caso (prompt estimado + `AI_MAX_OUTPUT_TOKENS`) estouraria o orçamento. Provedor mal configurado também fica bloqueado, sem consumir tentativas.
- `LLM_FALLBACK_PROVIDER=ollama`: reserva gratuita quando o pago está bloqueado (registrada no log da tarefa); `mock` e provedores pagos são recusados como reserva.
- `GET /costs` ganhou `remaining_usd`, `by_model` e `daily`; tela Financeiro mostra restante, gasto por modelo e por dia. `GET /settings` mostra o estado de Claude/Gemini sem expor chaves.
- `backend/scripts/check_ollama.py` para você conferir o Ollama real. `.env.example` com os novos campos vazios (leitura tolerante a vazio).
- Testes: +28 backend (`test_ai_providers.py`), +2 frontend.
### Fase 8 — Comunicação entre agentes
- Migração `0004` (tabela `agent_messages`), `app/services/communication.py` e endpoints `POST /agent-messages`, `POST /handoffs`, `GET /agent-messages` (filtros `agent`, `task_id`, `kind`).
- Handoff cria uma tarefa normal para o agente de destino, dependente da tarefa de origem (que precisa estar concluída), com log nas duas tarefas e entrada na auditoria. Não concede `action` (nenhum atalho em torno da política de aprovação).
- Travas contra loop: nunca para si mesmo, nunca para agente já presente na cadeia (A→B→A), profundidade máxima 5; a cadeia fica em `input.handoff` e o sistema a sobrescreve (não dá para forjar).
- Testes: +19 em `test_communication.py`, +1 de migração.
### Fase 7 — 3º lote de ferramentas
- Creative Director `creative_check`, Growth Strategist `growth_math`, Customer Success `refund_followup`, Social Media Manager `content_calendar`, Product Architect `product_spec_check` em `agent_tools.py`. Sem IA, rede ou custo; nada é publicado, enviado ou gasto. Cada uma declara o que não sabe.
- Testes: +11 em `test_agent_tools_3.py`.
### Fase 7 — CEO com roteiro de ferramentas
- Novo roteiro opt-in `steady_payoff_build` em `ceo.py` (`POST /ceo/plan` com `pipeline`): Product Creator → Quality Guardian → Sales Manager e CFO. Sem IA, rede, custo ou etapa de risco; `new_product` inalterado.
- `GET /ceo/report` ganhou `quality_rejected_tasks` e `quality_gap_tasks`, e `attention_needed` considera ambos.
- Testes: +6 em `test_ceo_tools.py`.
### Fase 7 — 2º lote de ferramentas
- Chief Strategy Officer `experiment_review`, Sales Manager `sales_report`, Competitor Analyst `offer_comparison` em `agent_tools.py`. Sem IA, rede ou custo; só leem dados registrados ou informados na tarefa e declaram o que não sabem.
- Testes: +17 em `test_agent_tools_2.py`.
### Fase 7 — 1º lote de ferramentas reais dos agentes
- `app/services/agent_tools.py`: CFO (`financial_summary`), Product Creator (`steady_payoff_xlsx`) e Quality Guardian (`review_xlsx`). Sem IA, rede ou custo. Tarefas pedem a ferramenta com `input.tool`; sem isso o comportamento anterior (provedor de IA) é o mesmo.
- Arquivos gerados ficam em `ARTIFACTS_DIR` (padrão `storage/artifacts`) e são rastreáveis pela saída da tarefa (caminho relativo, bytes, SHA-256); ação auditada (`tool_run`).
- Nova dependência: `openpyxl`. Recálculo de fórmulas usa o LibreOffice quando existe; sem ele o revisor declara a lacuna.
- Testes: +12 em `test_agent_tools.py`.
- Validar antes de escalar (Fase 16b, antecipada): `PUT /experiments/{id}/launch-plan` (3+ ângulos de criativo e checklist atestado pelo proprietário; bloqueia `request-approval`), evento sazonal (`event_name`/`event_date`, `days_to_event`, aviso, `stop` quando a data passa sem evidência), `POST /experiments/{id}/scale` (só de experimento validado, rascunho, nova aprovação, teto maior, uma escala aberta por vez). Migração `0003`. Order bump NÃO implementado. O sistema não gasta nem publica nada; o checklist não é verificado no mundo real.
- Correções da revisão do PR nº 4: aprovar um experimento revalida o plano e a recomendação (STOP bloqueia a aprovação, que segue pendente; rejeitar/pedir alterações não são bloqueados; auditoria do bloqueio e da revalidação); checklist estritamente booleano (`"yes"` e `1` são recusados); ângulo e gancho normalizados com `strip` (vazio ou só espaços é recusado). `policy.py` e a migração `0003` não mudaram.
- Testes: `test_validacao_escala.py` (49) + 1 em `test_migrations.py`; helper de `test_experiments.py` agora completa o plano de lançamento. Backend: 143 passam e 3 pulam em SQLite; 146 passam em PostgreSQL 16.
- Experimentos de validação de oferta (Fase 16a, antecipada): `POST/GET /experiments`, aprovação (`activate_campaign`), registro de gasto e vendas, métricas (CPA, CPA de equilíbrio, líquida, lucro, ROI `null` sem base) e recomendação por regras; `validated` só se as regras permitirem. Migração `0002`. O sistema não gasta nem publica anúncios. Mercado e moeda obrigatórios, sem padrão (primeiro teste: EUA/USD, decisão do proprietário). Só API.
- Testes: `test_experiments.py` (24). Backend: 93 passam e 3 pulam em SQLite; 96 passam em PostgreSQL. Dashboard continua de uma moeda só.
- Banco (Fase 3): Alembic com migração inicial `0001` (idempotente: adota bancos v0.2 sem perda de dados); o backend migra ao iniciar e `create_all` deixou de ser usado.
- PostgreSQL 16 testado de verdade (migração e suíte inteira). Variável `TEST_DATABASE_URL` para rodar os testes em PostgreSQL (separada de `DATABASE_URL` de propósito).
- Backup e restauração: `python -m app.database.backup backup|verify|restore` para SQLite e PostgreSQL; `restore` exige `--yes` e guarda o estado anterior; arquivos com permissão 600; `docs/BANCO.md`.
- Testes: `test_migrations.py` (7) e `test_backup.py` (8). Backend: 68 passam e 3 pulam em SQLite; 71 passam em PostgreSQL. `docker compose` NÃO foi testado.
- `test_settings_hide_secrets` passou a esperar o dialeto realmente configurado (antes fixava `sqlite`).
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
