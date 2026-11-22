"""Agent-style search queries per question (gpt-5.5), shared by F1/F2 rank checks and F4 targeting.

Stands in for real agent search logs, which this repo's scaffold has not produced yet for the
pilot. Output: work/agent_queries.jsonl {"qid", "queries"}.
"""
from __future__ import annotations
import asyncio, json, sys
import llm
from common import WORK, pilot_qids, ground_truth, read_jsonl
from docfmt import alias_hits

N = 8
PROMPT = """A search agent with a keyword search engine (BM25, top 5 results per query) over a web crawl is working on the question below. Write the {n} search queries it would most likely issue over its run, in order: short keyword queries (3-9 words) combining distinctive terms from the clues, the kind an agent types. Include early broad queries and later narrower ones. Do not include the answer or any of these strings: {aliases}

QUESTION:
{question}

Return JSON: {{"queries": [str]}}"""


async def one(spec: dict) -> dict:
    gt = ground_truth()[spec["qid"]]
    aliases = list(dict.fromkeys(spec.get("answer_aliases", []) + spec.get("target_aliases", []) + [gt["answer"]]))
    text, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": PROMPT.format(n=N, aliases="; ".join(aliases),
                             question=gt["query"])}], json_out=True, effort="low", tag=f"queries:{spec['qid']}")
    qs = [q for q in llm.parse_json(text).get("queries", []) if q and not alias_hits(q, aliases)]
    return {"qid": spec["qid"], "queries": qs[:N]}


async def main():
    specs = {r["qid"]: r for r in read_jsonl(WORK / "spec_v2.jsonl")}
    outp = WORK / "agent_queries.jsonl"
    done = {r["qid"] for r in read_jsonl(outp)}
    todo = [q for q in pilot_qids() if q in specs and q not in done]
    res = await llm.gather_limited([one(specs[q]) for q in todo], 32)
    with outp.open("a") as f:
        for q, r in zip(todo, res):
            if isinstance(r, Exception):
                print(f"ERR {q}: {r}", file=sys.stderr)
                continue
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"done {len(todo)}")


if __name__ == "__main__":
    asyncio.run(main())
