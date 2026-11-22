# PROJECT_STATUS — Steady AI Company (v0.2.0 + autenticação em revisão no PR nº 1, 2026-11-21)

Legenda: ✅ funciona e testado · 🟡 parcial · ⬜ não iniciado

## Fases
| Fase | Estado | Observação |
|---|---|---|
| 1 Diagnóstico e arquitetura | 🟡 | Sem acesso ao GitHub nesta sessão; arquitetura documentada neste arquivo e no README. Diagnóstico de repositório existente não foi feito. |
| 2 Estrutura inicial | ✅ | backend/, frontend/, workflows/, Docker, .env.example |
| 3 Banco de dados | 🟡 | SQLAlchemy; SQLite testado. PostgreSQL configurado, **não executado**. Sem Alembic (tabelas criadas no start). |
| 4 Backend e autenticação | 🟡 | **Em revisão (PR nº 1), não mesclada.** Feito e testado: conta do proprietário via ambiente, hash PBKDF2-HMAC-SHA256, sessão `HttpOnly` + `SameSite=Strict` de 12h, logout que invalida no servidor, bloqueio por IP, auditoria de login sem senha, `X-API-Key` desligada por padrão. **Faltam** (escopo original): CLI de criação de usuário, bloqueio por usuário, CSRF, hash argon2/bcrypt, teste manual no navegador. |
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

## Testes executados (sessão de 2026-11-21, Linux, Python 3.13, Node 22)
- Backend: `python -m pytest -q` → **56 passed**, 0 falhas, 0 erros (39 existentes + 17 em `test_auth_security.py`).
- Frontend: `npm ci && npm test` → **3 arquivos, 11 testes passed**. `npm run build` (tsc + vite build) e `npx tsc --noEmit` saem com código 0.
- Mutação: 11 quebras deliberadas das regras de segurança (senha em texto puro, `SameSite`, `HttpOnly`, bloqueio desligado, senha/e-mail na auditoria, rotas sem proteção, logout sem apagar sessão, `X-API-Key` aberta, senha em log, senha padrão) → os testes correspondentes falharam em todas; código restaurado depois.
- **Não verificado:** o erro local "no tests, 3 errors" do Vitest **não reproduziu** num `npm ci` limpo (causa provável: `node_modules` local desatualizado; não confirmado). O pytest **não foi rodado no Windows** do proprietário (o `pyreadline` nem existe neste Linux). Login manual no navegador com o cookie `SameSite=Strict` não foi feito nesta sessão. PostgreSQL, Docker/compose, Ollama real, Telegram, n8n e geração de arquivos continuam sem teste.

## Problemas conhecidos
- Respostas dos agentes com `LLM_PROVIDER=mock` são texto de teste (marcado `[MOCK]`).
- Conta proprietária inicial vem de `OWNER_EMAIL` e `OWNER_PASSWORD` (a senha passa por variável de ambiente); não há CLI nem tela de gerenciamento de contas.
- Bloqueio de login é só por IP (atrás de proxy reverso o IP visto é o do proxy), não por usuário. Sem token CSRF (só `SameSite=Strict`).
- Hash PBKDF2-HMAC-SHA256 com 260.000 rodadas, abaixo das 600.000 que a OWASP recomenda para essa combinação; o escopo pedia argon2 ou bcrypt.
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
3. Fechar a autenticação: CLI de usuário, bloqueio por usuário, CSRF, argon2/bcrypt, teste manual no navegador; depois gerenciamento de usuários e troca de senha no painel.
4. Ferramentas dos agentes (Market Hunter via Apify; Product Creator gerando XLSX).
5. Telegram; webhooks do n8n; Alembic.
