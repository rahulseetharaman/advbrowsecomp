"""Rank checks for injected docs: BM25 (offline scorer) and Cohere opening position."""
from __future__ import annotations
from functools import lru_cache
from common import ground_truth

_scorer = None


def scorer():
    global _scorer
    if _scorer is None:
        import bm25score
        _scorer = bm25score.Scorer()
    return _scorer


@lru_cache(None)
def _hits(query: str, k: int):
    return scorer().search(query, k)


def bm25_rank(query: str, text: str, k: int = 1000) -> tuple[int, float]:
    return scorer().rank_of(query, text, k=k, hits=_hits(query, k))


def gold_best_rank(query: str, gold: set[str], k: int = 1000) -> int:
    for i, h in enumerate(_hits(query, k), 1):
        if h.docid in gold:
            return i
    return k + 1


@lru_cache(None)
def evidence(qid: str) -> frozenset:
    gt = ground_truth()[qid]
    return frozenset(d["docid"] for d in gt.get("evidence_docs", [])) | frozenset(d["docid"] for d in gt["gold_docs"])


def evidence_top5(query: str, injected: list[str], ev: frozenset) -> tuple[int, int]:
    """Evidence docs (qrels evidence, incl. gold) in the top 5 before and after injection."""
    hits = _hits(query, 1000)[:5]
    before = sum(1 for h in hits if h.docid in ev)
    inj = [scorer().score(query, t) for t in injected]
    merged = sorted([(h.score, h.docid in ev) for h in hits] + [(x, False) for x in inj], reverse=True)[:5]
    return before, sum(1 for _, e in merged if e)


def rank_with_injected(query: str, injected: list[str], gold: set[str], k: int = 1000) -> dict:
    """Gold's best rank before/after adding the injected texts, and top-5 slots they take."""
    hits = _hits(query, k)
    inj_scores = [scorer().score(query, t) for t in injected]
    before = gold_best_rank(query, gold, k)
    gold_score = next((h.score for h in hits if h.docid in gold), None)
    if gold_score is None:
        after = k + 1
    else:
        after = before + sum(1 for s in inj_scores if s > gold_score)
    inj_ranks = [1 + sum(1 for h in hits if h.score > s) for s in inj_scores]
    # rank within the merged list: injected docs also outrank each other
    merged = sorted([(h.score, "o") for h in hits[:10]] + [(s, "i") for s in inj_scores], reverse=True)
    top5_inj = sum(1 for s, kind in merged[:5] if kind == "i")
    return {"gold_before": before, "gold_after": after, "inj_ranks": inj_ranks, "top5_injected": top5_inj}


def query_ranks(qid: str, texts: list[str], queries: list[str]) -> dict:
    """Per injected text: BM25 rank for the question and best rank / top-5 hits over agent queries.
    Plus, per query, gold's best rank before and after injection (this repo's agent sees top 5)."""
    gt = ground_truth()[qid]
    gold = {g["docid"] for g in gt["gold_docs"]}
    per_doc = [{"bm25_question_rank": bm25_rank(gt["query"], t)[0], "best_query_rank": 10 ** 6, "queries_in_top5": 0}
               for t in texts]
    per_query = []
    ev = evidence(qid)
    for q in queries:
        r = rank_with_injected(q, texts, gold)
        eb, ea = evidence_top5(q, texts, ev)
        per_query.append({"query": q, **r, "evidence_top5_before": eb, "evidence_top5_after": ea})
        for j, rk in enumerate(r["inj_ranks"]):
            per_doc[j]["best_query_rank"] = min(per_doc[j]["best_query_rank"], rk)
            per_doc[j]["queries_in_top5"] += int(rk <= 5)
    return {"per_doc": per_doc, "per_query": per_query}
