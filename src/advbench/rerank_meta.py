"""Recompute rank metadata of a family's raw docs against this repo's BM25 index and the agent queries."""
from __future__ import annotations
import sys
from common import WORK, read_jsonl, write_jsonl, agent_queries
import rankcheck

fam = sys.argv[1]
p = WORK / f"{fam}_raw.jsonl"
rows = read_jsonl(p)
for r in rows:
    if not r["docs"]:
        continue
    rk = rankcheck.query_ranks(r["qid"], [d["contents"] for d in r["docs"]], agent_queries(r["qid"]))
    for d, pd in zip(r["docs"], rk["per_doc"]):
        old = d["meta"].get("rank", {})
        d["meta"]["rank"] = {**pd, "repaired": old.get("repaired")}
        if old.get("bm25_lure_plus_question_rank") is not None:
            d["meta"]["rank"]["bm25_lure_plus_question_rank"] = old["bm25_lure_plus_question_rank"]
    r["per_query"] = rk["per_query"]
write_jsonl(p, rows)
print(f"{fam}: re-ranked {len(rows)} questions")
