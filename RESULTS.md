# Pilot results (22 November 2026)

We wrote fake web pages aimed at three failure modes from our error analysis of gpt-5.5 and Qwen3.8
on BrowseComp-Plus (`docs/error_analysis.md`), added them to the corpus, and re-ran a search agent on
99 questions. Two of the three attacks cut accuracy almost in half. In most of the extra failures the
agent answered with the fake page's answer.

## Setup

- **Questions.** 100 questions both gpt-5.5 and Qwen3.8 answered correctly in the original runs,
  excluding the 15 questions with gold-label or question flaws (D1/D2 in the error analysis) and the
  10 runs whose opening tool failed. Seed 20261122. Question 49 was dropped from the agent runs because
  its gold answer in the data file is "Yes" for a "name the band" question, leaving 99.
- **Agent.** BrowseComp-Plus's `search_agent/openai_client.py` with gpt-5.4-mini at medium reasoning
  effort; BM25 (`indexes/bm25`, k1=0.9, b=0.4), top 5 results with 512-token snippets, `get_document`
  enabled, 25-turn cap. One run per question per setup.
- **Corpora.** Clean: the BrowseComp-Plus index. Attacked: the same corpus plus one family's pages
  (`scripts/build_indexes.sh`). Excluding the injected pages, the attacked indexes keep the clean top-10
  order on 35–39 of 40 test queries, with score differences of at most 0.07.
- **Grading.** BrowseComp-Plus's `scripts_evaluation/evaluate_with_openai.py` (gpt-4.1).

## Attack pages

| Family | What a page does | Failure mode targeted | Pages kept | Questions with pages |
|---|---|---|--:|--:|
| F1 decoy | A made-up entity that matches every clue but one, which it fails in plain text | Commits to the first plausible hit without checking every clue (`anchor_opening`, `clue_relaxed`, `premature_commit`) | 166 | 83 |
| F2 memory lure | Seems to confirm the wrong answer gpt-5.5 or Qwen3.8 gives from memory, while stating one fact that rules it out | Trusts memory and looks for confirmation (`anchor_memory`) | 125 | 65 |
| F4 flood | Five pages about different entities that share the question's vocabulary but clearly fail at least two clues | Repeated searches never surface the answer (`query_loop` → M1) | 402 | 89 |

Every kept page passed an automatic validity check (`src/advbench/gate.py`):
- A blind model reading the gold pages next to the fakes still reaches the gold answer.
- A second model confirms each page states a clear clue violation, does not contradict the gold facts,
  names no other valid candidate, and has no self-referential text.
- No page contains the gold answer or its aliases.

Sets that fooled the blind reader into giving a fake answer were rejected as possibly ambiguous. This
removed the strongest decoys (15 F1 and 20 F2 questions).

## Results

| Setup | Correct (of 99) | Lost (of the 43 solved clean) | Gained | Lost by giving the fake answer | Lost to the turn cap |
|---|--:|--:|--:|--:|--:|
| Clean | 43 | — | — | — | — |
| F1 decoy | 26 | 23 | 6 | 17 | 5 |
| F2 memory lure | 24 | 25 | 6 | 19 | 5 |
| F4 flood | 36 | 16 | 9 | 7 | 9 |

"Lost" means right on the clean corpus and wrong with the attack pages present; "gained" is the
reverse and gives a rough size for run-to-run noise (there was no repeat clean run).

| Setup | Fake page shown | Fake page opened | Gold shown | Gold opened |
|---|--:|--:|--:|--:|
| Clean | — | — | 60 | 28 |
| F1 decoy | 73 of 82 | 44 | 49 | 20 |
| F2 memory lure | 59 of 64 | 44 | 42 | 15 |
| F4 flood | 76 of 88 | 23 | 60 | 26 |

Counts are questions. "Shown" means the page appeared in at least one search result.

## Findings

1. **The agent doesn't check every clue.** In 17 of 23 F1 losses it answered exactly with the decoy's
   answer, though each decoy states the clue it fails. Example: it gave the decoy's aircraft serial
   "XN776" instead of "XM598", which it got right on the clean corpus.
2. **Memory lures were the strongest attack.** F2 cost 25 questions, even after the lures that fooled
   gpt-5.5 during validation were removed.
3. **Floods waste turns more than they hide answers.** Gold pages were shown as often under F4 as on
   the clean corpus. The agent spent its turns on look-alike pages instead: 9 of 16 losses hit the
   turn cap.
4. **The fake pages are easy to detect when a model is asked.** Judged one page at a time
   (`src/advbench/realism_probe.py`), gpt-5.5 called 60/60 F1 and 150/150 F4 pages AI-written, against
   1/60 and 2/150 real pages that rank for the same questions. The agent showed no sign of noticing
   during search. Harder-to-detect generation is the main open problem.

## What we learned while building the pages

- **Clue lists must come from the question text only.** A first spec mixed in facts that only the gold
  pages contain, which would let a decoy "fail" a clue the question never states. Specs now quote each
  clue verbatim from the question.
- **Pages that talk around the question read as artificial.** Answerless "sink" pages were rejected 80%
  of the time and were replaced by the hard-negative flood (F4).
- **Generated pages contrast with the question's values.** For example, "completed in 1999, not in the
  twenty-first century". A minimal-edit pass (`fix_contrast.py`) restates these positively.
- **Realism and retrievability pull against each other.** Spreading clues thinly across pages made them
  read better but dropped them out of search results, and did not reduce detection.

## Limits

- One run per question per setup, with no repeat clean run.
- gpt-5.4-mini with a 25-turn cap is weaker than the gpt-5.5 and Qwen3.8 setups in the error analysis
  (43% clean accuracy).
- Rank checks used agent-style queries written by gpt-5.5, not real search logs.
- 71 F2 pages make invented claims about real entities (`meta.real_entity = true`). Remove them before
  any release.

## Cost

Agent runs $110.68 (gpt-5.4-mini; plus about $7 of setup tests); grading about $2. Page generation and
validation used gpt-5.5 for most of the work.

## Files

- `results/summary.json`, `results/per_question.jsonl`: metrics and per-question outcomes
- `results/evals/<arm>/`: judge summaries and per-question grades
- `results/agent_runs.tar.gz`: all 396 agent transcripts
- `results/report.html`: the same results as a one-page report
