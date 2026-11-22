# Shared settings. Source from the other scripts.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BCP_ROOT="${BCP_ROOT:-$REPO/../BrowseComp-Plus}"   # BrowseComp-Plus checkout (data, indexes/bm25, search_agent)
PY="${PY:-$BCP_ROOT/.venv/bin/python}"              # Python with pyserini, openai, transformers
[[ -f "$REPO/.env" ]] && { set -a; source "$REPO/.env"; set +a; }   # OPENAI_API_KEY (and OPENROUTER_API_KEY for Qwen guesses)
export REPO BCP_ROOT PY
