# Findings

Key findings from the AdvBrowseComp pilot (22 November 2026). Setup, tables and limits are in
[RESULTS.md](RESULTS.md).

## Headline

Fake web pages built to trigger known agent failure modes cut a BrowseComp-Plus search agent's accuracy
from 43% to 24% on 99 questions (gpt-5.4-mini, BM25, 25-turn cap). In most of the extra failures the
agent answered with the fake page's answer.

| Attack | Accuracy (of 99) | Questions lost (of 43 solved clean) | Lost by giving the fake answer |
|---|--:|--:|--:|
| None (clean) | 43 | — | — |
| F1 decoy | 26 | 23 | 17 |
| F2 memory lure | 24 | 25 | 19 |
| F4 flood | 36 | 16 | 7 |

## About the agent

1. **It doesn't check every clue.** Every decoy states, in plain text, the one clue it fails. The agent
   still gave the decoy's answer in 17 of the 23 questions F1 cost it. This is the
   `anchor_opening` / `clue_relaxed` / `premature_commit` pattern from the error analysis, now
   reproducible on demand.
2. **Confirmation of a memory guess is the strongest attack.** F2 pages back a wrong answer that
   gpt-5.5 or Qwen3.8 gives from memory. They cost 25 questions, even though the strongest lures had
   already been removed for fooling gpt-5.5 during validation (on 20 questions it picked the lure while
   holding the gold pages).
3. **Floods cost turns, not visibility.** Under F4, gold pages were shown as often as on the clean
   corpus (60 questions each). The agent spent its turns on look-alike pages instead, and 9 of 16 losses
   ran out of turns.
4. **It didn't notice the pages were fake.** It saw an injected page on most attacked questions and
   opened one on 44 questions for F1 and F2 alike, with no sign of suspicion in its answers.

## About the attack pages

5. **They are easy to detect when a model is asked.** Judged one page at a time, gpt-5.5 called 60 of 60
   F1 and 150 of 150 F4 pages AI-written, against 1 of 60 and 2 of 150 real pages that rank for the same
   questions. Its reasons: entities that don't seem to exist, and polished, overly dense detail. An agent
   prompted to watch for fabrication might resist these attacks. Harder-to-detect generation is the main
   open problem.
6. **Realism and retrievability pull against each other.** Spreading clues thinly across pages made them
   read more naturally, but they dropped out of search results, and detection did not improve.
7. **Clue lists must come from the question text only.** An early spec mixed in facts only the gold pages
   contain, which would have let decoys "fail" clues the question never states and created a second valid
   answer. Specs now quote each clue verbatim from the question.
8. **Generated pages contrast with the question.** They write "in 1999, not in the twenty-first century"
   or "PEGI 18, not a lower one", often naming the question's own value. These had to be rewritten.
9. **Answerless pages read as artificial.** Pages that are on topic but carry no answer and no entity
   were rejected as artificial 80% of the time. Pages about clearly non-matching entities replaced them.

## Practical notes

- Without a turn cap, gpt-5.4-mini kept searching (up to 178 searches) and cost about $3.40 per run.
  With a 25-turn cap it cost about $0.28.
- Question 49's gold answer in the decrypted data file is "Yes" for a "name the band" question, so it
  was dropped.

## Next steps

- Repeat the clean run to measure run-to-run noise. "Gained" questions (6–9 per attack) suggest noise of
  that size.
- Run a stronger agent (gpt-5.5, Qwen3.8) to compare with the error analysis setups.
- Test whether a system prompt warning about fabricated pages removes the effect.
- Generate harder-to-detect pages, for example by editing real corpus pages instead of writing from
  scratch.
