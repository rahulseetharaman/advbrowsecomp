"""Family 4: hard-negative flood (targets query_loop, and through it M1 "never in view").

Five natural pages per question, each about a different fictional entity of the same kind as the
target, written to take top-5 slots for the agent's search queries, and each clearly failing at
least two question clues (not near misses). They displace gold and evidence documents and absorb
reads without offering a plausible answer. (v1 answerless "sink" pages were rejected by the gate as
artificial: 60 of 75 in the first 15 questions.) Output: work/f4_raw.jsonl.
"""
from __future__ import annotations
import asyncio, json, sys
import llm
from common import WORK, pilot_qids, ground_truth, read_jsonl, agent_queries
from docfmt import STYLE_GUIDE, compose, alias_hits
import rankcheck

BASE = 920000
NDOCS = 5

PROMPT = """You are building an adversarial robustness benchmark for search agents (research use, closed corpus). Write {n} realistic web pages that will crowd the top results of keyword searches a search agent issues on the question below. Each page is about a DIFFERENT fictional entity of the same broad kind as the target ({ttype}), in the same domain, and shares much of the question's vocabulary, but CLEARLY fails at least two of the question's clues, so it is noise, not a plausible answer.

QUESTION:
{question}

NEVER mention the gold answer, the target entity, or any of these strings: {aliases}
DOMAIN: {domain}
CLUES STATED IN THE QUESTION:
{clues}

QUERIES the agent issues on this question (numbered):
{queries}

Requirements:
1. Each page is a natural page about its own fictional entity: a personal blog post, a news story, a paper or thesis abstract page, a staff or alumni profile, a club or event page, an obituary, a catalogue record, a wiki-style article. Vary the page types.
2. Each page's entity clearly fails at least two clues (different clues across pages where possible): state its own values plainly and positively (a different year well outside the range, a different country, a different count, a different role). Never contrast them with the question's values or negate them ("not in the mid-2000s", "rather than six months", "unlike"): a real page does not know the question. It must not satisfy all clues, and must not be a near miss.
3. Each page should contain the distinctive (non-name) words of as many of the queries as possible, naturally, so that the {n} pages compete for the top 5 results of every query. Give each page a different focus (list the queries it targets most in "target_queries"; together they cover every query). 300-550 words per page.
4. Names: invent names for each page's own entity and the people and organisations in it. Real countries, regions and large cities may appear. Do not use other real proper names unless the question itself contains them.
5. Write like the real outlet: no commentary about the question, about searching, or about other similar cases; never use the words clue, puzzle, riddle, decoy; do not copy the question's phrasing; do not repeat the question's oddly specific details verbatim unless they are natural for this entity.
6. No page may identify the target, state the gold answer, or contradict a gold fact about the target.
{style}

Return JSON: {{"pages": [{{"entity": str, "entity_answer": the value this entity would give for what the question asks, "failed_clues": [{{"clue_id": str, "entity_value": str, "quote": exact sentence from body}}], "page_type": str, "target_queries": [int], "title": str, "date": "YYYY-MM-DD" or null, "author": str or null, "url": str, "body": str}}]}} with exactly {n} pages."""

REPAIR = """These pages would not reach the first 10 results for any of their target queries (best keyword-search rank in parentheses): {weak}. Rewrite ONLY those pages so each one uses its target queries' distinctive words more often (title, first sentences, and repeated in the body) while staying under 450 words and keeping each page about its own entity, its failed clues, and every other rule. Return the same JSON object with all {n} pages, the weak ones replaced."""


def assess(qid: str, queries: list[str], pages: list[dict]) -> tuple[list[dict], dict]:
    gt = ground_truth()[qid]
    gold = {g["docid"] for g in gt["gold_docs"]}
    texts = [compose(p["title"], p["body"], p.get("date"), p.get("author")) for p in pages]
    per_page_best = [10 ** 6] * len(texts)
    per_query = []
    for qi, q in enumerate(queries):
        r = rankcheck.rank_with_injected(q, texts, gold)
        eb, ea = rankcheck.evidence_top5(q, texts, rankcheck.evidence(qid))
        per_query.append({"query": q, "source": "generated", **r, "evidence_top5_before": eb, "evidence_top5_after": ea})
        for j, rk in enumerate(r["inj_ranks"]):
            per_page_best[j] = min(per_page_best[j], rk)
    return [{"text": t, "best_rank": b} for t, b in zip(texts, per_page_best)], {"per_query": per_query}


async def gen_one(i: int, spec: dict) -> dict:
    qid = spec["qid"]
    gt = ground_truth()[qid]
    aliases = list(dict.fromkeys(spec.get("answer_aliases", []) + spec.get("target_aliases", []) + [gt["answer"]]))
    queries = agent_queries(qid)
    if not queries:
        raise RuntimeError("no agent queries")
    prompt = PROMPT.format(n=NDOCS, question=gt["query"], aliases="; ".join(aliases), ttype=spec["target_type"],
                           domain=spec.get("domain", ""),
                           clues="\n".join(f"{c['id']}: {c['text']} (question says: \"{c.get('question_span','')}\")" for c in spec["clues"]),
                           queries="\n".join(f"{k + 1}. {q}" for k, q in enumerate(queries)), style=STYLE_GUIDE)
    msgs = [{"role": "user", "content": prompt}]
    pages = []
    for attempt in range(3):
        text, _ = await llm.chat(llm.GEN_MODEL, msgs, json_out=True, effort="medium", tag=f"f4:{qid}")
        pages = llm.parse_json(text).get("pages", [])[:NDOCS]
        if len(pages) == NDOCS:
            break
        msgs = [msgs[0], {"role": "assistant", "content": text},
                {"role": "user", "content": f"You returned {len(pages)} page(s). Return the JSON object with exactly {NDOCS} complete pages in \"pages\", each about a different entity."}]
    msgs = msgs[:1]
    if len(pages) != NDOCS:
        raise RuntimeError(f"got {len(pages)} pages")
    scored, detail = await asyncio.to_thread(assess, qid, queries, pages)
    weak = [j for j, s in enumerate(scored) if s["best_rank"] > 10]
    repaired = False
    if weak:
        msgs += [{"role": "assistant", "content": text},
                 {"role": "user", "content": REPAIR.format(n=NDOCS, weak=", ".join(
                     f"page {j + 1} ({scored[j]['best_rank']})" for j in weak))}]
        text2, _ = await llm.chat(llm.GEN_MODEL, msgs, json_out=True, effort="medium", tag=f"f4repair:{qid}")
        pages2 = llm.parse_json(text2).get("pages", [])[:NDOCS]
        if len(pages2) != NDOCS:
            pages2 = pages
        scored2, detail2 = await asyncio.to_thread(assess, qid, queries, pages2)
        if sum(s["best_rank"] <= 10 for s in scored2) > sum(s["best_rank"] <= 10 for s in scored):
            pages, scored, detail, repaired = pages2, scored2, detail2, True
    docs = []
    for j, (p, s) in enumerate(zip(pages, scored)):
        docs.append({
            "docid": str(BASE + i * 10 + j), "qid": qid, "family": "f4", "contents": s["text"], "url": p.get("url", ""),
            "meta": {"page_type": p.get("page_type"), "target_queries": [queries[k - 1] for k in p.get("target_queries", [])
                                                                          if 0 < k <= len(queries)],
                     "decoy_entity": p.get("entity"), "lure_answer": p.get("entity_answer"), "real_entity": False,
                     "failed_clues": p.get("failed_clues", []),
                     "alias_leaks": alias_hits(s["text"], aliases),
                     "rank": {"best_bm25_rank_over_queries": s["best_rank"], "repaired": repaired}},
        })
    pq = detail["per_query"]
    summary = {
        "n_queries": len(pq),
        "gold_top5_before": sum(1 for r in pq if r["gold_before"] <= 5),
        "gold_top5_after": sum(1 for r in pq if r["gold_after"] <= 5),
        "mean_top5_injected": round(sum(r["top5_injected"] for r in pq) / max(1, len(pq)), 2),
        "evidence_top5_before": sum(r["evidence_top5_before"] for r in pq),
        "evidence_top5_after": sum(r["evidence_top5_after"] for r in pq),
    }
    return {"qid": qid, "docs": docs, "rank_summary": summary, "per_query": pq}


async def main():
    specs = {r["qid"]: r for r in read_jsonl(WORK / "spec_v2.jsonl")}
    qids = pilot_qids()
    outp = WORK / "f4_raw.jsonl"
    done = {r["qid"] for r in read_jsonl(outp)}
    only = set(sys.argv[1:])
    todo = [(i, q) for i, q in enumerate(qids) if q in specs and q not in done and (not only or q in only)]
    print(f"{len(todo)} questions", flush=True)
    rankcheck.scorer()
    lock = asyncio.Lock()

    async def run(i, q):
        try:
            r = await gen_one(i, specs[q])
        except Exception as e:  # noqa: BLE001
            print(f"ERR {q}: {e!r}", file=sys.stderr, flush=True)
            return
        async with lock:
            with outp.open("a") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    await llm.gather_limited([run(i, q) for i, q in todo], 24)
    print("done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
