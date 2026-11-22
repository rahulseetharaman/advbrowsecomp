"""Stage 1: per-question clue spec (gpt-5.5) and closed-book guesses (gpt-5.5, qwen3.8-27b).

Writes work/spec.jsonl and work/closedbook.jsonl. Re-running skips qids already done.
"""
from __future__ import annotations
import asyncio, json, sys
import llm
from common import WORK, pilot_qids, ground_truth, read_jsonl, gold_excerpt

SPEC_PROMPT = """You are preparing a research benchmark on retrieval robustness. Analyse one BrowseComp-Plus question.

QUESTION:
{question}

GOLD ANSWER: {answer}

GOLD DOCUMENTS (excerpts):
{golds}

Return JSON with these keys:
- "target_entity": the entity the clues describe (the answer may be this entity or a property of it).
- "target_type": a short type, e.g. "university", "footballer", "novel", "blog post".
- "answer_field": what the question asks for, e.g. "name of the institution", "number of months mourned".
- "answer_aliases": every surface form a grader should accept for the gold answer (spellings, short forms, with/without titles, numerals vs words). Include the gold answer itself.
- "target_aliases": surface forms of the target entity's name (may equal answer_aliases).
- "clues": list of atomic clues STATED IN THE QUESTION TEXT ONLY. Do not add facts that come only from the gold documents or the notes; those go in gold_fact. Each clue: {{"id": "C1", "question_span": the exact words of the question that state this clue (verbatim, contiguous, copied character for character), "text": the clue in your words without adding anything the question does not say, "gold_fact": what the gold documents say that satisfies it (quote briefly), "checkable_detail": the value or range the QUESTION gives that makes the clue checkable (a date, range, number, weekday, place, name) or "", "kind": one of "date","number","place","name","category","event","relation","other"}}. The final ask ("what is X") is not a clue.
- "bridge_entities": entities on the path to the target that are not the target (people, organisations, works).
- "domain": the real-world domain and setting (country, era, field) in one sentence.
- "doc_styles": the kinds of web pages the gold documents are (e.g. "Yemen Times news article", "university Wikipedia page").
Return only JSON."""

CB_PROMPT = """Answer the following question from your own knowledge only. You cannot search. Even if unsure, commit to your single best guess.

{question}

Return JSON: {{"entity": the entity you believe the clues describe, "answer": your final answer to what is asked, "confidence": 0-100}}"""


def golds_block(gt: dict) -> str:
    parts = []
    for g in gt["gold_docs"][:4]:
        parts.append(f"--- docid {g['docid']} ---\n" + gold_excerpt(g["text"], gt["answer"]))
    return "\n\n".join(parts)


async def spec_one(qid: str) -> dict:
    gt = ground_truth()[qid]
    prompt = SPEC_PROMPT.format(question=gt["query"], answer=gt["answer"], golds=golds_block(gt))
    text, _ = await llm.chat("gpt55", [{"role": "user", "content": prompt}], json_out=True, effort="medium",
                             tag=f"spec:{qid}")
    d = llm.parse_json(text)
    d["qid"] = qid
    d["question"] = gt["query"]
    d["gold_answer"] = gt["answer"]
    d["gold_docids"] = [g["docid"] for g in gt["gold_docs"]]
    return d


async def cb_one(qid: str, model: str) -> dict:
    gt = ground_truth()[qid]
    msgs = [{"role": "user", "content": CB_PROMPT.format(question=gt["query"])}]
    text, _ = await llm.chat(model, msgs, json_out=True, effort="medium" if model == "gpt55" else "low",
                             max_tokens=None if model == "gpt55" else 32000, tag=f"cb:{model}:{qid}", retries=3)
    d = llm.parse_json(text)
    return {"qid": qid, "model": model, **d}


async def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    qids = pilot_qids()
    spec_p, cb_p = WORK / "spec_v2.jsonl", WORK / "closedbook.jsonl"
    done_spec = {r["qid"] for r in read_jsonl(spec_p)}
    done_cb = {(r["qid"], r["model"]) for r in read_jsonl(cb_p)}
    lock = asyncio.Lock()
    nerr = 0

    async def run(kind, q, coro, path):
        nonlocal nerr
        try:
            r = await coro
        except Exception as e:  # noqa: BLE001
            nerr += 1
            print(f"ERR {kind} {q}: {e}", file=sys.stderr, flush=True)
            return
        async with lock:
            with path.open("a") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    jobs = []
    for q in qids:
        if which in ("all", "spec") and q not in done_spec:
            jobs.append(run("spec", q, spec_one(q), spec_p))
        for m in (sys.argv[2].split(",") if len(sys.argv) > 2 else ("gpt55", "qwen")):
            if which in ("all", "cb") and (q, m) not in done_cb:
                jobs.append(run("cb", q, cb_one(q, m), cb_p))
    print(f"{len(jobs)} jobs", flush=True)
    await llm.gather_limited(jobs, 40)
    print(f"done, errors={nerr}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
