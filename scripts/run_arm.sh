#!/bin/bash
# Run one arm of the agent experiment with BrowseComp-Plus's search agent.
# Usage: run_arm.sh <arm: clean|f1|f2|f4> [budget_usd]
# gpt-5.4-mini, medium effort, BM25 top-5 with 512-token snippets, get_document, 25-turn cap.
# A watchdog stops the arm when total spend across results/runs passes the budget (default 120).
set -uo pipefail
source "$(dirname "$0")/env.sh"
ARM=$1; BUDGET=${2:-120}
if [[ $ARM == clean ]]; then IDX="$BCP_ROOT/indexes/bm25"; else IDX="$REPO/indexes/bm25_$ARM"; fi
OUT="$REPO/results/runs/$ARM"; mkdir -p "$OUT" "$REPO/logs"
cd "$BCP_ROOT"
"$PY" search_agent/openai_client.py --model gpt-5.4-mini --reasoning-effort medium \
  --max_tokens 40000 --max-iterations 25 --query "$REPO/data/pilot/pilot99.tsv" --output-dir "$OUT" \
  --searcher-type bm25 --index-path "$IDX" --get-document --num-threads 16 > "$REPO/logs/arm_$ARM.log" 2>&1 &
PID=$!
while kill -0 $PID 2>/dev/null; do
  sleep 30
  "$PY" "$REPO/scripts/cost.py" "$BUDGET" > /dev/null || { echo "budget reached; stopping $ARM"; kill $PID; break; }
done
echo "arm $ARM: $(ls "$OUT"/run_*.json 2>/dev/null | wc -l) runs; $("$PY" "$REPO/scripts/cost.py")"
