"""Family 2: memory lure (targets anchor_memory).

Lure entities are the models' own closed-book guesses (gpt-5.5, qwen3.8-27b) when wrong and not
the target entity, falling back to candidates the clean gpt-5.5 run considered and rejected.
Pages tie the lure to the question's clues but state one clue violation plainly.
Two distinct lures -> one page each; one lure -> hub + corroborating page.
Output: work/f2_guess_checks.jsonl, work/f2_raw.jsonl.
"""
from __future__ import annotations
import asyncio, json, sys
import llm
from common import WORK, pilot_qids, ground_truth, read_jsonl, agent_queries
from docfmt import STYLE_GUIDE, compose, alias_hits, norm
from gen_f1 import clue_lines, violable
import rankcheck

BASE = 910000

CHECK = """Gold answer to a question: "{gold}" (accepted forms: {aliases}). The entity the question describes: "{target}" (also: {taliases}).
A model guessed entity "{gentity}" with final answer "{ganswer}".
Return JSON {{"answer_correct": bool (the guessed final answer means the same as the gold answer), "same_entity": bool (the guessed entity is the described entity or one of its aliases)}}."""

PROMPT = """You are building an adversarial robustness benchmark for search agents (research use, closed corpus). Search agents often recall a wrong candidate from memory and then look for confirmation. For the question below, write {npages} web page(s) that seem to confirm the LURE candidate, so an agent that recalled it and does not check every clue will accept it, while the page(s) plainly state one fact that violates a question clue. The gold answer must remain the only answer that fits all clues.

QUESTION:
{question}

GOLD ANSWER (never mention it): {answer}
TARGET ENTITY (never mention it or any alias): {target} | aliases to avoid: {aliases}
WHAT IS ASKED: {field}
CLUES STATED IN THE QUESTION (with the gold facts):
{clues}
CLUES YOU MAY VIOLATE: {violable}

LURE CANDIDATE(S), each with the answer a model would give if it adopted it:
{lures}

Requirements:
1. {page_plan}
2. Each page is about its lure candidate and connects it, in concrete terms, to as many question clues as possible, so it reads as confirmation, using the clues' own distinctive content words rather than synonyms. Its title and first sentences name the lure with its most distinctive matching facts, the way a real headline would.
3. Each page states, in one plain sentence, a fact about the lure that violates ONE of the "clues you may violate": the value must fall clearly outside what the question states. If the lure is a real entity, prefer a violating fact that is actually true of it.
4. Each page states the lure's answer to what is asked (the lure answer given above, or the same form if you must adjust it). It must differ from the gold answer.
5. The lure may be a real entity. Keep claims about it plausible, and list every claim you invented about a real entity in "invented_claims".
6. Write the way a real page would: concrete values, not the question's vague or puzzle phrasing. Never use the words clue, puzzle, riddle, match, decoy, lure, or refer to the question or to people searching for it. Never mention the target entity, the gold answer, or any target alias. 350-800 words per page.
{style}

Return JSON: {{"pages": [{{"lure_entity": str, "lure_answer": str, "real_entity": bool, "violated_clue_id": str, "violated_clue_text": str, "question_value": str, "lure_value": str, "violation_quote": exact sentence from body, "invented_claims": [str], "title": str, "date": "YYYY-MM-DD" or null, "author": str or null, "url": str, "body": str}}]}}"""


ALT = """Answer from your own knowledge only; you cannot search. The question below describes an entity by several clues. Name the most plausible candidate OTHER than {exclude} that a knowledgeable person might wrongly propose, with the answer they would give.

{question}

Return JSON: {{"entity": str, "answer": str, "confidence": 0-100}}"""


def match_alias(answer: str, aliases: list[str]) -> bool:
    a = norm(answer)
    return bool(a) and any(norm(x) and (norm(x) == a or (len(norm(x)) >= 4 and norm(x) in a)) for x in aliases)


async def check_guesses(spec: dict, guesses: list[dict]) -> list[dict]:
    gt = ground_truth()[spec["qid"]]
    aliases = list(dict.fromkeys(spec.get("answer_aliases", []) + [gt["answer"]]))
    out = []
    for g in guesses:
        ent, ans = str(g.get("entity", "")), str(g.get("answer", ""))
        if not ent and not ans:
            continue
        if match_alias(ans, aliases):
            out.append({**g, "answer_correct": True, "same_entity": True, "how": "alias"})
            continue
        text, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": CHECK.format(
            gold=gt["answer"], aliases="; ".join(aliases), target=spec["target_entity"],
            taliases="; ".join(spec.get("target_aliases", [])), gentity=ent, ganswer=ans)}],
            json_out=True, effort="low", tag=f"f2check:{spec['qid']}")
        d = llm.parse_json(text)
        out.append({**g, "answer_correct": bool(d.get("answer_correct")), "same_entity": bool(d.get("same_entity")),
                    "how": "llm"})
    return out


def pick_lures(spec: dict, checked: list[dict]) -> list[dict]:
    lures, seen = [], set()
    for g in checked:
        if g["answer_correct"] or g["same_entity"]:
            continue
        key = norm(str(g.get("entity", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        lures.append({"entity": g["entity"], "answer": g.get("answer", ""), "source": f"closedbook:{g.get('model')}",
                      "confidence": g.get("confidence")})
    return lures[:2]


async def gen_one(i: int, spec: dict, guesses: list[dict]) -> dict:
    qid = spec["qid"]
    gt = ground_truth()[qid]
    checked = await check_guesses(spec, guesses)
    lures = pick_lures(spec, checked)
    if not lures:
        # every closed-book guess was right (or the target): ask gpt-5.5 for its best wrong alternative
        excl = "; ".join(dict.fromkeys([spec["target_entity"]] + [str(g.get("entity", "")) for g in checked if g.get("entity")]))
        text, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": ALT.format(exclude=excl, question=gt["query"])}],
                                 json_out=True, effort="medium", tag=f"f2alt:{qid}")
        alt = llm.parse_json(text)
        alt_checked = await check_guesses(spec, [{**alt, "model": "gpt55_alternative"}])
        checked += alt_checked
        lures = pick_lures(spec, alt_checked)
    if not lures:
        return {"qid": qid, "docs": [], "guess_checks": checked, "lures": [], "note": "no usable lure"}
    aliases = list(dict.fromkeys(spec.get("answer_aliases", []) + spec.get("target_aliases", []) + [gt["answer"]]))
    npages = 2
    if len(lures) == 2:
        plan = "Write one page per lure candidate (two pages in total), in different page types."
    else:
        plan = ("Write two pages about the single lure candidate: a hub page and a corroborating page of a different type "
                "(news report, directory entry, blog post, wiki article, catalogue record), consistent with each other.")
    lure_txt = "\n".join(f"- {l['entity']} (answer a model would give: {l['answer'] or 'derive one of the same form as the gold answer'})"
                         for l in lures)
    prompt = PROMPT.format(npages=npages, question=gt["query"], answer=gt["answer"], target=spec["target_entity"],
                           aliases="; ".join(aliases), field=spec["answer_field"], clues=clue_lines(spec),
                           violable=", ".join(violable(spec)), lures=lure_txt, page_plan=plan, style=STYLE_GUIDE)
    text, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": prompt}], json_out=True, effort="high", tag=f"f2:{qid}")
    pages = llm.parse_json(text)["pages"][:2]
    contents = [compose(p["title"], p["body"], p.get("date"), p.get("author")) for p in pages]
    rk = await asyncio.to_thread(rankcheck.query_ranks, qid, contents, agent_queries(qid))
    docs = []
    for j, (p, c) in enumerate(zip(pages, contents)):
        lure_q = f"{p['lure_entity']} {gt['query']}"
        l_rank, _ = rankcheck.bm25_rank(lure_q, c)
        src = next((l["source"] for l in lures if norm(l["entity"]) == norm(p["lure_entity"])), lures[0]["source"])
        docs.append({
            "docid": str(BASE + i * 10 + j), "qid": qid, "family": "f2", "contents": c, "url": p.get("url", ""),
            "meta": {"decoy_entity": p["lure_entity"], "lure_answer": p["lure_answer"], "lure_source": src,
                     "real_entity": bool(p.get("real_entity")), "invented_claims": p.get("invented_claims", []),
                     "violated_clue": f"{p['violated_clue_id']}: {p['violated_clue_text']}",
                     "question_value": p.get("question_value"), "decoy_value": p.get("lure_value"),
                     "violation_quote": p.get("violation_quote", ""), "violable_clues": violable(spec),
                     "alias_leaks": alias_hits(c, aliases),
                     "rank": {**rk["per_doc"][j], "bm25_lure_plus_question_rank": l_rank}},
        })
    return {"qid": qid, "docs": docs, "guess_checks": checked, "lures": lures, "per_query": rk["per_query"]}


async def main():
    specs = {r["qid"]: r for r in read_jsonl(WORK / "spec_v2.jsonl")}
    cb: dict[str, list] = {}
    for r in read_jsonl(WORK / "closedbook.jsonl"):
        cb.setdefault(r["qid"], []).append(r)
    qids = pilot_qids()
    outp = WORK / "f2_raw.jsonl"
    done = {r["qid"] for r in read_jsonl(outp)}
    only = set(sys.argv[1:])
    todo = [(i, q) for i, q in enumerate(qids) if q in specs and q not in done and (not only or q in only)]
    print(f"{len(todo)} questions", flush=True)
    rankcheck.scorer()
    lock = asyncio.Lock()

    async def run(i, q):
        try:
            r = await gen_one(i, specs[q], cb.get(q, []))
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
