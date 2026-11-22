# Failure-source rubric (v2)

Unit: one run the judge marked wrong. Each failure gets exactly one **source**, chosen by the
decision order below, plus non-exclusive **drivers** and **flags**. The rubric is applied to the
analyst's full record for the case (`analyses/<qid>/chair.json` if a council ran, else `opus.json`),
the case file (`cases/<qid>.json`, mechanical signals), and the transcript where the record does not
settle a step.

Principle: the scaffold and the experiment setup are blamed only for verified defects and limits.
Anything the model did with a working scaffold is the model's failure: no final answer, an answer
left inside its reasoning, malformed or invented tool calls, loops, misreading, or a wrong frame.
Benchmark faults excuse a failure only when they decided it.

## Terms

- **Target entity:** the entity the question's clues describe; the answer is that entity or one of
  its properties. Entities the agent passes through on the way (an artist who leads to a song, a
  club that leads to a player) are **bridge entities**, not the target.
- **Answer-bearing document:** a document whose text states the answer, or identifies the target
  entity. A document that names only a bridge entity is not answer-bearing.
- **In view:** an answer-bearing document appeared in a preview (title and excerpt), or the answer
  string appeared in tool output **referring to the answer**. A coincidental match (the same word
  naming something else) does not count.
- **Read:** the agent called `read_document` on it and text was actually returned.

## Decision order (first that applies wins)

### 1. D: benchmark data or grading, only when decisive

A flaw counts as the source only if it decided the outcome: the agent's answer is equally valid
given the flaw, the flaw made the gold answer unreachable, or the agent demonstrably followed the
false clue to its wrong answer. A flaw that did not decide the outcome gets the `data_flaw` flag,
and the case is staged as a model failure.

- **D1 Gold label wrong.** Documents show the gold answer does not satisfy the question, or the gold
  documents are about something else. "Suspect" without document evidence is not enough.
- **D2 Question flawed.** Documents show that more than one answer satisfies every clue, or that a
  clue is false for the gold answer.
- **D3 Judge error.** The agent's own Exact Answer field names the same entity or value as the gold,
  differing only in spelling, transliteration, alias, or formatting, where that form is used for the
  same entity in a corpus document or is a standard variant. Containing the full gold string (for
  example "Uche Jombo (Uche Jombo Rodriguez)") also counts. A different field (film year vs
  ceremony year, product vs brand, restaurant vs structure), a different value, or an incomplete
  answer (surname only, part of a list) is **not** D3; it is M4.

### 2. E: scaffold defect

- **E1 Empty read.** `read_document` returned no body for a document with an over-long line (a
  one-line document, or one line longer than the 50 KB cap), and this blocked evidence the agent had
  already targeted correctly.
- **E2 Opening tool failed.** The opening `breadth_search` returned an error for a valid call
  ("decompose failed ... aborted"), so the run did not receive the condition under test.

Tool errors caused by the model's own calls (missing required arguments, tool names that do not
exist, unknown search ids) are not E.

### 3. S: experiment setup

- **S1 Time limit cut a viable path.** The submit-now steer (or the timeout) ended the run while it
  was on the right path. Before the steer the agent had either named the correct target entity as
  its candidate, or had an explicit pending step (a named document read or a query) aimed at an
  answer-bearing document, and the steer blocked that step. If the run was on a wrong path when
  steered, S1 does not apply; record the `steered` flag only. Slow turns are the model's, not the
  setup's: a run that spent its budget slowly and was steered on a wrong path is M.

### 4. M: model failure, by where the evidence chain broke

Apply M0 first. For M1 to M4, take the furthest stage the run reached.

- **M0 No answer produced.** The final output has no Exact Answer: cut-off generation, a degenerate
  repetition loop, reasoning with no answer line, or the run ended without the model producing a
  final answer. A properly formatted abstention ("could not be determined") is not M0; it is staged
  like any other answer.
- **M1 Never in view.** No answer-bearing document was ever in view.
- **M2 In view, not read.** An answer-bearing document was in view, and the agent never read it.
- **M3 Read, not used.** The agent read an answer-bearing document and misread, dismissed, or
  abandoned it, and never held the correct target entity as its candidate.
- **M4 Right entity, wrong final answer.** The agent held the correct target entity as its
  candidate, grounded in evidence, but the final answer gives the wrong field or form, is
  incomplete, or gives a different value.

## Drivers (any number, model failures only)

- `anchor_opening`: committed to an opening (breadth_search) hit that matched only some clues.
- `anchor_memory`: committed to a candidate from its own memory, with no document behind it.
- `premature_commit`: stopped and answered without checking clues it could have checked.
- `clue_relaxed`: ignored or bent a clue the answer fails.
- `query_loop`: repeated or thrashed queries without new information.
- `misread`: misread a document's text.
- `degenerate_output`: repetition loop or cut-off generation.
- `malformed_calls`: invalid or invented tool calls that cost progress.
- `no_search`: answered without searching.

## Flags (any number, all failures)

- `steered`: the submit-now steer arrived. For gpt-5.5 the steer text is only visible when a tool
  was called afterwards, so a run that lasted 630 s or more counts as steered.
- `abstained`: the final answer says it could not be determined.
- `gold_in_opening`: a gold-labelled document was in the opening breadth_search results.
- `empty_read`: the agent hit the empty-read defect, whether or not it was decisive.
- `data_flaw`: documents show a gold or question flaw that did not decide the outcome.

## Output per case

`{qid, study, source, evidence, drivers[], flags[], confidence (high|medium|low), notes}`

`evidence` must cite step numbers, docids, and short quotes that establish the source and stage.

## Changes from v1

- D faults must be decisive; non-decisive ones become the `data_flaw` flag.
- E2 added for opening-tool failures.
- Target entity and answer-bearing document defined; an answer string counts as in view only when
  it refers to the answer.
- D3 vs M4 boundary made explicit.
- Steered flag for gpt-5.5 runs defined by elapsed time.
