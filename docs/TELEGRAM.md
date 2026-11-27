# Telegram (Fase 12)

Bot para **avisar** de aprovações pendentes e para **decidir** pelo celular. Ele roda como um processo à parte
(`python -m app.services.telegram_bot`, na pasta `backend/`) e usa *long polling*: não precisa de URL pública nem HTTPS.
Se o Telegram cair, só o bot espera e tenta de novo; o resto do sistema segue.

## Configurar (no seu computador, nunca no chat)
1. No Telegram, fale com o @BotFather, crie o bot e copie o token. **Se o token já foi colado em algum chat, revogue com `/revoke` e use o novo.**
2. No `.env`: `TELEGRAM_BOT_TOKEN=...` e, por enquanto, `TELEGRAM_ALLOWED_USER_IDS=` vazio.
3. Rode o bot, abra a conversa com ele e mande `/id`. Ele responde o seu número (a qualquer pessoa; é só o ID dela).
4. Coloque o número em `TELEGRAM_ALLOWED_USER_IDS` (vários: separados por vírgula) e reinicie o bot.

## Comandos (só para usuários autorizados, em conversa privada)
`/pendentes`, `/ver N`, `/aprovar N`, `/confirmar N CODIGO`, `/rejeitar N`, `/alterar N motivo`, `/id`, `/ajuda`.

## Segurança
- Sem token o bot não roda; sem lista de autorizados ele ignora todo mundo. Grupos, canais e outros bots nunca são atendidos.
- **Aprovar exige duas etapas**: `/aprovar N` gera um código de 4 dígitos (uso único, 2 minutos, preso ao seu usuário e àquela aprovação); só `/confirmar N CODIGO` conclui. Rejeitar e pedir alterações são imediatos, pois não executam nada de risco.
- A decisão passa pelo mesmo caminho do painel, com as mesmas travas (inclusive a revalidação dos experimentos).
- O token não aparece em log, erro, auditoria ou resposta (a URL do Telegram carrega o token; erros são reescritos e o log do httpx é silenciado). A auditoria guarda quem decidiu e o número da aprovação, não o texto das mensagens.
- Mensagens em texto puro (sem Markdown/HTML).

## Limites conhecidos
- Os códigos de confirmação ficam na memória do bot: se ele reiniciar, o código some e você pede de novo. Rode **uma única** instância.
- O bot lê `TELEGRAM_*` ao iniciar; trocar a lista de autorizados exige reiniciar.
- Aviso de aprovação é enviado uma vez por aprovação a cada autorizado; se o envio falhar, tenta no próximo ciclo.
- Testado só contra um servidor falso da API. **Não foi testado contra o Telegram real.**
