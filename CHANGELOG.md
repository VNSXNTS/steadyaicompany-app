# Changelog

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
