"""Graph-free RAG baseline for mode="rag" on POST /api/ask.

Deliberately dumb: plain BM25 retrieval over flattened text chunks (issue/PR/doc
titles + bodies), then a single LLM call with the retrieved chunks as context.
No entity resolution, no relationships, no ownership/dependency traversal, no
tool calls. It exists as a comparison point to show why the graph matters -
ask it "what breaks if cartservice goes down" and it has no way to know.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from agent.llm import Message, get_provider

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_graph.json"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _load_corpus() -> list[dict]:
    raw = json.loads(_FIXTURE_PATH.read_text())
    chunks = []
    for n in raw["nodes"]:
        if n["label"] not in ("Issue", "PR", "Doc"):
            continue
        text = " ".join(filter(None, [n.get("name"), n.get("body")]))
        chunks.append({"id": n["id"], "label": n["label"], "text": text, "source_url": n.get("source_url")})
    return chunks


class _BM25:
    """Minimal BM25 (Robertson/Sparck Jones) - no external dependency on purpose,
    to keep this baseline obviously separate from the graph stack."""

    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = documents
        self.doc_lengths = [len(d) for d in documents]
        self.avg_len = (sum(self.doc_lengths) / len(documents)) if documents else 0.0

        self.doc_freqs: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for doc in documents:
            freq: dict[str, int] = {}
            for term in doc:
                freq[term] = freq.get(term, 0) + 1
            self.doc_freqs.append(freq)
            for term in freq:
                df[term] = df.get(term, 0) + 1

        n_docs = len(documents)
        self.idf = {term: math.log(1 + (n_docs - count + 0.5) / (count + 0.5)) for term, count in df.items()}

    def score(self, query_terms: list[str]) -> list[float]:
        scores = [0.0] * len(self.documents)
        for i, freq in enumerate(self.doc_freqs):
            length = self.doc_lengths[i] or 1
            for term in query_terms:
                if term not in freq:
                    continue
                idf = self.idf.get(term, 0.0)
                f = freq[term]
                denom = f + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
                scores[i] += idf * (f * (self.k1 + 1)) / (denom or 1)
        return scores


def _retrieve(question: str, top_k: int = 4) -> list[dict]:
    corpus = _load_corpus()
    if not corpus:
        return []
    tokenized = [_tokenize(c["text"]) for c in corpus]
    bm25 = _BM25(tokenized)
    scores = bm25.score(_tokenize(question))
    ranked = sorted(zip(corpus, scores), key=lambda cs: cs[1], reverse=True)
    return [c for c, s in ranked[:top_k] if s > 0]


def answer_question(question: str) -> str:
    chunks = _retrieve(question)
    if not chunks:
        return (
            "(RAG baseline) No relevant text chunks found via BM25 retrieval over issue/PR/doc titles. "
            "This baseline has no notion of services, ownership, or dependencies, so it can't say anything "
            "useful here - this is exactly the gap graph mode closes."
        )

    context = "\n\n".join(f"[{c['label']} {c['id']}] {c['text']} (source: {c['source_url']})" for c in chunks)
    prompt = (
        "You are answering using ONLY plain-text retrieval (BM25) over issue/PR/doc titles and bodies - "
        "you have NO access to a graph, no entity relationships, no ownership data, and no dependency data. "
        "Answer the question using only the context chunks below, and be explicit about what you cannot know "
        "without graph relationships (e.g. ownership, blast radius, dependency paths).\n\n"
        f"Context chunks:\n{context}\n\nQuestion: {question}"
    )
    provider = get_provider()
    response = provider.generate(
        "You are a plain-text retrieval baseline with no graph access.",
        [Message(role="user", content=prompt)],
        tools=[],
    )
    return response.text
