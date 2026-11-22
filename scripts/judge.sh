#!/bin/bash
# Grade every arm with BrowseComp-Plus's OpenAI judge (gpt-4.1). Output: results/evals/<arm>/.
source "$(dirname "$0")/env.sh"
cd "$BCP_ROOT"
for a in clean f1 f2 f4; do
  "$PY" scripts_evaluation/evaluate_with_openai.py --input_dir "$REPO/results/runs/$a" --eval_dir "$REPO/results/evals_raw/$a" &
done
wait
