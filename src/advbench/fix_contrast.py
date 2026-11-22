"""Minimal-edit pass: restate facts that are contrasted with unstated alternatives.

Generated pages sometimes write "completed in 1999, not in the twenty-first century" or "posted on
October 6, not on October 5": a real page has no reason to mention the alternative, and the
alternative is often the question's own value, which gives the decoy away. This pass rewrites only
such sentences, keeping every fact, the violated-clue value and the lure answer.
Usage: python fix_contrast.py f1|f2   (edits work/<family>_raw.jsonl in place, keeps a .bak)
"""
from __future__ import annotations
import asyncio, json, re, shutil, sys
import llm
from common import WORK, read_jsonl, write_jsonl

PROMPT = """Edit a web page minimally. Find every sentence that contrasts or negates a fact against an alternative the page has no reason to mention (for example "completed in 1999, not in the twenty-first century", "posted on October 6, not October 5", "rated PEGI 18, not a lower one", "in 2014 rather than the mid-2000s", "unlike ..."), and rewrite it to state the fact positively. Also remove any mention of these strings if present: {avoid}.
Keep every other sentence exactly as it is, and keep every fact. Keep the front matter block at the top unchanged. The fact "{keep_short}" must stay stated in the page.

Return JSON: {{"changed": bool, "contents": the full edited page (only the page text between the markers, without the markers), "violation_quote": the sentence of the edited page that states "{keep_short}"}}

<<<PAGE
{contents}
PAGE>>>"""


TAIL = re.compile(r"\n\s*(?:Return JSON:|PAGE>>>|<<<PAGE).*$", re.S)


def strip_tail(text: str) -> str:
    """Drop any echoed prompt text (e.g. a trailing 'Return JSON: ...' line) from an edited page."""
    return TAIL.sub("", text).rstrip() + "\n"


async def fix(d: dict, avoid: list[str]) -> dict:
    m = d["meta"]
    keep = m.get("violation_quote", "")
    text, _ = await llm.chat(llm.GEN_MODEL, [{"role": "user", "content": PROMPT.format(  # noqa
        avoid="; ".join(avoid) or "(none)", keep_short=(m.get("decoy_value") or keep)[:200],
        contents=d["contents"])}], json_out=True, effort="low", tag=f"fix:{d['docid']}")
    out = llm.parse_json(text)
    if out.get("contents"):
        out["contents"] = strip_tail(out["contents"])
    if out.get("changed") and out.get("contents", "").startswith("---"):
        d = {**d, "contents": out["contents"].rstrip() + "\n",
             "meta": {**m, "violation_quote": out.get("violation_quote") or keep, "contrast_fixed": True}}
    else:
        d = {**d, "meta": {**m, "contrast_fixed": False}}
    return d


async def main():
    fam = sys.argv[1]
    p = WORK / f"{fam}_raw.jsonl"
    if not p.with_suffix(".jsonl.bak").exists():
        shutil.copy(p, p.with_suffix(".jsonl.bak"))
    rows = read_jsonl(p)
    specs = {r["qid"]: r for r in read_jsonl(WORK / "spec_v2.jsonl")}
    jobs, where = [], []
    for ri, r in enumerate(rows):
        sp = specs[r["qid"]]
        avoid = list(dict.fromkeys(sp.get("answer_aliases", []) + sp.get("target_aliases", [])))
        for di, d in enumerate(r["docs"]):
            if "contrast_fixed" in d["meta"]:
                continue
            jobs.append(fix(d, avoid))
            where.append((ri, di))
    res = await llm.gather_limited(jobs, 32)
    nchg = nerr = 0
    for (ri, di), d in zip(where, res):
        if isinstance(d, Exception):
            nerr += 1
            continue
        rows[ri]["docs"][di] = d
        nchg += int(d["meta"].get("contrast_fixed", False))
    write_jsonl(p, rows)
    print(f"{fam}: {len(jobs)} docs, {nchg} edited, {nerr} errors (unchanged)")


if __name__ == "__main__":
    asyncio.run(main())
