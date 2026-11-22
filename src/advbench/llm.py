"""Async LLM client for OpenAI and OpenRouter with retries, JSON parsing and a call log."""
from __future__ import annotations
import asyncio, json, os, re, time
from pathlib import Path
from openai import AsyncOpenAI

def _load_env():
    """Load KEY=VALUE lines from a .env at the repo root if present; the environment wins."""
    p = Path(__file__).resolve().parents[2] / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
_load_env()

_clients: dict[str, AsyncOpenAI] = {}
LOG = Path(__file__).resolve().parents[2] / "data" / "work" / "llm_calls.jsonl"

def client(provider: str) -> AsyncOpenAI:
    if provider not in _clients:
        if provider == "openai":
            _clients[provider] = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=900)
        else:
            _clients[provider] = AsyncOpenAI(api_key=os.environ["OPENROUTER_API_KEY"],
                                             base_url="https://openrouter.ai/api/v1", timeout=900)
    return _clients[provider]

MODELS = {
    "gpt55": ("openai", "gpt-5.5"),
    "mini": ("openai", "gpt-5.4-mini"),
    "qwen": ("openrouter", "qwen/qwen3.8-27b"),
}

# Model for generation and gating (default gpt-5.4-mini). The pilot docs were generated with gpt-5.5
# (ADV_MODEL=gpt55); 27 F2 questions were gated with gpt-5.4-mini.
GEN_MODEL = os.environ.get("ADV_MODEL", "mini")
MAX_EFFORT = os.environ.get("ADV_MAX_EFFORT", "medium")
_EFFORT_ORDER = ["minimal", "low", "medium", "high"]


def parse_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            return json.loads(text[s:e + 1])
        raise

async def chat(model_key: str, messages: list[dict], *, json_out: bool = False, effort: str | None = None,
               max_tokens: int | None = None, tag: str = "", retries: int = 4) -> tuple[str, dict]:
    provider, model = MODELS[model_key]
    if effort and effort in _EFFORT_ORDER and _EFFORT_ORDER.index(effort) > _EFFORT_ORDER.index(MAX_EFFORT):
        effort = MAX_EFFORT
    kw: dict = {"model": model, "messages": messages}
    if provider == "openai":
        if effort:
            kw["reasoning_effort"] = effort
        if json_out:
            kw["response_format"] = {"type": "json_object"}
        if max_tokens:
            kw["max_completion_tokens"] = max_tokens
    else:
        if max_tokens:
            kw["max_tokens"] = max_tokens
        if effort:
            kw["extra_body"] = {"reasoning": {"effort": effort}}
    last = None
    for attempt in range(retries):
        t0 = time.time()
        try:
            r = await client(provider).chat.completions.create(**kw)
            text = r.choices[0].message.content or ""
            usage = r.usage.model_dump() if r.usage else {}
            with LOG.open("a") as f:
                f.write(json.dumps({"t": time.time(), "tag": tag, "model": model, "secs": round(time.time() - t0, 1),
                                    "usage": usage}) + "\n")
            if json_out:
                parse_json(text)  # validate; raises to trigger retry
            return text, usage
        except Exception as e:  # noqa: BLE001
            last = e
            await asyncio.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{model_key} failed after {retries}: {last}")

async def gather_limited(coros, limit: int):
    sem = asyncio.Semaphore(limit)
    async def run(c):
        async with sem:
            return await c
    return await asyncio.gather(*(run(c) for c in coros), return_exceptions=True)
