"""Shared paths and loaders for the advbench generation pipeline."""
from __future__ import annotations
import json, os, re
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# BrowseComp-Plus checkout: decrypted data, BM25 index and search agent.
BCP = Path(os.environ.get("BCP_ROOT", REPO.parent / "BrowseComp-Plus"))
GEN = REPO / "data" / "attacks"          # gated documents per family: <family>/docs.jsonl, validation.jsonl
WORK = REPO / "data" / "work"            # specs, queries, closed-book guesses, raw (pre-gate) generations
PILOT = REPO / "data" / "pilot" / "pilot100.json"
GT = BCP / "data" / "browsecomp_plus_decrypted.jsonl"
INDEX = str(BCP / "indexes" / "bm25")    # same index and BM25 settings as searcher/searchers/bm25_searcher.py


def pilot_qids() -> list[str]:
    return [str(q) for q in json.loads(PILOT.read_text())["query_ids"]]


@lru_cache(None)
def ground_truth() -> dict:
    out = {}
    for line in GT.open():
        d = json.loads(line)
        out[str(d["query_id"])] = d
    return out


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.open() if l.strip()]


def write_jsonl(p: Path, rows) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def gold_excerpt(text: str, answer: str, head: int = 5000, win: int = 700, max_wins: int = 3) -> str:
    """Head of the doc plus windows around answer mentions that fall past the head."""
    out = text[:head]
    if len(text) <= head:
        return out
    low = text.lower()
    toks = [answer.lower()] + [t for t in re.split(r"[\s,;:()]+", answer.lower()) if len(t) >= 5]
    wins = []
    for t in toks:
        start = head
        while len(wins) < max_wins:
            i = low.find(t, start)
            if i < 0:
                break
            wins.append((max(head, i - win // 2), i + win // 2))
            start = i + win
        if wins:
            break
    for s, e in wins:
        out += "\n[...]\n" + text[s:e]
    return out + "\n[...document continues...]"


def agent_queries(qid: str) -> list[str]:
    """Agent-style search queries generated for this question (work/agent_queries.jsonl)."""
    for r in read_jsonl(WORK / "agent_queries.jsonl"):
        if r["qid"] == qid:
            return r["queries"]
    return []
