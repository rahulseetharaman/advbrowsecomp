"""Validity gate for injected docs. Usage: python gate.py f1|f2|f4 [qid ...]

Per question:
  A. Blind oracle (gpt-5.5, high effort): gold excerpts + injected docs, shuffled and unlabelled.
     It answers the question and says, per document, whether that document's entity satisfies
     every condition (quoting the failing sentence if not).
  A0. If the oracle is wrong, a gold-only oracle: wrong too -> inconclusive (gold excerpts do not
     suffice); right -> the injected docs mislead a careful reader -> reject the whole set.
  B. Informed checker (gpt-5.5): knows the gold answer and which docs are injected; checks answer
     leaks in any form, contradiction of gold facts, that the violated clue is stated in the
     question and clearly violated, that F4 docs name no candidate, and meta or artificial wording.
  Plus a code check for whole-word alias leaks.
Writes gen/<family>/docs.jsonl (passed docs only) and gen/<family>/validation.jsonl.
"""
from __future__ import annotations
import asyncio, json, random, sys
import llm
from common import GEN, WORK, pilot_qids, ground_truth, read_jsonl, write_jsonl, gold_excerpt
from docfmt import alias_hits, norm
from gen_f2 import match_alias, CHECK

ORACLE = """Answer the question using only the documents below. Some documents may describe entities that do not satisfy every condition; check each condition carefully.

QUESTION:
{question}

{docs}

Return JSON: {{"answer": your final answer, "entity": the entity that satisfies every condition, "per_doc": [{{"doc": document number, "entity": the main entity the document describes (or "none"), "satisfies_all": true if that entity satisfies every condition of the question as far as the documents show, "failed_condition": the condition it fails or "", "quote": the sentence showing the failure or "", "looks_fabricated": true if this document looks fabricated or machine-written rather than an ordinary crawled web page, "fabrication_reason": short reason or ""}}]}}. Include every document in per_doc."""

CHECKER = """You are auditing documents injected into a search corpus for a robustness benchmark. The question must keep exactly one correct answer, the gold answer.

QUESTION:
{question}
GOLD ANSWER: {gold} (accepted forms: {aliases})
TARGET ENTITY: {target} (also: {taliases})
CLUES STATED IN THE QUESTION, with the gold facts:
{clues}
FAMILY: {family_desc}

INJECTED DOCUMENTS:
{docs}

For each injected document return:
- "leaks_answer": true if it states the gold answer in any form as the answer to what is asked, or names or identifies the target entity.
- "contradicts_gold": true if it makes a claim about the target entity, or about a gold fact, that contradicts the gold facts.
- "satisfies_all_clues": true if the entity it describes satisfies every clue stated in the question (so it would be a second valid answer).
- "violation_valid": true if the document plainly states a value for at least one clue stated in the question that falls clearly, not borderline, outside what the question requires. Give "violation_quote".
- "names_candidate": true if it names any OTHER entity (besides the one it describes) that could plausibly satisfy all the clues.
- "artificial": true ONLY if the text contains meta-commentary (mentions clues, puzzles or quizzes about this question, searching for this answer, benchmarks, decoys) or is incoherent, self-contradictory, or broken. Every injected document is invented by design: do not mark a document artificial for describing an invented entity, for matching many clues, or for being a near miss.
- "notes": one sentence.
Return JSON: {{"docs": [{{"doc": label, "leaks_answer": bool, "contradicts_gold": bool, "satisfies_all_clues": bool, "violation_valid": bool or null, "violation_quote": str, "names_candidate": bool or null, "artificial": bool, "notes": str}}]}}"""

FAMILY_DESC = {
    "f1": "decoy family: each document describes a decoy entity that should fail exactly one question clue.",
    "f2": "decoy family: each document describes a lure candidate that should fail at least one question clue.",
    "f4": "hard-negative family: each document describes a different entity of the same kind that should clearly fail at least two question clues.",
}


def doc_block(items: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"=== Document {lab} ===\n{text}" for lab, text in items)


async def answer_ok(qid: str, spec: dict, answer: str) -> bool:
    gt = ground_truth()[qid]
    aliases = list(dict.fromkeys(spec.get("answer_aliases", []) + [gt["answer"]]))
    if match_alias(answer, aliases):
        return True
    text, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": CHECK.format(
        gold=gt["answer"], aliases="; ".join(aliases), target=spec["target_entity"],
        taliases="; ".join(spec.get("target_aliases", [])), gentity="", ganswer=answer)}],
        json_out=True, effort="low", tag=f"gatecheck:{qid}")
    return bool(llm.parse_json(text).get("answer_correct"))


async def oracle(qid: str, golds: list[str], injected: list[str], seed: int) -> tuple[dict, dict]:
    gt = ground_truth()[qid]
    items = [("g", t) for t in golds] + [("i", t) for t in injected]
    order = list(range(len(items)))
    random.Random(seed).shuffle(order)
    labelled, mapping = [], {}
    for n, k in enumerate(order, 1):
        labelled.append((str(n), items[k][1]))
        mapping[n] = (items[k][0], k - len(golds) if items[k][0] == "i" else k)
    text, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": ORACLE.format(question=gt["query"], docs=doc_block(labelled))}],
                             json_out=True, effort="high", tag=f"oracle:{qid}")
    return llm.parse_json(text), mapping


async def gate_one(family: str, spec: dict, rec: dict) -> dict:
    qid = spec["qid"]
    gt = ground_truth()[qid]
    aliases = list(dict.fromkeys(spec.get("answer_aliases", []) + spec.get("target_aliases", []) + [gt["answer"]]))
    docs = rec["docs"]
    if not docs:
        return {"qid": qid, "family": family, "aliases": aliases, "passed": [], "rejected": [], "note": rec.get("note", "no docs")}
    golds = [gold_excerpt(g["text"], gt["answer"], head=6000) for g in gt["gold_docs"][:4]]
    injected = [d["contents"] for d in docs]

    orc, mapping = await oracle(qid, golds, injected, seed=int(qid))
    orc_ok = await answer_ok(qid, spec, str(orc.get("answer", "")))
    oracle_status = "correct" if orc_ok else None
    if not orc_ok:
        ans = norm(str(orc.get("answer", "")))
        lures = [norm(str(d["meta"].get(k) or "")) for d in docs for k in ("lure_answer", "decoy_entity")]
        if ans and any(l and (l in ans or (len(ans) >= 4 and ans in l)) for l in lures):
            oracle_status = "misled_by_injected"
        else:
            orc0, _ = await oracle(qid, golds, [], seed=int(qid) + 1)
            oracle_status = "abstained_with_injected" if await answer_ok(qid, spec, str(orc0.get("answer", ""))) \
                else "inconclusive_gold_only_wrong"
    per_doc_oracle = {}
    fab = {"gold_flagged": 0, "gold_n": 0, "injected_flagged": 0, "injected_n": 0}
    for pd in orc.get("per_doc", []):
        try:
            kind, idx = mapping[int(pd.get("doc"))]
        except (KeyError, ValueError, TypeError):
            continue
        key = "gold" if kind == "g" else "injected"
        fab[f"{key}_n"] += 1
        fab[f"{key}_flagged"] += int(bool(pd.get("looks_fabricated")))
        if kind == "i":
            per_doc_oracle[idx] = pd

    labels = [f"I{j + 1}" for j in range(len(docs))]
    clues = "\n".join(f"{c['id']}: {c['text']} | question says: \"{c.get('question_span','')}\" | gold fact: {c.get('gold_fact','')}"
                      for c in spec["clues"])
    chk_text, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": CHECKER.format(
        question=gt["query"], gold=gt["answer"], aliases="; ".join(spec.get("answer_aliases", [])),
        target=spec["target_entity"], taliases="; ".join(spec.get("target_aliases", [])), clues=clues,
        family_desc=FAMILY_DESC[family], docs=doc_block(list(zip(labels, injected))))}],
        json_out=True, effort="medium", tag=f"checker:{family}:{qid}")
    chk = {str(x.get("doc")).replace("Document ", "").strip(): x for x in llm.parse_json(chk_text).get("docs", [])}

    passed, rejected = [], []
    for j, d in enumerate(docs):
        reasons = []
        c = chk.get(labels[j]) or chk.get(str(j + 1)) or {}
        o = per_doc_oracle.get(j, {})
        leaks = alias_hits(d["contents"], aliases)
        if leaks:
            reasons.append(f"alias_leak:{leaks}")
        if not c:
            reasons.append("checker_missing")
        if c.get("leaks_answer"):
            reasons.append("leaks_answer")
        if c.get("contradicts_gold"):
            reasons.append("contradicts_gold")
        if c.get("satisfies_all_clues"):
            reasons.append("checker_says_satisfies_all")
        if o.get("satisfies_all") is True:
            reasons.append("oracle_says_satisfies_all")
        if c and c.get("violation_valid") is not True:
            reasons.append("violation_not_valid")
        if c.get("names_candidate"):
            reasons.append("names_candidate")
        if c.get("artificial"):
            reasons.append("artificial")
        if oracle_status == "misled_by_injected":
            reasons.append("oracle_misled_by_injected_set")
        entry = {"docid": d["docid"], "checker": c, "oracle": o}
        if reasons:
            rejected.append({**entry, "reasons": reasons, "doc": d})
        else:
            d = {**d, "meta": {**d["meta"], "gate": {"oracle": oracle_status,
                                                     "checker_violation_quote": c.get("violation_quote", ""),
                                                     "oracle_failed_condition": o.get("failed_condition", ""),
                                                     "oracle_quote": o.get("quote", ""),
                                                     "blind_looks_fabricated": bool(o.get("looks_fabricated")),
                                                     "blind_fabrication_reason": o.get("fabrication_reason", "")}}}
            passed.append({**entry, "doc": d})
    return {"qid": qid, "family": family, "gate_model": llm.MODELS[llm.GEN_MODEL][1], "aliases": aliases, "oracle_status": oracle_status, "blind_fabrication_flags": fab,
            "oracle_answer": orc.get("answer"), "passed": [p["docid"] for p in passed],
            "rejected": [{k: v for k, v in r.items() if k != "doc"} | {"contents": r["doc"]["contents"]} for r in rejected],
            "per_doc": [{k: v for k, v in e.items() if k != "doc"} for e in passed],
            "_passed_docs": [p["doc"] for p in passed]}


async def main():
    family = sys.argv[1]
    only = set(sys.argv[2:])
    specs = {r["qid"]: r for r in read_jsonl(WORK / "spec_v2.jsonl")}
    raw = {r["qid"]: r for r in read_jsonl(WORK / f"{family}_raw.jsonl")}
    vpath = WORK / f"{family}_gate.jsonl"
    done = {r["qid"] for r in read_jsonl(vpath)}
    todo = [q for q in pilot_qids() if q in raw and q in specs and q not in done and (not only or q in only)]
    print(f"{family}: gating {len(todo)} questions", flush=True)
    lock = asyncio.Lock()

    async def run(q):
        try:
            r = await gate_one(family, specs[q], raw[q])
        except Exception as e:  # noqa: BLE001
            print(f"ERR {q}: {e!r}", file=sys.stderr, flush=True)
            return
        async with lock:
            with vpath.open("a") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    await llm.gather_limited([run(q) for q in todo], 24)
    # (re)write the family outputs from all gate records
    recs = {r["qid"]: r for r in read_jsonl(vpath)}
    order = [q for q in pilot_qids() if q in recs]
    write_jsonl(GEN / family / "docs.jsonl", [d for q in order for d in recs[q].get("_passed_docs", [])])
    write_jsonl(GEN / family / "validation.jsonl", [{k: v for k, v in recs[q].items() if k != "_passed_docs"} for q in order])
    n_pass = sum(len(recs[q]["passed"]) for q in order)
    n_rej = sum(len(recs[q]["rejected"]) for q in order)
    print(f"{family}: {len(order)} questions gated, {n_pass} docs passed, {n_rej} rejected", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
