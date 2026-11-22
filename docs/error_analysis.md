# Error analysis: gpt-5.5 and Qwen3.8-27B on BrowseComp-Plus

Every wrong answer in two full 830-query runs was read and assigned one cause with a written
rubric. 250 failures were labelled twice by independent reviewers and settled against the
transcripts. This document covers how the review was done, what each kind of error looks like, the
full per-case lists, and the scaffold defects found along the way.

## The two runs

| | gpt-5.5 | Qwen3.8-27B |
|---|---|---|
| Agent | gpt-5.5 (OpenAI) | Qwen3.8-27B, served with vLLM |
| Opening (first move) | clue decomposition, BM25 pool, Cohere rerank-4-pro; computed live, top 10 | Qwen3-4B rerank of the top 500, Qwen3.8-27B picks 10; precomputed |
| Time budget / steer to answer | 900 s / 630 s | 2700 s / 1890 s |
| Correct | 751 / 830 (90.5%) | 659 / 830 (79.4%) |
| Failures | 79 | 171 |
| Run directory | `runs/pi_bm25_browsecomp-plus_qfull_qg_dx_gpt-4o_openai_gpt-55_breadth10_norule_s32_t900_live_coherepro` | `runs/pi_bm25_browsecomp-plus_qfull{A,B}_qg_dx_gpt-4o_vllm_Qwen_Qwen38-27B_agent_qwen38_qfull{A,B}_beD_k10` |

Both runs are judged by the same judge (gpt-5.3-codex) against the BrowseComp-Plus gold answers.

## The short version

- **Most failures are the model's: 52 of 79 for gpt-5.5 (66%) and 143 of 171 for Qwen3.8 (84%).**
  Most of those never had a document with the answer in front of them (M1: 32 and 91).
- **A quarter of gpt-5.5's failures are the benchmark's, not the model's.** Gold labels that are
  wrong, questions with more than one valid answer, and judge errors account for 19 failures in
  each run. Counting judge errors as correct and setting aside the undecidable questions gives
  92.7% for gpt-5.5 and 81.4% for Qwen3.8.
- **Two scaffold defects decided 8 gpt-5.5 failures and 6 Qwen3.8 failures.** Both are fixed. A
  third defect found while fixing them touched many runs but decided no failure.
- **The time limit decided 3 Qwen3.8 failures and no gpt-5.5 failure.** Qwen3.8 was steered in 106
  of its 143 model failures, but in all but those 3 it was already on a wrong path.

## How the review was done

1. **Material.** For each case: the full transcript (every tool call, the agent's `reason`
   argument, every tool output in full), the text of every gold and evidence document, and
   step-level signals computed from the transcript (first step a gold document was shown, opened,
   cited, and so on).
2. **Analyst pass.** One Opus 5.5 analyst read each case through three lenses: the trajectory, the
   evidence, and a skeptic that checks the gold label first. A pilot showed a single analyst matched
   a four-agent council on the same case at about 40% of the cost. Cases the analyst rated low
   confidence went to a council (one case, gpt-5.5 561). The study covered all failures plus long
   correct runs and short clean controls: 156 cases for gpt-5.5 and 240 for Qwen3.8.
3. **Rubric.** The analyst records give rich stories but no single, comparable cause. A written
   rubric (`failure_rubric.md`) assigns exactly one source per failure, in a fixed decision order.
   Its guiding rule: the scaffold and the setup are blamed only for verified defects and limits.
   Anything the model did with a working scaffold is the model's failure. That includes no answer
   line, an answer left inside its reasoning, invented tool calls, loops and slow turns.
4. **Two independent passes.** Two sets of reviewers labelled all 250 failures. Each pass grouped
   the cases differently, and each reviewer went back to the transcript wherever the analyst record
   did not settle a step. The passes agreed on 239 of 250 (95.6%, Cohen's kappa 0.94). In one pass
   some files were written by the wrong agent through a shared scratch folder. A validation script
   caught them, and those cases were redone.
5. **Rubric v2 and final rulings.** The disagreements exposed five gaps in the first rubric:
   - benchmark faults had to be decisive;
   - a failed opening tool had no category;
   - "answer-bearing document" was undefined;
   - the line between a judge error and a wrong-form answer was unclear;
   - gpt-5.5's steer is invisible unless a tool was called after it.

   v2 closes them. 96 cases then got a final ruling from a fresh reviewer working directly from the
   transcript, with quotes: the 11 disagreements, every case a v2 rule could change, and the files
   in doubt. The other 154 keep the label both passes agreed on.
6. **Checks that do not rest on judgment.**
   - Every "the time limit blocked it" claim was tested by re-running the blocked search against the
     BM25 index, to see whether it would have shown the answer on the first page.
   - Every judge-error claim quotes a corpus document that uses the agent's spelling.
   - The `steered` and `empty_read` flags are computed from the transcripts, not taken from
     reviewers.
7. **One ruling per question across runs.** "Gold unreachable" and "more than one valid answer"
   depend on the question and corpus, not on the run. Where the two runs disagreed, one ruling was
   applied to both (624 and 869). Rulings that depend on how a run behaved stay run-specific.
8. **Scaffold claims were verified in code.** Each defect was traced to the line that causes it,
   reproduced against the real index, and fixed. The fixed code was checked against reads replayed
   from the transcripts (see the scaffold section below).

Label confidence: gpt-5.5 has 58 high and 21 medium. Qwen3.8 has 139 high, 31 medium and 1 low
(1201).

## The rubric in one table

The first rule that applies wins. Within M, M0 is checked first, then the furthest stage the run
reached.

| Code | Name | Rule |
|---|---|---|
| D1 | Gold label wrong | Documents show the gold answer does not fit the question, or the gold documents are about something else |
| D2 | Question flawed | Documents show more than one answer fits every clue, or a clue is false for the gold answer, and this decided the outcome |
| D3 | Judge error | The agent's Exact Answer is the gold entity in a spelling or alias a corpus document uses |
| E1 | Empty read | `read_document` returned no body for a document with an over-long line, on a document the agent had correctly targeted |
| E2 | Opening tool failed | The opening `breadth_search` returned an error for a valid call |
| S1 | Time limit cut a viable path | The steer blocked a pending step aimed at the answer, or came after the agent named the right target |
| M0 | No answer | No Exact Answer: a repetition loop, cut-off output, or reasoning with no answer line |
| M1 | Never in view | No document stating the answer or identifying the target was ever shown |
| M2 | In view, not read | Such a document was shown in a preview, but never opened |
| M3 | Read, not used | It was opened, but the agent misread or dropped it and never held the right target |
| M4 | Right entity, wrong answer | The agent held the right target, but answered the wrong field, value or form |

A flaw in the data that did not decide the outcome gets a `data_flaw` flag, and the case is staged
as a model failure.

## Results

| Source | gpt-5.5 (79) | Qwen3.8 (171) |
|---|--:|--:|
| **Benchmark data or grading** | **19** | **19** |
| D1 gold label wrong | 4 | 5 |
| D2 question flawed | 6 | 7 |
| D3 judge error | 9 | 7 |
| **Scaffold defect** | **8** | **6** |
| E1 empty read | 6 | 6 |
| E2 opening tool failed | 2 | 0 |
| **Experiment setup** | **0** | **3** |
| S1 time limit cut a viable path | 0 | 3 |
| **Model failure** | **52** | **143** |
| M0 no answer | 0 | 9 |
| M1 never in view | 32 | 91 |
| M2 in view, not read | 10 | 28 |
| M3 read, not used | 3 | 10 |
| M4 right entity, wrong answer | 7 | 5 |

### gpt-5.5: every failure

| Source | n | Cases |
|---|--:|---|
| D1 gold label wrong | 4 | 794 869 873 930 |
| D2 question flawed | 6 | 221 427 624 754 1021 1094 |
| D3 judge error | 9 | 71 116 219 283 406 688 826 987 1117 |
| E1 empty read | 6 | 86 89 120 420 556 1038 |
| E2 opening tool failed | 2 | 757 1204 |
| S1 time limit cut a viable path | 0 | — |
| M0 no answer | 0 | — |
| M1 never in view | 32 | 26 156 166 183 244 251 276 293 349 362 396 471 490 507 513 525 575 600 666 712 716 732 747 773 844 851 948 1004 1055 1068 1161 1265 |
| M2 in view, not read | 10 | 100 223 342 467 497 734 739 742 775 1131 |
| M3 read, not used | 3 | 486 1036 1222 |
| M4 right entity, wrong answer | 7 | 70 234 521 625 638 1174 1190 |

### Qwen3.8-27B: every failure

| Source | n | Cases |
|---|--:|---|
| D1 gold label wrong | 5 | 561 794 869 873 930 |
| D2 question flawed | 7 | 221 521 624 809 1021 1052 1201 |
| D3 judge error | 7 | 116 283 688 728 826 987 1079 |
| E1 empty read | 6 | 86 89 120 420 556 1038 |
| E2 opening tool failed | 0 | — |
| S1 time limit cut a viable path | 3 | 254 297 672 |
| M0 no answer | 9 | 427 432 610 618 960 981 986 1141 1213 |
| M1 never in view | 91 | 23 25 30 70 79 100 121 122 128 131 156 161 174 180 228 237 244 250 251 264 280 293 294 315 322 349 350 362 371 395 409 442 473 487 490 501 507 513 524 525 527 614 630 633 666 685 709 710 711 712 716 718 719 732 739 747 754 757 775 781 802 844 851 898 905 919 921 927 941 948 961 998 1003 1004 1010 1015 1044 1055 1094 1107 1110 1111 1161 1174 1196 1211 1219 1222 1226 1236 1242 |
| M2 in view, not read | 28 | 3 138 223 233 266 330 438 532 549 587 601 653 671 713 774 800 827 875 916 920 1036 1078 1131 1164 1193 1228 1233 1253 |
| M3 read, not used | 10 | 8 85 153 689 773 969 980 1034 1223 1265 |
| M4 right entity, wrong answer | 5 | 61 71 421 471 942 |

## What each error looks like

### Benchmark data and grading (D)

These are failures the agent could not have avoided, or did not actually make. They count only when
the flaw decided the outcome.

- **D1, gold label wrong (4 and 5).** The gold documents do not support the gold answer.
  - In 869 the question asks the school grade of a specific person's oldest child. All four gold
    documents are generic pages (CDC lead guidance, a Wikipedia article on US education, a table of
    kindergarten entry rules), and none names the person.
  - In 873 the only gold document is a student's fitness assignment. Its BMI of 27 matches the gold
    "27" by coincidence; it has none of the question's clues (birthday, two children, spouse).
  - Four of these are shared by both models. Qwen3.8 adds 561.
- **D2, question flawed (6 and 7).** Two answers fit, or a clue is false for the gold.
  - In 624 the question asks for a share of funding without fixing the year. gpt-5.5 read the 2018
    report (66%); the gold is the 2019 figure (65%).
  - In 221 both of the collector's books fit "a book about a poppy-derived substance". The agent
    picked *Opium: A Portrait of the Heavenly Demon*; the gold is the other one.
- **D3, judge error (9 and 7).** The agent's answer is right, and the judge rejected the form.
  - In 283 the agent answered "Zimri Eder", the spelling in the Wikipedia page it read. The gold
    documents say "Zimri Elder".
  - Five of these are shared by both models: 116 283 688 826 987.

### Scaffold defects (E)

- **E1, empty read (6 in each run, the same six questions).** `read_document` pages by line, and
  the 50 KB output cap keeps only whole lines. A document whose text is one very long line comes
  back as a header with no body. In gpt-5.5 run 86, the agent found the right thesis (doc 39935, a
  single 640 KB line) and opened it twice, getting 29 bytes each time. The answer, a name in the
  acknowledgements, was never shown, and the agent guessed.
- **E2, opening tool failed (2, gpt-5.5 only).** The live opening decomposes the question with
  gpt-5.5. Each request had a 120 s limit and 3 tries. In 10 runs all three tries timed out, and the
  agent got an error instead of an opening. Two of those runs, 757 and 1204, failed. Qwen3.8's
  opening was precomputed, so it never hit this.

### Experiment setup (S)

- **S1, time limit cut a viable path (3, Qwen3.8 only).** In 254 the agent had found the
  university and was about to confirm the band's album; the steer blocked a search whose top hit is
  the gold document. In 297 the agent had identified the actor and director; its two blocked searches
  rank the answer document second and first. In 672 the blocked step was a read of the gold
  document itself. In every other steered failure the agent was already
  on a wrong path, so the steer is a flag there, not the cause.

### Model failures (M)

- **M0, no answer (Qwen3.8 only, 9).** The output has no Exact Answer line. In 432 the model ran
  for 932 s in one turn without a single tool call, reasoned from memory, repeated blocks of text,
  and stopped mid-word in a looping list of town names. Six of the nine never searched at all.
- **M1, never in view (32 and 91).** The largest group in both runs. The agent never saw a document
  that states the answer or identifies the target.
  - Typical shape: in gpt-5.5 run 26 the opening showed only bridge pages (a surname page, the
    Billboard Wikipedia page). The agent searched the owner's surname without paging past rank 5,
    then answered from memory ("Club Bahia", 45% confident).
  - In Qwen3.8 run 23 the agent committed to the film *22 July* from memory at step 3, made up a
    supporting detail at step 5, and spent the rest of the run looking for confirmation of it.
- **M2, in view, not read (10 and 28).** The answer was on screen in a preview, and the agent never
  opened it.
  - In gpt-5.5 run 100 the opening's rank-8 result was the Phoenix New Times Wikipedia page, the
    answer itself. The agent made 12 reads, none of that page.
  - In Qwen3.8 run 138 the gold page was in the opening at rank 10, and again at rank 6 later. The
    agent anchored on the rank-1 result and never opened it.
- **M3, read, not used (3 and 10).** The agent read the answer and did not take it up. In gpt-5.5
  run 486 a list it read names Eder as the scorer of the goal that won Euro 2016. The agent was
  reading the page for something else and never followed up on Eder.
- **M4, right entity, wrong answer (7 and 5).** The agent found the target but answered the wrong
  thing.
  - In gpt-5.5 run 70 it identified the actor and answered his 1982 TV drama. The gold is his
    earlier 1980 debut, in a document it never saw.
  - In Qwen3.8 run 61 it read a catalogue entry that classes the book as poetry, misreported it, and
    answered "a novel" from its own knowledge.

## Why the model failures happen

Drivers are non-exclusive, counted over model failures only.

| Driver | Meaning | gpt-5.5 (52) | Qwen3.8 (143) |
|---|---|--:|--:|
| query_loop | repeated or rephrased the same search without new information | 43 | 104 |
| clue_relaxed | ignored or bent a clue the answer fails | 35 | 105 |
| anchor_memory | committed to a candidate from its own memory, with no document behind it | 27 | 77 |
| premature_commit | answered without checking clues it could have checked | 22 | 33 |
| anchor_opening | committed to an opening hit that matched only some clues | 17 | 93 |
| misread | misread a document | 3 | 28 |
| degenerate_output | repetition loop or cut-off output | 0 | 11 |
| no_search | answered without searching | 0 | 6 |
| malformed_calls | invalid tool calls that cost progress | 0 | 1 |

The pattern is the same in both models: pick a candidate early, bend the clues that do not fit,
and keep searching for confirmation of it. Qwen3.8 does every part of this more often.

The biggest difference is `anchor_opening`: 93 against 17. Qwen3.8's opening contains a gold
document more often than gpt-5.5's (572 against 434 of 830 questions). Yet it more often locks onto
whichever opening hit is ranked first, even when that hit fails some of the question's clues.

## Scaffold defects and their fixes

Three defects were found and fixed. Two of them decided failures (E1, E2). The third was found while
fixing E1 and decided no failure.

| Defect | Cause | Fix | Failures decided |
|---|---|---|---|
| Empty read | Upstream pi-serini code: pages are by line and the 50 KB cap keeps only whole lines, so a line over 50 KB is never shown | The search server splits only lines too large to ever be shown (over ~50 KB); all other lines are unchanged (`jvm/src/main/java/dev/jhy/piserini/Bm25Server.java`) | 6 / 6 |
| Page cut past the cap | Same code: when a 200-line page passes 50 KB, the tail lines are dropped, and the "continue at line 201" hint skips them | A page over the cap ends at the last whole line that fits, and the hint points at the next line (`src/pi-search/tool_handlers.ts`) | 0 / 0 |
| Opening timeout | Each decomposition request was limited to 120 s with 3 tries; gpt-5.5 sometimes needs longer, and in 10 runs all three tries timed out | Per-try limit raised to 600 s, adjustable with `PI_SEARCH_DECOMP_TIMEOUT_MS` (`src/pi-search/constraint_decomp.ts`) | 2 / — |

**The page-cut defect was checked against every failure it touched.** That was 4 gpt-5.5 failures
(600 794 1117 1222) and 11 Qwen3.8 failures (85 131 153 264 294 395 490 501 556 960 1004). In none
of them did the lost lines contain the answer. The only answer words in them were coincidences,
such as "William Allen" where the answer is Walter Allen. In Qwen3.8 run 85 the agent read 26 of
the 28 lost lines later anyway.

**The opening timeout also cost 46 gpt-5.5 runs two to four minutes** before a retry succeeded. The
agent does not see the clock, so this only matters for runs that reached the steer. There are four:
8 (correct), and 362, 497 and 747 (model failures already on a wrong path when steered).

**The fixes change nothing for runs that never hit a defect.** 400 reads replayed from the gpt-5.5
transcripts give 399 byte-identical outputs. The one difference is a document with an over-long
line, whose later lines are renumbered. Documents 39935, 46080 and 85088 now page from first to
last line with no gaps and no page over the cap.

**Runs to re-run.** These are the runs whose tool outputs or time budget change under the fixes,
taken regardless of outcome. Re-running only the failures would inflate accuracy.

| | gpt-5.5 | Qwen3.8 |
|---|--:|--:|
| Runs with an empty read | 17 | 18 |
| Runs with a page cut | 29 | 44 |
| Runs that read a renumbered document (no empty read) | 5 | 2 |
| Runs with a failed opening | 10 | — |
| Runs delayed by the opening timeout and then steered | 4 | — |
| **All affected runs** | **60** | **60** |
| of which failures | 15 | 16 |

Status: the fixes are written and tested. The affected runs have not been re-run, so every number
in this document is from the original runs.

## Accuracy once the benchmark's errors are removed

Counting judge errors (D3) as correct and setting aside questions with a wrong gold label or a
flawed question (D1, D2):

| | Reported | Adjusted |
|---|--:|--:|
| gpt-5.5 | 751 / 830 = 90.5% | 760 / 820 = 92.7% |
| Qwen3.8 | 659 / 830 = 79.4% | 666 / 818 = 81.4% |

These come from the rubric labels, not from a new judging run.

## Where the labels could move

- **What counts as answer-bearing.** A document counts if it states the answer or ties the clues to
  the target. One that names only a bridge entity, or contains the answer string by coincidence,
  does not. A looser reading would move a few M1 cases to M2, such as Qwen3.8 250, 718 and 1222.
- **D2 because two answers fit.** These rulings are all medium confidence. If "the following year"
  in 624 fixes the year, both runs become M4.
- **D1 because the gold is unreachable** (561, 869, 873, 930). These rest on BM25 probes and an
  88,693-document copy of the corpus, not an exhaustive scan.
- **Qwen3.8 1201** (D2, low confidence) could instead be M3 with the `data_flaw` flag. The quote the
  question relies on is spoken by a different person in the only document that has it.

## Files

- Rubric: `docs/trace_study/failure_rubric.md`
- Labels with evidence (step numbers, docids, quotes) and both pass labels:
  `runs/trace_study/rubric/labels.jsonl` (gitignored)
- Tallies, drivers by stage, flags: `docs/trace_study/failure_sources_tallies.md`
- Merge and tally script: `scripts/trace_study/merge_rubric.py`
- BM25 rank check used for the time-limit rulings: `scripts/trace_study/bm25_rank.sh`
- Full studies: `docs/trace_study/study_gpt55_qfull.md` and `docs/trace_study/study_qwen38_qfull.md`
