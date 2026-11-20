# PROJECT_STATUS — Steady AI Company (v0.2.0, 2026-11-19)

Legenda: ✅ funciona e testado · 🟡 parcial · ⬜ não iniciado

## Fases
| Fase | Estado | Observação |
|---|---|---|
| 1 Diagnóstico e arquitetura | 🟡 | Sem acesso ao GitHub nesta sessão; arquitetura documentada neste arquivo e no README. Diagnóstico de repositório existente não foi feito. |
| 2 Estrutura inicial | ✅ | backend/, frontend/, workflows/, Docker, .env.example |
| 3 Banco de dados | 🟡 | SQLAlchemy; SQLite testado. PostgreSQL configurado, **não executado**. Sem Alembic (tabelas criadas no start). |
| 4 Backend e autenticação | 🟡 | Chave de administrador (fail-closed). Faltam usuários, senhas com hash, sessões, rate limit. |
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

## Testes executados
- Backend: `pytest` — 36 passam (tarefas, aprovações, política, CEO, custos, orçamento, health, logs sem segredo, autenticação).
- Frontend: `vitest` — 11 passam (formatação, cliente da API, login, painel vazio sem números inventados, decisão de aprovação). `tsc` e `vite build` limpos.
- Manual: backend real servindo o painel; login, plano do CEO, execução da fila (mock), venda/despesa, aprovação pendente; capturas desktop e celular sem erros de console.
- Não existem testes para: Telegram, n8n, geração de arquivos, PostgreSQL (nada disso está implementado ou foi executado).

## Problemas conhecidos
- Respostas dos agentes com `LLM_PROVIDER=mock` são texto de teste (marcado `[MOCK]`).
- Chave de administrador digitada no login e guardada em sessionStorage; trocar por login real na Fase 4.
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
3. Autenticação real (usuários, hash, sessão, rate limit).
4. Ferramentas dos agentes (Market Hunter via Apify; Product Creator gerando XLSX).
5. Telegram; webhooks do n8n; Alembic.
