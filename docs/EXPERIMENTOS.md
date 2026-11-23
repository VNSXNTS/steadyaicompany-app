# Experimentos de validação de oferta (Fases 16a e 16b, antecipadas)

Origem: um vídeo (resumo fornecido pelo proprietário; **o vídeo não foi visto por quem implementou**) em que o autor
valida um low ticket gastando pouco: nicho com data marcada, produto visual, 3 criativos (dor, urgência, material),
campanha de vendas com público aberto, orçamento inicial pequeno, escala só depois de validar. Os números do vídeo
(CPA de R$ 6–7, vendas em poucas horas) são do próprio autor e **não foram verificados**. O método aqui é uma disciplina
de decisão, **não uma promessa de lucro**.

## Decisão do proprietário (2026-11-22)
O primeiro teste é no **mercado EUA, em dólar (`US` / `USD`)**, coerente com o Steady Payoff. Com uma moeda só, a limitação do dashboard abaixo não afeta este teste. O CPA do vídeo é brasileiro e **não se transfere**: o CPA real nos EUA só se conhece medindo, e deve ser bem diferente. Preço, teto de gasto e mínimo de vendas do primeiro experimento **ainda não foram definidos** pelo proprietário.

## O que o sistema faz e não faz
- **Faz:** guarda um experimento com orçamento e critérios de parada definidos antes de gastar; calcula CPA, CPA de
  equilíbrio, receita líquida, lucro e ROI; recomenda continuar, parar ou "candidato a validada"; recusa marcar como
  validada uma oferta que não cumpriu as regras; exige a sua aprovação para o teste começar.
- **NÃO faz:** não cria nem publica anúncio, não gasta, não fala com o Meta Ads. Você roda a campanha fora e registra
  gasto e vendas. Não gera criativos (Fases 7 e 15), **não escolhe nem pesquisa o nicho sazonal** (Fase 7, Market Hunter) e **não implementa order bump**.

## Fluxo (todas as chamadas exigem login)
1. `POST /experiments`: nome, `market` (ex.: `US`, `BR`), `currency` (ex.: `USD`, `BRL`), `price_cents`, taxas
   (`fee_bps`, `fee_fixed_cents`), `budget_cap_cents`, `max_spend_without_sale_cents`, `min_sales_to_decide`.
   **Mercado e moeda são obrigatórios e sem padrão** (a decisão é sua). Depois de criado, nada disso é editável.
   Opcional: `event_name` + `event_date` (evento sazonal; os dois juntos ou nenhum; data em UTC).
2. `PUT /experiments/{id}/launch-plan` (só em rascunho): 3 ou mais **ângulos de criativo** distintos, cada um com
   gancho (`{"angle": "dor", "hook": "..."}`), e o **checklist atestado por você** (veja a seção 16b).
3. `POST /experiments/{id}/request-approval`: **recusa (409) se o plano estiver incompleto**; senão cria uma aprovação
   `activate_campaign`. Aprove em `/approvals/{id}/decide`.
4. Você roda a campanha e registra: `POST /experiments/{id}/spend` e `POST /experiments/{id}/sales`.
5. `GET /experiments/{id}` devolve as métricas e a recomendação a cada momento.
6. `POST /experiments/{id}/close` com `killed` ou `validated`. `validated` só é aceito se a regra abaixo permitir.
7. Só depois de **validado**: `POST /experiments/{id}/scale` cria a etapa de escala (seção 16b).

## Regras da recomendação (a primeira que casar vence)
| Situação | Recomendação |
|---|---|
| Encerrado | `closed` |
| Ainda não aprovado | `not_started` |
| Gasto ≥ teto | `stop` |
| 0 vendas e gasto ≥ limite sem venda | `stop` |
| Vendas < mínimo e o evento sazonal já passou | `stop` (a janela de demanda acabou sem evidência) |
| Vendas < mínimo para decidir | `continue` (evidência insuficiente) |
| Vendas ≥ mínimo e CPA ≤ CPA de equilíbrio | `validated_candidate` (não é garantia) |
| Vendas ≥ mínimo e CPA > CPA de equilíbrio | `stop` |

Contas, em centavos: CPA de equilíbrio = preço − (preço × `fee_bps` ÷ 10.000 + taxa fixa); receita líquida = bruto −
taxas − reembolsos; lucro = líquida − gasto do experimento; ROI = lucro ÷ gasto, **`null` sem gasto**; CPA = gasto ÷
vendas, **`null` sem vendas**. Reembolsos futuros não são estimados no CPA de equilíbrio.

## Fase 16b: validar antes de escalar
Traz do método do vídeo a disciplina que faltava: preparar antes de gastar, respeitar a janela sazonal e só ampliar o
orçamento de uma oferta que já provou o CPA. **Nada disso gasta ou publica algo.**
- **Checklist atestado por você** (4 itens, todos obrigatórios para pedir aprovação): checkout testado com compra de
  teste; evento de compra configurado; política de reembolso publicada; anúncio e página sem promessa de resultado
  garantido nem depoimento inventado. **O sistema não consegue conferir isso no mundo real**: é uma atestação sua,
  registrada na auditoria. Ela reduz esquecimento, não prova que está certo.
- **Ângulos de criativo:** pelo menos 3, com nomes distintos e gancho preenchido (o vídeo usou dor, urgência e material;
  os nomes são livres). O texto é seu: o sistema não gera nem publica criativo.
- **Plano congelado:** o plano só muda em rascunho; depois do pedido de aprovação o que você aprovou não muda.
- **Revalidação ao aprovar:** na hora de aprovar, o sistema reavalia o plano e a recomendação com os dados de agora,
  como se o experimento já estivesse aprovado. Se der `STOP` (evento já passou, teto já atingido por gasto registrado
  etc.) ou o plano deixou de valer, a aprovação é **recusada (400)** e continua pendente, com o motivo e um registro
  `experiment_approval_blocked` na auditoria. Você ainda pode rejeitar ou pedir alterações. Uma aprovação válida
  registra `experiment_approval_revalidated`.
- **Rigor dos campos:** o checklist só aceita `true`/`false` reais (nada de `"yes"` ou `1`); ângulo e gancho são
  gravados sem espaços nas pontas, e vazio ou só espaços é recusado.
- **Evento sazonal:** `days_to_event` nas métricas; aviso quando faltam 7 dias ou menos (**7 é uma heurística
  nossa, não um número do vídeo**); data já passada bloqueia o pedido de aprovação; depois da data, sem evidência
  suficiente, a recomendação vira `stop`. Se já houver evidência suficiente e CPA dentro do equilíbrio, a recomendação
  `validated_candidate` continua valendo. Datas em UTC.
- **Escala (`scale`):** só a partir de um experimento **encerrado como validado** e que seja de validação (não de outra
  escala). Herda preço, taxas, mercado, moeda, evento e ângulos; **começa em rascunho, sem gasto e sem vendas, com o
  checklist zerado** e exige nova aprovação `activate_campaign`. O teto precisa ser maior que o da validação, e só pode
  haver uma escala em aberto por experimento (uma rejeitada ou encerrada libera outra). Os critérios de parada da escala
  são **seus**: o sistema não sugere o salto de orçamento (o vídeo foi de R$ 30 para R$ 200 por conjunto, número do autor e
  não verificado).
- **Order bump: não implementado.** O vídeo só o recomenda depois de validar; aqui, como não há bump no sistema, ele
  não existe na etapa de validação, mas também não há campo nem conta para ele na escala. Vendas com bump podem ser
  registradas pelo valor bruto total, e o CPA de equilíbrio continua calculado só sobre o preço principal (conservador).

## Limites conhecidos (leia antes de usar dinheiro de verdade)
- **Evidência fraca por natureza:** com poucas vendas, o acaso pesa muito. As regras são critérios de disciplina
  (parar cedo, não escalar no escuro), não um teste estatístico.
- **Dashboard de uma moeda só (não afeta o teste nos EUA, só se algum dia entrar BRL):** gasto e vendas de experimentos alimentam o `/dashboard` e o Financeiro sem duplicar,
  mas o painel **não converte moedas**. Misturar BRL e USD dá totais sem sentido. Isso precisa ser resolvido antes de
  operar nos dois mercados.
- **Sem tela:** só API por enquanto (o painel é da Fase 11). Sem edição nem exclusão de experimentos.
- Gasto registrado sem aprovação (ou acima do teto) é aceito, porque o fato já aconteceu, mas gera aviso em `warnings`.
- Registros de gasto/venda de um experimento encerrado são recusados (reembolsos tardios exigem decisão futura).
