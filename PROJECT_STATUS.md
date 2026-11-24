# PROJECT_STATUS — Steady AI Company (v0.2.0 + autenticação em revisão no PR nº 1, 2026-11-21)

Legenda: ✅ funciona e testado · 🟡 parcial · ⬜ não iniciado

## Fases
| Fase | Estado | Observação |
|---|---|---|
| 1 Diagnóstico e arquitetura | 🟡 | Sem acesso ao GitHub nesta sessão; arquitetura documentada neste arquivo e no README. Diagnóstico de repositório existente não foi feito. |
| 2 Estrutura inicial | ✅ | backend/, frontend/, workflows/, Docker, .env.example |
| 3 Banco de dados | 🟡 | **Em revisão (branch `feature/fase-03-banco`, empilhada sobre o PR nº 1), não mesclada.** Feito e testado: Alembic com migração `0001` idempotente (adota banco v0.2), SQLite e **PostgreSQL 16.15 real** (suíte inteira), backup/restauração em ambos, teste de deriva modelo×migração. **Faltam/NÃO testado:** `docker compose` (sem daemon na sessão), backup agendado, trava entre réplicas, restauração entre versões do PostgreSQL. Ver `docs/BANCO.md`. |
| 4 Backend e autenticação | 🟡 | **Em revisão (PR nº 1), não mesclada.** Feito e testado: conta do proprietário via ambiente, hash PBKDF2-HMAC-SHA256, sessão `HttpOnly` + `SameSite=Strict` de 12h, logout que invalida no servidor, bloqueio por IP, auditoria de login sem senha, `X-API-Key` desligada por padrão. **Faltam** (escopo original): CLI de criação de usuário, bloqueio por usuário, CSRF, hash argon2/bcrypt, teste manual no navegador. |
| 5 Sistema de tarefas | ✅ | prioridades, dependências, retentativas, logs, cancelamento, auditoria |
| 6 CEO Agent | ✅ | pipeline fixo `new_product` de 10 passos; para na aprovação |
| 7 12 agentes | 🟡 | **Ferramentas reais em 2 lotes, sem IA, rede nem custo.** 1º lote (PR nº 5, branch `feature/fase-07-agentes`): CFO `financial_summary`, Product Creator `steady_payoff_xlsx`, Quality Guardian `review_xlsx` (recalcula no LibreOffice e confere contra cálculo independente). 2º lote (branch `feature/fase-07b-agentes`, empilhada sobre o PR nº 5, em revisão): Chief Strategy Officer `experiment_review` (regras de `experiments` + nível de confiança e riscos), Sales Manager `sales_report` (vendas, receita líquida e taxa de reembolso por produto; margem de reembolso nula sem receita bruta; **sem conversão de funil**, pois não há visitas/cliques), Competitor Analyst `offer_comparison` (só as ofertas informadas na tarefa; nada é coletado da internet). Tarefa só usa ferramenta com `input.tool`. **Faltam (6 agentes):** Market Hunter (exige token do Apify), Creative Director, Growth Strategist, Customer Success, Social Media Manager, Product Architect; **3º passo (branch `feature/fase-07c-ceo-ferramentas`, em revisão):** o CEO ganhou o roteiro opt-in `steady_payoff_build` (planilha → revisão do Quality Guardian → relatório de vendas → resumo financeiro), sem IA, custo nem etapa de risco; o roteiro `new_product` não mudou. O relatório executivo agora sinaliza revisões `rejected` e `approved_with_gaps`. Ainda sem tela de download de arquivos. |
| 8 Comunicação entre agentes | 🟡 | via dependências de tarefas; sem mensagens diretas |
| 9 Ollama e provedores | 🟡 | Mock + Ollama implementados (Ollama **não testado contra servidor real**). Claude/Gemini não implementados. |
| 10 Workflows n8n | 🟡 | 1 workflow de mineração importável; 12 faltam; backend sem webhooks |
| 11 Painel administrativo | ✅ | todas as telas ligadas à API real; testado no navegador (desktop e celular) |
| 12 Telegram | ⬜ | |
| 13 Steady Payoff | 🟡 | planilha e página de vendas prontas (entregues antes); ainda não integradas ao sistema |
| 14 Landing + checklist | ⬜ | checklist de 20 itens não implementado |
| 15 Marketing e vendas | ⬜ | |
| 16 Financeiro e relatórios | 🟡 | demonstrativo, registro de vendas/despesas, custos de IA; sem exportação de relatório. **Recorte 16a (antecipado, em revisão na branch `feature/fase-16a-experimentos`, empilhada sobre o PR nº 2):** experimentos de validação com CPA, ROI e recomendação por regras, só API. Primeiro teste: EUA/USD (decisão do proprietário). Parâmetros do 1º experimento ainda a definir. **Recorte 16b (branch `feature/fase-16b-validacao`, empilhada sobre o PR nº 3, em revisão):** checklist atestado + 3 ângulos antes de pedir aprovação, evento sazonal, escala só após validar. Order bump, tela e conversão de moedas **não existem**. Ver `docs/EXPERIMENTOS.md`. |
| 17 Testes completos | 🟡 | ver abaixo |
| 18 Produção | ⬜ | backups, HTTPS, monitoramento externo |

## Testes executados (sessão de 2026-11-21, Linux, Python 3.13, Node 22)
- Backend: `python -m pytest -q` → **56 passed**, 0 falhas, 0 erros (39 existentes + 17 em `test_auth_security.py`).
- Frontend: `npm ci && npm test` → **3 arquivos, 11 testes passed**. `npm run build` (tsc + vite build) e `npx tsc --noEmit` saem com código 0.
- Mutação: 11 quebras deliberadas das regras de segurança (senha em texto puro, `SameSite`, `HttpOnly`, bloqueio desligado, senha/e-mail na auditoria, rotas sem proteção, logout sem apagar sessão, `X-API-Key` aberta, senha em log, senha padrão) → os testes correspondentes falharam em todas; código restaurado depois.
- **Não verificado:** o erro local "no tests, 3 errors" do Vitest **não reproduziu** num `npm ci` limpo (causa provável: `node_modules` local desatualizado; não confirmado). O pytest **não foi rodado no Windows** do proprietário (o `pyreadline` nem existe neste Linux). Login manual no navegador com o cookie `SameSite=Strict` não foi feito nesta sessão. PostgreSQL, Docker/compose, Ollama real, Telegram, n8n e geração de arquivos continuam sem teste.

## Testes da Fase 3 (sessão de 2026-11-22, Linux, Python 3.13, PostgreSQL 16.15 local sem Docker)
- Backend em SQLite: `python -m pytest -q` → **68 passed, 3 skipped** (os 3 só rodam com PostgreSQL). Em PostgreSQL real (`TEST_DATABASE_URL`): **71 passed**. Coletados: 56 anteriores + 7 em `test_migrations.py` + 8 em `test_backup.py` = 71.
- CLI de ponta a ponta em PostgreSQL real: `alembic upgrade head` → backup → dado apagado → `restore` (recusa sem `--yes`) → dado e versão `0001` de volta → `downgrade base` (0 tabelas) → `upgrade head` (12 tabelas).
- Mutação: 9 execuções em 8 regras dos testes novos (deriva modelo×migração, adoção de banco v0.2, downgrade, restore sem confirmação, senha do PostgreSQL em argumento, permissão do backup, validação do arquivo de backup, cópia de segurança do restore). Na 1ª rodada 7 falharam como esperado e **1 sobreviveu** (a validação de arquivo de lixo era coberta por outra checagem, então o teste não provava a regra). Foi acrescentado um teste específico (SQLite válido de outro sistema) e o mutante refeito falhou. Resultado final: 8 de 8 regras com teste que reage à quebra. O código foi restaurado byte a byte após cada quebra.
- **Não verificado:** `docker compose up` e os comandos `docker compose exec` (sem daemon Docker); frontend não foi reexecutado nesta fase (não foi alterado); Windows; PostgreSQL de outra versão; backup agendado.

## Testes da Fase 16a (sessão de 2026-11-22, Linux, Python 3.13, PostgreSQL 16.15 local sem Docker)
- Backend em SQLite: **93 passed, 3 skipped**. Em PostgreSQL real: **96 passed**. Coletados: 71 anteriores + 24 em `test_experiments.py` + 1 em `test_migrations.py` = 96.
- Migração `0002` na linha de comando em PostgreSQL real: `upgrade` → despesa inserida → `downgrade 0001` (tabela e coluna removidas, despesa preservada) → `upgrade`.
- Mutação: 20 quebras deliberadas das regras do experimento (CPA de equilíbrio sem taxas, ROI/CPA 0 sem base, regras de parada, validação invertida, evidência mínima, fechar validado sem checar, líquida sem reembolso, aprovação que não ativa, mercado com padrão etc.) → o teste correspondente falhou em 20 de 20; código restaurado byte a byte.
- Corrigido nesta fase: o teste de adoção de banco v0.2 usava `create_all` com os modelos atuais e deixou de representar um banco v0.2 real; passou a ser reconstruído a partir da migração `0001`.
- **Não verificado:** o vídeo de origem (só o resumo do proprietário); `docker compose`; frontend (sem tela de experimentos e não reexecutado); Windows; uso com dinheiro real; conversão entre moedas no dashboard.

## Testes da Fase 16b (sessão de 2026-11-22/23, Linux, Python 3.13, PostgreSQL 16.15 local sem Docker)
- Backend em SQLite: **143 passed, 3 skipped**. Em PostgreSQL real: **146 passed, 0 skipped**. Contagem: 96 da 16a + 1 em `test_migrations.py` + 49 em `test_validacao_escala.py` = 146.
- Mutação (primeira rodada): 14 quebras deliberadas das regras do commit `7bd49e3` → 14 detectadas. Mutação das correções da revisão (M1, L1, L2): 10 quebras (revalidação vazia, portão desligado, `assume_approved` ignorado, bloqueio também na rejeição, sem auditoria de bloqueio, sem commit antes de recusar, sem auditoria de revalidação, checklist voltando a coagir, sem `strip`) → 10 detectadas. Código restaurado byte a byte (`cmp`) nas duas rodadas.
- Migração `0003` na linha de comando em PostgreSQL real, com linha antiga: `upgrade` → padrões (`validation`, `[]`, `{}`) → `downgrade 0002` (experimento preservado) → `upgrade`. Migração e `policy.py` sem alteração nesta rodada.
- Mudança deliberada em testes existentes (commit anterior): o helper `approve` de `test_experiments.py` e 3 testes de aprovação completam o plano de lançamento antes de pedir aprovação. Nenhum teste apagado ou pulado.
- **Correções da revisão independente do PR nº 4:** M1 (aprovar revalida plano e recomendação com os dados de agora; `STOP` bloqueia a aprovação, que continua pendente; rejeitar e pedir alterações nunca são bloqueados; auditoria `experiment_approval_blocked` / `experiment_approval_revalidated`), L1 (checklist só aceita `true`/`false` reais), L2 (ângulo e gancho com `strip`; vazio ou só espaços é rejeitado).
- **Não verificado:** o vídeo (só o resumo do proprietário) e seus números; que o checklist reflita a realidade (é atestação); tela; `docker compose`; Windows; frontend; concorrência na regra de uma escala aberta (sem trava no banco, L3 da revisão); data do evento em UTC (L5 da revisão); uso com dinheiro real; mergeabilidade da pilha contra `develop`.

## Testes da Fase 7 (1º lote, 2026-11-24, Linux, Python 3.13, LibreOffice presente)
- Backend: `python -m pytest -q` → **155 passed, 3 skipped** (143 anteriores + 12 novos); os 3 skips são os testes de PostgreSQL já existentes (sem `TEST_DATABASE_URL` nesta rodada). 12 testes novos em `test_agent_tools.py`, sem skips.
- Mutação: 8 quebras deliberadas (revisor ignora hash, ignora erros de fórmula, não compara valores, lacuna vira "aprovado", sem checagem de caminho, ferramenta de outro agente, margem 0 inventada, fórmula de juros errada) → os testes falharam em todas; arquivos restaurados.
- **Não verificado:** abrir a planilha no Excel de verdade (só LibreOffice); frontend não foi alterado nem reexecutado; PostgreSQL nesta rodada; `docker compose`.

## Testes da Fase 7, 2º lote (2026-11-24)
- Backend: `python -m pytest -q` → **172 passed, 3 skipped** (155 + 17 novos em `test_agent_tools_2.py`); os 3 skips são os testes de PostgreSQL já existentes (sem `TEST_DATABASE_URL` nesta rodada).
- Mutação: 7 quebras deliberadas (confiança sempre alta, sem alerta de amostra pequena, líquido ignorando reembolso, taxa de reembolso 0 inventada, mediana virando média, preço inválido aceito, sem aviso de escopo) → os testes falharam em todas; arquivo restaurado.
- Os limiares de 30 vendas (confiança) e 10% (reembolso) são heurísticas nossas, não padrões estatísticos ou de mercado. Frontend não foi alterado nem reexecutado; PostgreSQL e `docker compose` não foram exercitados.

## Testes da Fase 7, passo do CEO (2026-11-24)
- Backend: `python -m pytest -q` → **178 passed, 3 skipped** (172 + 6 novos em `test_ceo_tools.py`); os 3 skips são os testes de PostgreSQL já existentes.
- Mutação: 5 quebras deliberadas (`$step` não resolvido, rejeição não sinalizada, lacuna não sinalizada, revisor sem dependência da geração, etapa de risco no roteiro) → os testes falharam em todas; arquivo restaurado.
- **Não verificado:** o roteiro pela interface do painel (o painel ainda não escolhe `pipeline`; só a API); execução no Excel real; frontend, PostgreSQL e `docker compose` nesta rodada.

## Testes da Fase 7, 3º lote (2026-11-24)
- Backend: `python -m pytest -q` → **189 passed, 3 skipped** (178 + 11 novos em `test_agent_tools_3.py`); os 3 skips são os testes de PostgreSQL já existentes.
- Mutação: 8 quebras deliberadas (criativo sempre aprovado, arredondamento para baixo, reembolso incluindo vendas sem reembolso, datas sem espaçamento, limite de título, post marcado como publicado, entregáveis sem checagem, guarda de taxa maior que o preço) → os testes falharam em todas; uma escapou na 1ª rodada (guarda de taxa) e o teste foi reforçado; arquivo restaurado byte a byte.
- Limites (`RISKY_PHRASES`, 90 caracteres de título) são heurísticas nossas, não regras de plataforma nem revisão jurídica.
- **Não verificado:** frontend, PostgreSQL e `docker compose` nesta rodada; uso pelo painel (só API). Market Hunter segue sem ferramenta (exige token do Apify e pode gerar custo).

## Testes da Fase 8 (2026-11-24)
- Backend: `python -m pytest -q` → **208 passed, 3 skipped** (189 + 19 novos); os 3 skips são os testes de PostgreSQL já existentes.
- Mutação: 9 quebras deliberadas (sem trava de ciclo, sem profundidade em handoff e em respostas, origem não concluída aceita, auto-envio aceito, cadeia forjável pelo chamador, handoff sem dependência da origem, sem auditoria, sem limite de tamanho) → os testes falharam em todas; arquivo restaurado byte a byte.
- Profundidade máxima 5 é heurística nossa.
- **Não verificado:** a migração `0004` em PostgreSQL e `docker compose`; frontend (sem tela de mensagens; só API); execução automática (um handoff só cria a tarefa, quem a roda é a fila normal); concorrência entre vários processos.

## Testes da Fase 9 (2026-11-24)
- Backend: `python -m pytest -q` → **236 passed, 3 skipped** (208 + 28 novos); os 3 skips são os testes de PostgreSQL já existentes. Frontend: `vitest` → **13 passed**, `tsc` e `vite build` limpos.
- Mutação: 14 quebras deliberadas no backend (arredondamento para baixo, chave/preço ausente aceitos, HTTP 4xx aceito, corpo da resposta vazando no erro, chave não enviada, reserva `mock` aceita, pior caso sem entrada ou ignorado, `max_tokens` fixo, config ignorada, reserva não aplicada, restante inventado) e 1 no frontend (restante virando 0 em vez de traço) → os testes falharam em todas; uma escapou na 1ª rodada (termo de entrada do pior caso) e o teste foi reforçado; arquivos restaurados byte a byte.
- **Ollama:** o protocolo foi testado contra um servidor HTTP LOCAL FALSO. **Nenhum Ollama real foi testado** (este ambiente não tem Ollama nem acesso ao registro de modelos). Para fechar: rodar `python backend/scripts/check_ollama.py` na sua máquina.
- **Claude e Gemini:** formato de requisição/resposta (cabeçalhos, JSON, campos de tokens) foi escrito a partir da documentação conhecida e testado só contra servidores falsos; **nenhuma chamada real foi feita** (exigiria chave e gastaria dinheiro). Preços não têm padrão: você precisa informá-los.
- Estimativa de pior caso usa 1 token a cada 3 caracteres (heurística nossa, conservadora); `AI_MAX_OUTPUT_TOKENS=1024` é padrão nosso.
- **Não verificado:** PostgreSQL e `docker compose` nesta rodada; o painel no navegador real (só testes de componente); fallback quando o Ollama cai no meio de uma chamada (a tarefa tenta de novo e, esgotadas as tentativas, falha; a reserva só cobre bloqueio do pago).

## Problemas conhecidos
- Respostas dos agentes com `LLM_PROVIDER=mock` são texto de teste (marcado `[MOCK]`).
- Conta proprietária inicial vem de `OWNER_EMAIL` e `OWNER_PASSWORD` (a senha passa por variável de ambiente); não há CLI nem tela de gerenciamento de contas.
- Bloqueio de login é só por IP (atrás de proxy reverso o IP visto é o do proxy), não por usuário. Sem token CSRF (só `SameSite=Strict`).
- Hash PBKDF2-HMAC-SHA256 com 260.000 rodadas, abaixo das 600.000 que a OWASP recomenda para essa combinação; o escopo pedia argon2 ou bcrypt.
- A tabela `audit_logs` cresce a cada tentativa de login (inclusive bloqueadas); não há limpeza nem rotação.
- Docker/compose não foram executados (sem daemon na sessão de desenvolvimento).
- Migrações: existem `0001`, `0002` e `0003`. Mudar colunas de tabela existente exige nova migração revisada à mão; o `downgrade` da `0001` apaga todas as tabelas; instância única (sem trava de migração entre processos).

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
5. Telegram; webhooks do n8n.
