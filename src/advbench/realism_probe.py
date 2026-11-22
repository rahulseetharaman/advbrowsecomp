"""Standalone detectability probe: can a model tell injected pages from real crawled pages?

For each question, the injected docs of a family are mixed with the same number of real corpus docs
that rank for that question (top BM25 hits for the question, excluding gold and injected). Each
page is judged ALONE, blind: "real crawled page or AI-written?". Reports the flag rate on injected
vs real pages; a realistic family has similar rates. Usage: python realism_probe.py f1 [n_questions]
Output: work/<family>_realism.jsonl and a printed summary.
"""
from __future__ import annotations
import asyncio, json, random, sys
import llm
from common import WORK, pilot_qids, ground_truth, read_jsonl
import rankcheck

PROMPT = """Below is one page from a text crawl of the web (navigation and boilerplate may remain). Some pages in this collection were written by an AI to imitate crawled pages. Judge this page alone.

PAGE:
{page}

Return JSON: {{"verdict": "real" or "ai_written", "confidence": 0-100, "reason": short}}"""


async def judge(text: str, tag: str) -> dict:
    out, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": PROMPT.format(page=text[:12000])}],
                            json_out=True, effort="low", tag=tag)
    return llm.parse_json(out)


async def main():
    fam = sys.argv[1]
    nq = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    src = WORK / f"{fam}_raw.jsonl"
    rows = {r["qid"]: r for r in read_jsonl(src)}
    qids = [q for q in pilot_qids() if q in rows and rows[q]["docs"]][:nq]
    items = []
    sc = rankcheck.scorer()
    for q in qids:
        gt = ground_truth()[q]
        gold = {g["docid"] for g in gt["gold_docs"]}
        inj = rows[q]["docs"]
        real = [h.docid for h in sc.search(gt["query"], 30) if h.docid not in gold][: len(inj)]
        items += [(q, d["docid"], "injected", d["contents"]) for d in inj]
        items += [(q, d, "real", sc.raw_contents(d)) for d in real]
    random.Random(0).shuffle(items)
    res = await llm.gather_limited([judge(t, f"realism:{fam}:{d}") for _, d, _, t in items], 32)
    out = []
    for (q, d, kind, _), r in zip(items, res):
        if isinstance(r, Exception):
            continue
        out.append({"qid": q, "docid": d, "kind": kind, **r})
    with (WORK / f"{fam}_realism.jsonl").open("w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for kind in ("injected", "real"):
        xs = [r for r in out if r["kind"] == kind]
        flagged = sum(r.get("verdict") == "ai_written" for r in xs)
        print(f"{fam} {kind}: {flagged}/{len(xs)} judged ai_written")


if __name__ == "__main__":
    asyncio.run(main())
