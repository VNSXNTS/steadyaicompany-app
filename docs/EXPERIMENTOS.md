# Experimentos de validação de oferta (Fase 16a, antecipada)

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
  gasto e vendas. Não escolhe nicho, não gera criativos (isso é das Fases 7 e 15), não implementa order bump nem escala.

## Fluxo (todas as chamadas exigem login)
1. `POST /experiments`: nome, `market` (ex.: `US`, `BR`), `currency` (ex.: `USD`, `BRL`), `price_cents`, taxas
   (`fee_bps`, `fee_fixed_cents`), `budget_cap_cents`, `max_spend_without_sale_cents`, `min_sales_to_decide`.
   **Mercado e moeda são obrigatórios e sem padrão** (a decisão é sua). Depois de criado, nada disso é editável.
2. `POST /experiments/{id}/request-approval`: cria uma aprovação `activate_campaign`. Aprove em `/approvals/{id}/decide`.
3. Você roda a campanha e registra: `POST /experiments/{id}/spend` e `POST /experiments/{id}/sales`.
4. `GET /experiments/{id}` devolve as métricas e a recomendação a cada momento.
5. `POST /experiments/{id}/close` com `killed` ou `validated`. `validated` só é aceito se a regra abaixo permitir.

## Regras da recomendação (a primeira que casar vence)
| Situação | Recomendação |
|---|---|
| Encerrado | `closed` |
| Ainda não aprovado | `not_started` |
| Gasto ≥ teto | `stop` |
| 0 vendas e gasto ≥ limite sem venda | `stop` |
| Vendas < mínimo para decidir | `continue` (evidência insuficiente) |
| Vendas ≥ mínimo e CPA ≤ CPA de equilíbrio | `validated_candidate` (não é garantia) |
| Vendas ≥ mínimo e CPA > CPA de equilíbrio | `stop` |

Contas, em centavos: CPA de equilíbrio = preço − (preço × `fee_bps` ÷ 10.000 + taxa fixa); receita líquida = bruto −
taxas − reembolsos; lucro = líquida − gasto do experimento; ROI = lucro ÷ gasto, **`null` sem gasto**; CPA = gasto ÷
vendas, **`null` sem vendas**. Reembolsos futuros não são estimados no CPA de equilíbrio.

## Limites conhecidos (leia antes de usar dinheiro de verdade)
- **Evidência fraca por natureza:** com poucas vendas, o acaso pesa muito. As regras são critérios de disciplina
  (parar cedo, não escalar no escuro), não um teste estatístico.
- **Dashboard de uma moeda só (não afeta o teste nos EUA, só se algum dia entrar BRL):** gasto e vendas de experimentos alimentam o `/dashboard` e o Financeiro sem duplicar,
  mas o painel **não converte moedas**. Misturar BRL e USD dá totais sem sentido. Isso precisa ser resolvido antes de
  operar nos dois mercados.
- **Sem tela:** só API por enquanto (o painel é da Fase 11). Sem edição nem exclusão de experimentos.
- Gasto registrado sem aprovação (ou acima do teto) é aceito, porque o fato já aconteceu, mas gera aviso em `warnings`.
- Registros de gasto/venda de um experimento encerrado são recusados (reembolsos tardios exigem decisão futura).
