"""Dump BrowseComp-Plus's BM25 index to JSONL {"id","contents"} exactly as stored. Usage: dump_corpus.py <bcp_root> <out.jsonl>"""
import json, sys
from pyserini.search.lucene import LuceneSearcher
s = LuceneSearcher(f"{sys.argv[1]}/indexes/bm25")
with open(sys.argv[2], "w") as f:
    for i in range(s.num_docs):
        d = s.doc(i)
        f.write(json.dumps({"id": d.docid(), "contents": json.loads(d.raw())["contents"]}, ensure_ascii=False) + "\n")
print("dumped", s.num_docs)
