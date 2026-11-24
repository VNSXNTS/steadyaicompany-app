# PROJECT_STATUS — Steady AI Company (v0.2.0 + autenticação em revisão no PR nº 1, 2026-11-21)

Legenda: ✅ funciona e testado · 🟡 parcial · ⬜ não iniciado

## Fases
| Fase | Estado | Observação |
|---|---|---|
| 1 Diagnóstico e arquitetura | 🟡 | Sem acesso ao GitHub nesta sessão; arquitetura documentada neste arquivo e no README. Diagnóstico de repositório existente não foi feito. |
| 2 Estrutura inicial | ✅ | backend/, frontend/, workflows/, Docker, .env.example |
| 3 Banco de dados | 🟡 | SQLAlchemy; SQLite testado. PostgreSQL configurado, **não executado**. Sem Alembic (tabelas criadas no start). |
| 4 Backend e autenticação | 🟡 | **Em revisão (PR nº 1), não mesclada.** Correções da revisão aplicadas e testadas: hash **Argon2id** com migração/rehash no login, bloqueio **por conta e por IP** com atualização atômica, `X-Forwarded-For` só com `TRUSTED_PROXIES`, **CSRF** (token + Origem) integrado ao painel, `APP_ENV=production` exige cookie `Secure` e desliga `/docs`, limite de 128 caracteres de senha. Sessão `HttpOnly` + `SameSite=Strict`, logout que invalida, auditoria sem senha, `X-API-Key` desligada por padrão. **Pendências futuras (não feitas):** CLI segura para criar/recuperar a conta proprietária; limpeza automática de sessões expiradas; política de retenção/limpeza da auditoria; teste manual completo em navegador real. |
| 5 Sistema de tarefas | ✅ | prioridades, dependências, retentativas, logs, cancelamento, auditoria |
| 6 CEO Agent | ✅ | pipeline fixo `new_product` de 10 passos; para na aprovação |
| 7 12 agentes | 🟡 | 13 cadastrados; hoje só chamam o provedor de IA (sem ferramentas próprias) |
| 8 Comunicação entre agentes | 🟡 | via dependências de tarefas; sem mensagens diretas |
| 9 Ollama e provedores | 🟡 | Mock + Ollama implementados (Ollama **não testado contra servidor real**). Claude/Gemini não implementados. |
| 10 Workflows n8n | 🟡 | 1 workflow de mineração importável; 12 faltam; backend sem webhooks |
| 11 Painel administrativo | ✅ | todas as telas ligadas à API real; testado no navegador (desktop e celular) |
| 12 Telegram | ⬜ | |
| 13 Steady Payoff | 🟡 | planilha e página de vendas prontas (entregues antes); ainda não integradas ao sistema |
| 14 Landing + checklist | ⬜ | checklist de 20 itens não implementado |
| 15 Marketing e vendas | ⬜ | |
| 16 Financeiro e relatórios | 🟡 | demonstrativo, registro de vendas/despesas, custos de IA; sem exportação de relatório |
| 17 Testes completos | 🟡 | ver abaixo |
| 18 Produção | ⬜ | backups, HTTPS, monitoramento externo |

## Testes executados (sessão de 2026-11-23, Linux, Python 3.13, Node 22)
- Backend: `python -m pytest -q` → **98 passed**, 0 falhas (56 anteriores + 42 em `test_auth_hardening.py`); rodado 3 vezes seguidas com o mesmo resultado (inclui os testes de concorrência). 5 testes antigos foram **adaptados** (não removidos) ao novo comportamento: logout agora exige token CSRF, hash esperado é `$argon2id$`, e o teste de bloqueio também expira o bloqueio por conta.
- Frontend: `npm test` → **3 arquivos, 13 testes passed** (11 anteriores + 2 de CSRF). `npx tsc --noEmit` e `npm run build` saem com código 0.
- Mutação: 10 quebras deliberadas (CSRF desligado, Origem ignorada, bloqueio por conta removido, `X-Forwarded-For` confiado cegamente, compare-and-swap removido, rehash desligado, limite de senha removido, checagem de produção removida, `/docs` ligado em produção, limite por IP removido) → os testes falharam em todas; arquivos restaurados e conferidos com `cmp`.
- **Não verificado:** login manual em navegador real (CSRF, cookie `Secure` atrás de HTTPS e proxy reverso reais não foram exercitados fora do `TestClient`); PostgreSQL e Docker/compose (esta branch ainda não tem Alembic e o bloqueio atômico só foi testado em SQLite); concorrência com vários processos/réplicas; pytest no Windows do proprietário; Ollama real, Telegram, n8n e geração de arquivos.

## Problemas conhecidos
- Respostas dos agentes com `LLM_PROVIDER=mock` são texto de teste (marcado `[MOCK]`).
- Conta proprietária inicial vem de `OWNER_EMAIL` e `OWNER_PASSWORD` (a senha passa por variável de ambiente); não há CLI nem tela de gerenciamento de contas.
- Quem souber o e-mail do proprietário pode mantê-lo bloqueado por até 15 min por vez (bloqueio temporário por conta; é o custo de impedir força bruta distribuída). Atrás de proxy reverso é preciso configurar `TRUSTED_PROXIES`, senão o IP visto é o do proxy.
- Linhas de `account_login_attempts`/`login_attempts` e sessões expiradas não são limpas automaticamente (pendência).
- A tabela `audit_logs` cresce a cada tentativa de login (inclusive bloqueadas); não há limpeza nem rotação.
- Docker/compose não foram executados (sem daemon na sessão de desenvolvimento).
- Sem migrações: mudar uma tabela exige recriar o banco até existir Alembic.

## Decisões técnicas
- SQLite local por padrão (custo zero), PostgreSQL por URL.
- Dinheiro sempre em centavos; margem e ROI são nulos quando não há base (nunca 0% inventado).
- Ações de risco sempre exigem aprovação e o criador da tarefa não pode desligar isso.
- Provedor pago só roda com `AI_MONTHLY_BUDGET_USD` > 0 e não esgotado.
- Painel com rota por hash para o SPA ocupar só `/`, sem conflito com a API.
- Sem bibliotecas de gráfico/UI: SVG próprio e Tailwind.

## Próximas tarefas
1. Conectar GitHub e subir `main`/`develop`.
2. Testar Ollama real e ajustar.
3. Autenticação, o que resta: CLI segura de criação/recuperação da conta proprietária, limpeza de sessões expiradas, retenção da auditoria, teste manual em navegador real; depois gerenciamento de usuários e troca de senha no painel.
4. Ferramentas dos agentes (Market Hunter via Apify; Product Creator gerando XLSX).
5. Telegram; webhooks do n8n; Alembic.
