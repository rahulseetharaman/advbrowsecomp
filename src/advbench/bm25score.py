"""Score documents that are not in the index against the original index's BM25 statistics.

Mirrors Lucene BM25Similarity (no (k1+1) factor) with Anserini's bag-of-words query, where a
query term repeated n times gets boost n. Used to check, before indexing, where an injected doc
would rank for a query: compare its score to the scores of the original top-k hits.
"""
from __future__ import annotations
import json, math, os
from collections import Counter

os.environ.setdefault("_JAVA_OPTIONS", "-Xmx16g")
if os.environ.get("JAVA_HOME"):
    os.environ["PATH"] = os.environ["JAVA_HOME"] + "/bin:" + os.environ["PATH"]

from pyserini.search.lucene import LuceneSearcher  # noqa: E402
from pyserini.index.lucene import LuceneIndexReader  # noqa: E402
from pyserini.analysis import Analyzer, get_lucene_analyzer  # noqa: E402

from common import INDEX  # noqa: E402

from collections import namedtuple  # noqa: E402
Hit = namedtuple("Hit", "docid score")

K1, B = 0.9, 0.4  # Pyserini LuceneSearcher defaults, used by this repo's BM25 searcher


class Scorer:
    def __init__(self, index: str = INDEX):
        self.searcher = LuceneSearcher(index)
        self.searcher.set_bm25(k1=K1, b=B)
        self.reader = LuceneIndexReader(index)
        st = self.reader.stats()
        self.N = st["documents"]
        self.avgdl = st["total_terms"] / st["documents"]
        self.an = Analyzer(get_lucene_analyzer())
        self._df: dict[str, int] = {}

    def analyze(self, text: str) -> list[str]:
        return self.an.analyze(text)

    def df(self, term: str) -> int:
        if term not in self._df:
            df, _ = self.reader.get_term_counts(term, analyzer=None)
            self._df[term] = df or 0
        return self._df[term]

    def idf(self, term: str) -> float:
        df = self.df(term)
        return math.log(1 + (self.N - df + 0.5) / (df + 0.5))

    def score_terms(self, qterms: Counter, dterms: Counter, dl: int) -> float:
        s = 0.0
        norm = K1 * (1 - B + B * dl / self.avgdl)
        for t, qn in qterms.items():
            tf = dterms.get(t, 0)
            if tf and self.df(t):
                s += qn * self.idf(t) * tf / (tf + norm)
        return s

    def score(self, query: str, text: str) -> float:
        q = Counter(self.analyze(query))
        d = self.analyze(text)
        return self.score_terms(q, Counter(d), len(d))

    def search(self, query: str, k: int = 1000):
        """Plain (docid, score) hits; Java hit objects carry full documents, so they are not kept."""
        return [Hit(h.docid, float(h.score)) for h in self.searcher.search(query, k=k)]

    def raw_contents(self, docid: str) -> str:
        doc = self.searcher.doc(docid)
        raw = doc.raw()
        try:
            p = json.loads(raw)
            return p.get("contents") or p.get("text") or raw
        except json.JSONDecodeError:
            return raw

    def rank_of(self, query: str, text: str, k: int = 1000, hits=None) -> tuple[int, float]:
        """1-based rank the text would take among the original top-k (k+1 means beyond k)."""
        hits = hits if hits is not None else self.search(query, k)
        s = self.score(query, text)
        rank = 1 + sum(1 for h in hits if h.score > s)
        return rank, s
