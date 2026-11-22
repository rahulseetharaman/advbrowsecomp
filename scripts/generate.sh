#!/bin/bash
# Generate and gate the three attack families. Specs, queries and guesses first, then each family:
# generate -> contrast fix (F1/F2) -> gate -> realism probe. Re-running skips finished questions.
# Model: ADV_MODEL (default gpt-5.4-mini; the pilot used gpt55). Effort is capped at medium.
set -uo pipefail
source "$(dirname "$0")/env.sh"
cd "$REPO/src/advbench"
"$PY" stage1_spec.py spec && "$PY" stage1_spec.py cb && "$PY" gen_queries.py
pipe() {
  local fam=$1
  "$PY" gen_$fam.py
  [[ $fam != f4 ]] && "$PY" fix_contrast.py $fam
  "$PY" gate.py $fam
  "$PY" realism_probe.py $fam 30
}
pipe f1 & pipe f4 & pipe f2 &
wait
