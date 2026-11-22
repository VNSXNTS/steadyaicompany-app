"""Backup e restauração do banco (SQLite e PostgreSQL). Uso, com a aplicação PARADA para restaurar:

    python -m app.database.backup backup [--out DIR]
    python -m app.database.backup verify ARQUIVO
    python -m app.database.backup restore ARQUIVO --yes

Segurança: a senha do PostgreSQL só viaja na variável de ambiente PGPASSWORD do processo filho; nunca
em argumentos de linha de comando nem em saída. `restore` é destrutivo: exige --yes e antes grava uma
cópia de segurança do estado atual (`*.pre-restore-*`). Os arquivos de backup contêm hashes de senha,
auditoria e vendas: ficam com permissão 600 e a pasta `backups/` está no .gitignore.
"""
import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings


class BackupError(RuntimeError):
    pass


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:  # sistemas de arquivos sem permissão POSIX (ex.: Windows)
        pass


def _sqlite_path(url: str) -> Path:
    path = make_url(url).database
    if not path or path == ":memory:":
        raise BackupError("banco SQLite em memória não tem arquivo para copiar")
    return Path(path)


def _pg_env_and_args(url: str) -> tuple[dict[str, str], list[str], str]:
    u = make_url(url)
    env = dict(os.environ)
    if u.password:
        env["PGPASSWORD"] = u.password
    args = ["-h", u.host or "localhost", "-p", str(u.port or 5432)]
    if u.username:
        args += ["-U", u.username]
    return env, args, u.database or ""


def _run(cmd: list[str], env: dict[str, str]) -> None:
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise BackupError(f"ferramenta não encontrada: {cmd[0]} (instale o cliente PostgreSQL)") from exc
    if result.returncode != 0:
        raise BackupError(f"{cmd[0]} falhou (código {result.returncode}): {result.stderr.strip()[:500]}")


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def backup(url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if _is_sqlite(url):
        dest = out_dir / f"steady-{_stamp()}.sqlite"
        src = sqlite3.connect(_sqlite_path(url))
        try:
            dst = sqlite3.connect(dest)
            try:
                src.backup(dst)  # cópia consistente mesmo com o banco em uso
            finally:
                dst.close()
        finally:
            src.close()
    else:
        dest = out_dir / f"steady-{_stamp()}.dump"
        env, args, dbname = _pg_env_and_args(url)
        _run(["pg_dump", *args, "-Fc", "--no-owner", "-f", str(dest), dbname], env)
    _chmod_private(dest)
    verify(url, dest)
    return dest


def verify(url: str, file: Path) -> None:
    """Confere que o arquivo é um backup legível (não prova que o conteúdo está certo)."""
    if not file.is_file():
        raise BackupError(f"arquivo não encontrado: {file}")
    if _is_sqlite(url):
        con = sqlite3.connect(f"file:{file}?mode=ro", uri=True)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("integrity_check do backup SQLite falhou")
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").fetchone() is None:
                raise BackupError("o arquivo não parece um backup deste sistema (sem alembic_version)")
        except sqlite3.DatabaseError as exc:
            raise BackupError(f"arquivo SQLite inválido: {exc}") from exc
        finally:
            con.close()
    else:
        env, _, _ = _pg_env_and_args(url)
        _run(["pg_restore", "--list", str(file)], env)


def restore(url: str, file: Path, *, confirmed: bool) -> Path:
    """Restaura `file` sobre o banco atual. Devolve o caminho da cópia de segurança do estado anterior."""
    if not confirmed:
        raise BackupError("restore sobrescreve o banco atual; repita com --yes")
    verify(url, file)
    safety_dir = file.parent
    if _is_sqlite(url):
        live = _sqlite_path(url)
        safety = safety_dir / f"{live.stem}.pre-restore-{_stamp()}.sqlite"
        if live.exists():
            src = sqlite3.connect(live)
            try:
                dst = sqlite3.connect(safety)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            _chmod_private(safety)
        src = sqlite3.connect(f"file:{file}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(live)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return safety
    env, args, dbname = _pg_env_and_args(url)
    safety = safety_dir / f"steady.pre-restore-{_stamp()}.dump"
    _run(["pg_dump", *args, "-Fc", "--no-owner", "-f", str(safety), dbname], env)
    _chmod_private(safety)
    # --single-transaction: se algo falhar no meio, o banco volta ao estado anterior (nada pela metade).
    _run(["pg_restore", *args, "--clean", "--if-exists", "--no-owner", "--single-transaction",
          "-d", dbname, str(file)], env)
    return safety


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.database.backup")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--out", default="backups")
    v = sub.add_parser("verify")
    v.add_argument("file")
    r = sub.add_parser("restore")
    r.add_argument("file")
    r.add_argument("--yes", action="store_true", help="confirma a sobrescrita do banco atual")
    args = parser.parse_args(argv)
    url = get_settings().database_url
    try:
        if args.cmd == "backup":
            print(f"backup criado: {backup(url, Path(args.out))}")
        elif args.cmd == "verify":
            verify(url, Path(args.file))
            print("arquivo legível")
        else:
            safety = restore(url, Path(args.file), confirmed=args.yes)
            print(f"restaurado. Estado anterior guardado em: {safety}")
    except BackupError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
