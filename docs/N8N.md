# n8n: webhooks e workflows (Fase 10)

O n8n fala com o backend por webhooks próprios, com segredo próprio. Ele é um **cliente de escopo mínimo**: enfileira
tarefa, lê o estado das tarefas que ele mesmo criou, lê o relatório executivo e lê as aprovações pendentes.
Ele **não** aprova, não rejeita, não executa a fila e não gasta nada. Nenhuma tarefa criada por webhook pode ter `action`
(logo nunca é de risco) e o campo reservado `handoff` é removido do `input`.

## Backend

1. Gere o segredo (32+ caracteres) e coloque em `N8N_WEBHOOK_SECRET`:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Sem ele (ou com menos de 32 caracteres) todos os
   webhooks respondem 503. O segredo é diferente do `ADMIN_API_KEY`, e um não abre a porta do outro.
2. Todas as chamadas levam o cabeçalho `X-Webhook-Secret`. Use **HTTPS** fora da sua máquina: é segredo compartilhado
   em cabeçalho, sem assinatura (guia de produção na Fase 18).

| Método e rota | Para quê |
|---|---|
| `POST /webhooks/n8n/tasks` | Enfileira tarefa. Exige `Idempotency-Key` (8 a 100 caracteres: letras, números, `. _ : -`). Corpo: `agent_key`, `description`, `priority`, `input`. Mesma chave = mesma tarefa (200, `duplicate: true`), nunca duas. |
| `GET /webhooks/n8n/tasks/{id}` | Estado e resultado, só de tarefas criadas por webhook (as demais dão 404). |
| `GET /webhooks/n8n/report` | Relatório executivo (contagens, falhas, agentes pausados, revisões do Quality Guardian). |
| `GET /webhooks/n8n/approvals/pending` | Aprovações pendentes, só o mínimo para avisar (sem os detalhes completos). |

Tarefa enfileirada **não roda sozinha**: quem executa a fila é o painel (ou o CEO). O n8n só enfileira e consulta.

## n8n: credencial e importação

1. Em *Credentials*, crie uma credencial **Header Auth** chamada exatamente `Steady Webhook`, com `Name` =
   `X-Webhook-Secret` e `Value` = o segredo do backend.
2. *Workflows > Import from file* para cada arquivo de `workflows/n8n/`. Eles entram **desativados**. Em cada nó HTTP,
   selecione a credencial `Steady Webhook` se o n8n pedir.
3. No nó **Config** de cada workflow, troque `https://SEU-BACKEND-AQUI` pelo endereço do seu backend.
4. Teste com o gatilho "Teste manual" antes de ativar.

## Workflows

| Arquivo | O que faz | Observação |
|---|---|---|
| `relatorio-diario.json` | Todo dia às 8h (fuso de São Paulo) lê o relatório e monta a mensagem. | O nó **Enviar e-mail** vem DESLIGADO: configure SMTP, troque os e-mails e ative. Telegram vem na Fase 12. |
| `aprovacoes-pendentes.json` | A cada 15 min lê as aprovações pendentes e monta aviso só das novas. | Mesmo nó de e-mail desligado. A memória de "já avisei" só persiste com o workflow ATIVO. O aviso só informa; decidir é no painel. |
| `criativos-enfileirar.json` | Enfileira a conferência de honestidade de um criativo (Creative Director, `creative_check`) e lê o estado. | Preencha `headline` (e `body`) no Config; vazio falha com mensagem clara. |
| `ofertas-para-comparacao.json` | Enfileira a comparação das ofertas que VOCÊ levantou (Competitor Analyst, `offer_comparison`). | Preencha `offers_json` no Config com ofertas reais; nada é inventado nem coletado. |
| `market-hunter-mineracao.json` | (anterior) Minera anúncios via Apify e gera rascunhos com a API do Claude. | Usa tokens pagos fora do backend. **Não foi alterado nem testado nesta fase.** |

## O que foi verificado e o que não foi

Ver `PROJECT_STATUS.md` (seção "Testes da Fase 10"). Resumo: os 4 workflows novos foram importados e executados no
n8n 2.35.7 contra um backend local, com efeito real nas tarefas; **e-mail, Telegram, ativação por agenda e
mineração com Apify não foram exercitados**.
