"""Verifica o Ollama REAL configurado (OLLAMA_URL, OLLAMA_MODEL). Rode na sua máquina: `python scripts/check_ollama.py`.

Mostra se o servidor responde, se o modelo está instalado e faz UMA chamada curta para conferir resposta, tokens e
tempo. Não usa nada pago. Use --no-generate para só checar disponibilidade (sem gerar texto).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services.llm import OllamaProvider  # noqa: E402


def main() -> int:
    s = get_settings()
    provider = OllamaProvider(s.ollama_url, s.ollama_model)
    ok, detail = provider.check()
    print(f"[{'OK' if ok else 'FALHOU'}] {detail}")
    if not ok or "--no-generate" in sys.argv:
        return 0 if ok else 1
    start = time.monotonic()
    try:
        r = provider.complete("Você é um verificador de conexão.", "Responda apenas com a palavra: ok")
    except Exception as exc:
        print(f"[FALHOU] geração: {type(exc).__name__}: {exc}")
        return 1
    print(f"[OK] resposta em {time.monotonic() - start:.1f}s | tokens entrada={r.prompt_tokens} saída={r.completion_tokens}")
    print(f"     texto: {r.text.strip()[:200]!r}")
    if r.prompt_tokens == 0 and r.completion_tokens == 0:
        print("[ATENÇÃO] o servidor não informou tokens; o painel de consumo mostrará zero para esta chamada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
