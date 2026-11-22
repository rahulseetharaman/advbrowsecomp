# AdvBrowseComp

An adversarial extension of [BrowseComp-Plus](https://github.com/texttron/BrowseComp-Plus). It
generates fake web pages that trigger the failure modes found in an error analysis of deep-research
agents, adds them to the BrowseComp-Plus corpus, and measures how much they hurt a search agent.

Pilot results are in [RESULTS.md](RESULTS.md): on 99 questions, decoy and memory-lure pages cut
gpt-5.4-mini's accuracy from 43% to 26% and 24%.

> **Keep this repository private.** `data/work/spec_v2.jsonl`, `data/attacks/*/validation.jsonl`,
> `results/per_question.jsonl` and the judge outputs contain BrowseComp-Plus gold answers, which the
> benchmark distributes encrypted. The attack pages are fabricated text, and some F2 pages make invented
> claims about real entities.

## Attack families

| Family | Page | Targets |
|---|---|---|
| F1 decoy | A made-up entity matching every clue but one, which it fails in plain text | Committing to a partial match without checking every clue |
| F2 memory lure | Seems to confirm a model's wrong closed-book answer, while stating one fact that rules it out | Anchoring on memory |
| F4 flood | Five pages about different entities sharing the question's vocabulary, each failing at least two clues | Search loops that never surface the answer |

The failure modes come from `docs/error_analysis.md` (rubric in `docs/failure_rubric.md`).

## Layout

```
src/advbench/        generation and validation
  stage1_spec.py       clue specs (clues quoted from the question) and closed-book guesses
  gen_queries.py       agent-style search queries per question, used for rank checks
  gen_f1.py gen_f2.py gen_f4.py   page generators, with BM25 rank checks and one repair round
  fix_contrast.py      minimal-edit pass that removes "X, not Y" contrasts
  gate.py              validity gate (blind oracle + informed checker + alias-leak check)
  realism_probe.py     can a model tell a page from a real crawled page?
  bm25score.py rankcheck.py   score unindexed pages against the BrowseComp-Plus index
scripts/             experiment
  generate.sh          run the whole generation pipeline
  build_indexes.sh     corpus + one family's pages -> indexes/bm25_<family>
  run_arm.sh           run the agent on one arm, with a spending cap
  judge.sh             grade all arms with the BrowseComp-Plus judge
  analyze.py           flips, lure adoption, exposure, gold visibility
data/
  pilot/               question set (pilot100; pilot99 drops question 49, whose gold label is broken)
  work/                specs, agent queries, closed-book guesses, realism-probe outputs
  attacks/<family>/    gated pages (docs.jsonl), per-question validation records, DONE summary
results/             pilot outputs (see RESULTS.md)
docs/                error analysis that motivated the attacks
```

## Setup

1. Clone and set up [BrowseComp-Plus](https://github.com/texttron/BrowseComp-Plus) next to this repo:
   decrypt the dataset to `data/browsecomp_plus_decrypted.jsonl` and download `indexes/bm25`. Its
   Python environment needs `pyserini` and Java 21.
2. Install this repo's extra requirements into that environment: `pip install -r requirements.txt`.
3. Export your keys, or put them in a `.env` at this repo's root:
   ```
   OPENAI_API_KEY=...
   OPENROUTER_API_KEY=...   # only for Qwen closed-book guesses
   ```
4. If BrowseComp-Plus is not at `../BrowseComp-Plus`, set `BCP_ROOT`. Set `PY` if its Python is not
   `$BCP_ROOT/.venv/bin/python`.

## Reproduce

```bash
bash scripts/generate.sh          # specs, queries, guesses, then F1/F2/F4: generate, fix, gate, probe
bash scripts/build_indexes.sh     # three attacked indexes (~5 min each)
for a in clean f1 f2 f4; do bash scripts/run_arm.sh $a 120 & done; wait
bash scripts/judge.sh
python scripts/analyze.py
```

To re-analyze the pilot without new API calls, unpack the transcripts with
`tar -xzf results/agent_runs.tar.gz -C results`, re-run `scripts/judge.sh`, then run `analyze.py`.

## Cost

Generation and validation call `ADV_MODEL` (default `gpt-5.4-mini`; the pilot used gpt-5.5), with
reasoning effort capped at medium (`ADV_MAX_EFFORT`). The agent runs cost about $0.28 per run with
gpt-5.4-mini and the 25-turn cap; without the cap, runs cost about $3.40 each because the agent keeps
searching. `run_arm.sh` stops when total spend passes its budget argument.
