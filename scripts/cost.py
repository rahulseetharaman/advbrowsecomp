"""Spend so far across stage-2 agent runs (gpt-5.4-mini: $0.75/M input, $0.075/M cached, $4.50/M output)."""
import glob, json, sys
from pathlib import Path
tot = 0.0; n = 0
for f in glob.glob(str(Path(__file__).resolve().parents[1] / "results" / "runs" / "**" / "run_*.json"), recursive=True):
    try:
        u = json.load(open(f))["usage"]
    except Exception:
        continue
    tot += (u["input_tokens"] - u["input_tokens_cached"]) * 0.75e-6 + u["input_tokens_cached"] * 0.075e-6 + u["output_tokens"] * 4.5e-6
    n += 1
print(f"{n} runs, ${tot:.2f}")
if len(sys.argv) > 1 and tot > float(sys.argv[1]):
    sys.exit(3)
