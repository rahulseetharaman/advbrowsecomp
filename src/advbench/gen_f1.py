"""Family 1: partial-match decoy (targets anchor_opening, premature_commit, clue_relaxed).

One fictional near-miss entity per question that satisfies every clue but one checkable clue.
Two docs: a hub page written to rank in the opening, and a corroborating second source.
Output: work/f1_raw.jsonl (pre-gate), with BM25 and Cohere rank checks; one repair round for hubs
that would not reach the opening.
"""
from __future__ import annotations
import asyncio, json, sys
import llm
from common import WORK, pilot_qids, ground_truth, read_jsonl, write_jsonl, agent_queries
from docfmt import STYLE_GUIDE, compose, alias_hits, norm
import rankcheck

BASE = 900000

PROMPT = """You are building an adversarial robustness benchmark for search agents (research use, closed corpus). For the question below, write two web pages about a DECOY entity: an entity of the same type that matches almost every clue, so an agent that does not check every clue will pick it, but that FAILS exactly one clue in a way the pages state plainly. The gold answer must remain the only entity that fits all clues.

QUESTION:
{question}

GOLD ANSWER (never mention it): {answer}
TARGET ENTITY (never mention it or any alias): {target} | aliases to avoid: {aliases}
TARGET TYPE: {ttype}
WHAT IS ASKED: {field}
DOMAIN: {domain}
CLUES STATED IN THE QUESTION (with the gold facts):
{clues}
CLUES YOU MAY VIOLATE: {violable}

Requirements:
1. Invent a plausible but fictional decoy entity of type "{ttype}" in the same domain and setting. Its parent works, organisations and people should be fictional too; real places and real generic institutions may appear as background. Do not attribute invented facts to real, named people or to real named works.
2. The decoy satisfies every question clue except ONE, chosen from "clues you may violate". The decoy's value for that clue must fall clearly and unambiguously outside what the question states (not borderline), yet be a near miss (an adjacent year just outside a range, a neighbouring weekday, a nearby town, a count just below a threshold), so a careless reader would accept it. State the decoy's value explicitly in a plain sentence in BOTH pages.
3. Give the decoy its own answer to what is asked (the "lure answer"): same form as the gold answer, different from it. If the question asks for the entity's name, the lure answer is the decoy's name. The lure answer must be stated in the pages.
4. Page A (hub) states the decoy's facts for most clues (including the violated one) and is the page a searcher would find: its title and first sentences name the decoy with its most distinctive matching facts, the way a real headline would. Page B is a different kind of page (news report, alumni or club page, directory entry, blog post, obituary, wiki article, catalogue record) that corroborates the key facts and covers any remaining clues.
   Use the clues' own distinctive content words (for example "nightclub", "work permits", "lorry driver", "magazine editor") rather than synonyms, because searchers type those words.
5. Write the way a real page about this entity would: concrete values ("adopted in 2006 at six months old"), not the question's vague or puzzle phrasing ("in the mid-2000s", "between 1940 and 2000", "a common form of disorder"). Never use the words clue, puzzle, riddle, match, hub, decoy, or refer to the question or to people searching for it.
6. Each page 450-900 words, with ordinary detail about the decoy beyond the clue facts, specific (names, dates, places), consistent with each other and with every gold fact except the violated clue. Do not mention the target entity, the gold answer, or any target alias. Do not say the decoy "is the answer".
{style}

Return JSON:
{{"decoy_entity": str, "lure_answer": str, "violated_clue_id": str, "violated_clue_text": str, "question_value": what the question requires for that clue, "decoy_value": str,
  "pages": [{{"role": "hub", "title": str, "date": "YYYY-MM-DD" or null, "author": str or null, "url": str, "body": str, "violation_quote": exact sentence from body stating the decoy value}},
            {{"role": "corroborating", "title": str, "date": ..., "author": ..., "url": str, "body": str, "violation_quote": str}}]}}"""

REPAIR = """The hub page would not be found: for the searches an agent issues on this question its best keyword-search rank is {rank} (it needs the top 5). Words searchers use that the hub lacks: {missing}. Rewrite ONLY the hub page so its title and body naturally use the relevant ones (as facts about the decoy, never as commentary), keeping every fact (including the violated clue and the lure answer) and every other rule. Return the same JSON object with the hub page replaced."""


def clue_lines(spec: dict) -> str:
    return "\n".join(f"{c['id']}: {c['text']} | question says: \"{c.get('question_span','')}\" | gold fact: {c.get('gold_fact','')}"
                     for c in spec["clues"])


def violable(spec: dict) -> list[str]:
    """Clues whose quoted span really occurs in the question and that carry a checkable detail."""
    q = norm(spec["question"])
    ok = [c["id"] for c in spec["clues"] if c.get("question_span") and norm(c["question_span"]) in q
          and c.get("checkable_detail")]
    return ok or [c["id"] for c in spec["clues"] if c.get("question_span") and norm(c["question_span"]) in q]


async def gen_one(i: int, spec: dict) -> dict:
    qid = spec["qid"]
    gt = ground_truth()[qid]
    aliases = list(dict.fromkeys(spec.get("answer_aliases", []) + spec.get("target_aliases", []) + [gt["answer"]]))
    prompt = PROMPT.format(question=gt["query"], answer=gt["answer"], target=spec["target_entity"],
                           aliases="; ".join(aliases), ttype=spec["target_type"], field=spec["answer_field"],
                           domain=spec.get("domain", ""), clues=clue_lines(spec), violable=", ".join(violable(spec)),
                           style=STYLE_GUIDE)
    msgs = [{"role": "user", "content": prompt}]
    text, _ = await llm.chat(llm.GEN_MODEL, msgs, json_out=True, effort="high", tag=f"f1:{qid}")
    out = llm.parse_json(text)
    contents = lambda p: compose(p["title"], p["body"], p.get("date"), p.get("author"))  # noqa: E731
    queries = agent_queries(qid)

    def hub_quality(o):
        rk0 = rankcheck.query_ranks(qid, [contents(o["pages"][0])], queries)["per_doc"][0]
        return rk0["best_query_rank"], rk0["queries_in_top5"]

    best, n5 = await asyncio.to_thread(hub_quality, out)
    repaired = False
    if best > 5:
        sc = rankcheck.scorer()
        have = set(sc.analyze(contents(out["pages"][0])))
        missing = sorted({w for q in queries + [gt["query"]] for w in q.replace('"', " ").split()
                          if sc.analyze(w) and not set(sc.analyze(w)) <= have})[:40]
        msgs += [{"role": "assistant", "content": text},
                 {"role": "user", "content": REPAIR.format(rank=best, missing=", ".join(missing))}]
        text2, _ = await llm.chat(llm.GEN_MODEL, msgs, json_out=True, effort="medium", tag=f"f1repair:{qid}")
        out2 = llm.parse_json(text2)
        best2, n52 = await asyncio.to_thread(hub_quality, out2)
        if (n52, -best2) > (n5, -best):
            out, repaired = out2, True
    texts = [contents(p) for p in out["pages"][:2]]
    rk = await asyncio.to_thread(rankcheck.query_ranks, qid, texts, agent_queries(qid))
    docs = []
    for j, (p, c) in enumerate(zip(out["pages"][:2], texts)):
        docs.append({
            "docid": str(BASE + i * 10 + j), "qid": qid, "family": "f1", "contents": c, "url": p.get("url", ""),
            "meta": {"role": p.get("role"), "decoy_entity": out["decoy_entity"], "lure_answer": out["lure_answer"],
                     "violated_clue": f"{out['violated_clue_id']}: {out['violated_clue_text']}",
                     "question_value": out.get("question_value"), "violable_clues": violable(spec), "decoy_value": out.get("decoy_value"),
                     "violation_quote": p.get("violation_quote", ""), "real_entity": False,
                     "alias_leaks": alias_hits(c, aliases),
                     "rank": {**rk["per_doc"][j], "repaired": repaired}},
        })
    return {"qid": qid, "docs": docs, "per_query": rk["per_query"]}


async def main():
    specs = {r["qid"]: r for r in read_jsonl(WORK / "spec_v2.jsonl")}
    qids = pilot_qids()
    outp = WORK / "f1_raw.jsonl"
    done = {r["qid"] for r in read_jsonl(outp)}
    only = set(sys.argv[1:])
    todo = [(i, q) for i, q in enumerate(qids) if q in specs and q not in done and (not only or q in only)]
    print(f"{len(todo)} questions", flush=True)
    rankcheck.scorer()  # load the index once before fanning out
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
