#!/bin/bash
# Build one BM25 index per attack family: the BrowseComp-Plus corpus plus that family's gated docs.
# Output: indexes/bm25_<family>. Takes ~5 minutes per index with 16 threads.
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$REPO"
mkdir -p corpus indexes
[[ -f corpus/corpus.jsonl ]] || "$PY" scripts/dump_corpus.py "$BCP_ROOT" corpus/corpus.jsonl
for f in f1 f2 f4; do
  mkdir -p corpus/in_$f
  ln -sf ../corpus.jsonl corpus/in_$f/corpus.jsonl
  "$PY" -c "
import json,sys
with open('corpus/in_$f/injected.jsonl','w') as o:
    for l in open('data/attacks/$f/docs.jsonl'):
        d=json.loads(l); o.write(json.dumps({'id':d['docid'],'contents':d['contents']},ensure_ascii=False)+'\n')"
  "$PY" -m pyserini.index.lucene --collection JsonCollection --input corpus/in_$f --index indexes/bm25_$f \
    --generator DefaultLuceneDocumentGenerator --threads 16 --storeRaw &
done
wait
echo "indexes built"
