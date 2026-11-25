# Banco de dados: migrações, PostgreSQL, backup e restauração

Escrito na Fase 3. Tudo marcado **(testado)** foi executado de verdade; o que está marcado **(NÃO testado)** foi
escrito mas nunca rodou. Ambiente dos testes: Linux, Python 3.13, SQLite, PostgreSQL 16.15 local (sem Docker).

## 1. Como o esquema nasce

O esquema é criado **só por migrações Alembic**; `create_all` não é mais usado pela aplicação. Ao iniciar,
o backend executa `alembic upgrade head` na própria conexão (`app/database/migrate.py`). A versão fica na tabela
`alembic_version` do banco. A URL vem de `DATABASE_URL` (SQLite por padrão; PostgreSQL com `postgresql+psycopg://`).

Migração atual: `0005`. A `0001` é o esquema inicial (12 tabelas, incluindo `users`, `auth_sessions`, `login_attempts`); a `0002` cria `experiments` e a coluna `experiment_id` em `sales` e `expenses` (testada em SQLite e PostgreSQL 16.15: `upgrade`, `downgrade` para `0001` preservando dados antigos, `upgrade`). A `0003` (Fase 16b) acrescenta a `experiments` as colunas `stage`, `parent_experiment_id`, `event_name`, `event_date`, `creative_angles` e `launch_checklist`, com valor padrão no banco (linhas antigas viram etapa `validation`); `downgrade` para `0002` preserva os experimentos e remove só essas colunas (testado em SQLite e PostgreSQL). A `0004` (Fase 8) cria só a tabela `agent_messages` (mensagens e handoffs entre agentes); `downgrade` para `0003` apaga esse histórico e preserva o resto (testado em SQLite; PostgreSQL não exercitado nesta rodada). A `0005` (Fase 10) cria só `webhook_receipts` (recibos de idempotência dos webhooks do n8n); `downgrade` para `0004` apaga os recibos (um reenvio antigo do n8n com a mesma chave passaria a criar tarefa duplicada) e preserva o resto (testado em SQLite).

**Banco antigo (v0.2, criado por `create_all`) (testado):** a `0001` é idempotente. Cria só as tabelas que faltam
e não altera nem apaga nenhuma existente, então o banco é adotado sem perda de dados. Limite: se uma tabela antiga
tiver colunas diferentes das esperadas, a `0001` não as corrige.

### Mudar o esquema
1. Edite o modelo em `backend/app/models/entities.py`.
2. `cd backend && alembic revision --autogenerate -m "descricao"` e **revise o arquivo gerado** (o autogenerate erra
   renomeações e alguns tipos).
3. `pytest`: o teste `test_migrated_schema_matches_the_models_exactly` falha se o modelo e as migrações divergirem.

Comandos úteis (rodar em `backend/`, com `DATABASE_URL` apontando para o banco desejado): `alembic current`,
`alembic upgrade head`, `alembic downgrade -1`. **`downgrade` é destrutivo** (o da `0001` apaga todas as tabelas; o da `0002` apaga os dados de experimentos; o da `0003` apaga etapa, evento, ângulos e checklist; o da `0004` apaga o histórico de mensagens entre agentes; o da `0005` apaga os recibos de idempotência dos webhooks);
faça backup antes.

## 2. PostgreSQL

Uso: `DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@HOST:5432/BANCO`.

**Testado (testado):** migração `upgrade`/`downgrade`/`upgrade`, ausência de deriva entre modelos e migrações, a
suíte inteira do backend e backup/restauração, tudo contra um PostgreSQL 16.15 real (servidor iniciado localmente,
com autenticação por senha).

**Rodar a suíte em PostgreSQL:** exporte `TEST_DATABASE_URL` com um banco **descartável** e rode `pytest`. A variável
é separada de `DATABASE_URL` de propósito: o fixture de testes apaga todas as tabelas do banco indicado.

```bash
createdb steady_test
TEST_DATABASE_URL=postgresql+psycopg://steady:SENHA@localhost:5432/steady_test python -m pytest -q
```
Sem `TEST_DATABASE_URL`, os 3 testes exclusivos de PostgreSQL aparecem como *skipped*.

**Docker compose (NÃO testado):** `docker compose up --build` não foi executado: a sessão de desenvolvimento não tem
daemon do Docker. O que foi verificado foi o arquivo lido e a lógica equivalente fora do Docker. A imagem copia
`alembic.ini` e `migrations/` (`COPY backend/ .`) e o backend migra sozinho ao subir, mas isso **não foi confirmado
em contêiner**. O Dockerfile usa Python 3.12; os testes rodaram em 3.13.

## 3. Backup e restauração

Ferramenta: `python -m app.database.backup` (em `backend/`, usa `DATABASE_URL`).

```bash
python -m app.database.backup backup [--out backups]      # cria steady-AAAAMMDDTHHMMSSZ.sqlite|.dump
python -m app.database.backup verify ARQUIVO              # confere se o arquivo é legível
python -m app.database.backup restore ARQUIVO --yes       # PARE o backend antes
```

- **SQLite (testado):** usa a API de backup do próprio SQLite (cópia consistente mesmo com o banco em uso).
- **PostgreSQL (testado):** usa `pg_dump -Fc` e `pg_restore --clean --if-exists --single-transaction`. Precisa do
  cliente PostgreSQL (`pg_dump`, `pg_restore`) no PATH. A senha segue só pela variável `PGPASSWORD` do processo
  filho, nunca em argumentos (verificado por teste).
- **`restore` é destrutivo:** exige `--yes` e antes grava o estado atual em `*.pre-restore-*` na mesma pasta do
  backup. No PostgreSQL, se a restauração falhar no meio, nada fica pela metade (transação única).
- Os arquivos têm permissão 600 (contêm hashes de senha, auditoria e vendas). `backups/` está no `.gitignore`.
  **Guarde backups fora da máquina do banco**; um backup no mesmo disco não protege contra perda do disco.

**Com Docker compose (NÃO testado em contêiner):** os mesmos `pg_dump`/`pg_restore` por pipe foram testados fora do
Docker, apontando para um PostgreSQL real; dentro do compose os comandos seriam:

```bash
docker compose exec -T db pg_dump -U steady -Fc --no-owner steady > backups/steady.dump
docker compose stop backend
docker compose exec -T db pg_restore -U steady --clean --if-exists --no-owner --single-transaction -d steady < backups/steady.dump
docker compose start backend
```

## 4. Limites conhecidos
- **Instância única:** não há trava entre processos para migrar. Não suba duas réplicas do backend contra o mesmo
  banco ao mesmo tempo na primeira migração.
- **Backup é manual:** não há agendamento nem rotação. Também não há recuperação para um ponto no tempo.
- Restauração testada só na mesma versão do PostgreSQL (16) e do esquema (`0005`); entre versões diferentes não foi
  testada.
- A tabela `audit_logs` cresce sem limpeza (herdado da Fase 4).
