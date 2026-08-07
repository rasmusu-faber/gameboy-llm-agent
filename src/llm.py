"""LLM backend: local Ollama or any OpenAI-compatible cloud endpoint.

Mirrors the relocation-assistant-rag `generator.py` pattern: one call, a provider
switch, and an OpenAI-compatible `base_url` so it points at ANY host
(Together / OpenRouter / DeepInfra / …). Configure with env vars (see
`.env.example`); the key lives only in `.env` (git-ignored), never in code.

  LLM_BACKEND = ollama | openai        (default: ollama)
  OLLAMA_BASE_URL, OLLAMA_MODEL
  OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL

Local `llama3.2:3b` is the free/offline default. Point OPENAI_* at a cloud host
of the SAME model (e.g. Together's `meta-llama/Llama-3.2-3B-Instruct-Turbo`) for
sub-second responses while testing, or at a stronger model for real runs.
"""

import json
import os
import time
from pathlib import Path

import httpx


def _load_dotenv():
    """Minimal KEY=VALUE loader for a repo-root .env - no extra dependency."""
    env = Path(__file__).resolve().parents[1] / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

BACKEND = os.environ.get("LLM_BACKEND", "ollama").lower()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "")


def model_name() -> str:
    return OPENAI_MODEL if BACKEND == "openai" else OLLAMA_MODEL


MAX_RETRIES = 4                # attempts on a 429 before giving up to the fallback
RETRY_CAP = 20.0               # never wait longer than this on one backoff

# Optional viewer-friendly sleep: the agent sets this to viewer.sleep so backoff
# waits pump the Tk event loop instead of freezing the window (white on Windows).
# Default None -> a plain blocking time.sleep (correct for headless runs).
WAIT_HOOK = None


def _wait(seconds: float) -> None:
    (WAIT_HOOK or time.sleep)(seconds)


def _retry_after(resp, fallback: float) -> float:
    """Seconds to wait per the server's Retry-After header (Groq sends one on a
    429), capped; fall back to a caller-supplied backoff if it's missing/unparsable."""
    raw = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
    try:
        return min(float(raw), RETRY_CAP) if raw is not None else min(fallback, RETRY_CAP)
    except (TypeError, ValueError):
        return min(fallback, RETRY_CAP)


def chat_json(system: str, user: str, timeout: float = 120.0) -> dict:
    """Send a system+user prompt, expect a JSON object, return it parsed.

    Returns {} if the model didn't produce valid JSON, so callers can validate
    without try/except at every site. On a 429 (rate limit) it retries with a
    Retry-After-honoring backoff - which both keeps the LLM in the loop and
    naturally paces rapid runs under the provider's per-minute cap - only degrading
    to {} (the explore fallback) once retries are exhausted.
    """
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    content = None
    for attempt in range(MAX_RETRIES):
        try:
            content = (_openai(messages, timeout) if BACKEND == "openai"
                       else _ollama(messages, timeout))
            break
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                wait = _retry_after(e.response, fallback=2.0 * (attempt + 1))
                print(f"  [llm] 429 rate-limited; retry {attempt + 1}/{MAX_RETRIES - 1} "
                      f"in {wait:.1f}s")
                _wait(wait)
                continue
            print(f"  [llm] request failed: {type(e).__name__}: {str(e)[:80]}")
            return {}
        except Exception as e:                   # network / timeout / etc.
            print(f"  [llm] request failed: {type(e).__name__}: {str(e)[:80]}")
            return {}
    if content is None:
        return {}
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {}


def _ollama(messages, timeout):
    resp = httpx.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": OLLAMA_MODEL, "messages": messages,
              "stream": False, "format": "json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _openai(messages, timeout):
    if not (OPENAI_BASE_URL and OPENAI_API_KEY and OPENAI_MODEL):
        raise RuntimeError(
            "LLM_BACKEND=openai needs OPENAI_BASE_URL, OPENAI_API_KEY and "
            "OPENAI_MODEL - set them in .env (never in code).")
    resp = httpx.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={"model": OPENAI_MODEL, "messages": messages,
              "temperature": 0.3,
              "response_format": {"type": "json_object"}},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
