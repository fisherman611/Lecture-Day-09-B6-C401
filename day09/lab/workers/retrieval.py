"""
workers/retrieval.py — Retrieval Worker
Sprint 2: Implement retrieval từ ChromaDB, trả về chunks + sources.

Input (từ AgentState):
    - task: câu hỏi cần retrieve
    - (optional) retrieved_chunks nếu đã có từ trước

Output (vào AgentState):
    - retrieved_chunks: list of {"text", "source", "score", "metadata"}
    - retrieved_sources: list of source filenames
    - worker_io_log: log input/output của worker này

Gọi độc lập để test:
    python workers/retrieval.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ─── Paths ───────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_LAB_ROOT = os.path.dirname(_HERE)  # workers/ → lab/
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(_LAB_ROOT, "chroma_db"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "day09_docs")

# ─────────────────────────────────────────────
# Worker Contract (xem contracts/worker_contracts.yaml)
# Input:  {"task": str, "top_k": int = 3}
# Output: {"retrieved_chunks": list, "retrieved_sources": list, "error": dict | None}
# ─────────────────────────────────────────────

WORKER_NAME = "retrieval_worker"
DEFAULT_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "7"))


_ST_MODEL = None  # module-level cache
_OAI_CLIENT = None  # OpenAI client cache

# Embedding model priority:
# 1. OpenAI text-embedding-3-small (multilingual, tốt nhất cho tiếng Việt)
# 2. Sentence Transformers all-MiniLM-L6-v2 (offline fallback)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai")  # "openai" | "local"
OPENAI_EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536  # openai dim; local = 384


def _get_embedding_fn():
    """Trả về embedding function (cached)."""
    global _ST_MODEL, _OAI_CLIENT

    # Option A: OpenAI text-embedding-3-small (multilingual)
    if EMBEDDING_MODEL == "openai":
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key and not openai_key.startswith("sk-..."):
            try:
                from openai import OpenAI
                if _OAI_CLIENT is None:
                    _OAI_CLIENT = OpenAI(api_key=openai_key)
                client = _OAI_CLIENT

                def embed_oai(text: str) -> list:
                    resp = client.embeddings.create(
                        input=text,
                        model=OPENAI_EMBED_MODEL,
                    )
                    return resp.data[0].embedding

                return embed_oai
            except Exception as e:
                print(f"⚠️  OpenAI embedding failed: {e}, falling back to local")

    # Option B: Sentence Transformers (offline)
    try:
        from sentence_transformers import SentenceTransformer
        if _ST_MODEL is None:
            _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        model = _ST_MODEL

        def embed_local(text: str) -> list:
            return model.encode([text])[0].tolist()

        return embed_local
    except ImportError:
        pass

    # Fallback
    import random

    def embed_random(text: str) -> list:
        return [random.random() for _ in range(384)]

    print("⚠️  WARNING: Using random embeddings.")
    return embed_random


# Preload model ngay khi import để tránh cold-start latency
try:
    _get_embedding_fn()
except Exception:
    pass


def _get_collection():
    """Kết nối ChromaDB collection."""
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    try:
        collection = client.get_collection(CHROMA_COLLECTION)
    except Exception:
        collection = client.get_or_create_collection(
            CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )
        print(f"⚠️  Collection '{CHROMA_COLLECTION}' chưa có data. Chạy index script trong README trước.")
    return collection


def retrieve_dense(query: str, top_k: int = DEFAULT_TOP_K) -> list:
    """Dense retrieval via ChromaDB."""
    embed = _get_embedding_fn()
    query_embedding = embed(query)

    try:
        collection = _get_collection()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "distances", "metadatas"]
        )
        chunks = []
        for doc, dist, meta in zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0]
        ):
            chunks.append({
                "text": doc,
                "source": meta.get("source", "unknown"),
                "score": round(1 - dist, 4),
                "metadata": meta,
            })
        return chunks
    except Exception as e:
        print(f"⚠️  ChromaDB query failed: {e}")
        return []


def _get_all_chunks() -> list:
    """Lấy toàn bộ chunks từ ChromaDB (dùng cho BM25)."""
    try:
        col = _get_collection()
        result = col.get(include=["documents", "metadatas"])
        return [
            {"text": doc, "source": meta.get("source", "unknown"), "metadata": meta}
            for doc, meta in zip(result["documents"], result["metadatas"])
        ]
    except Exception:
        return []


# BM25 index cache
_BM25_INDEX = None
_BM25_CORPUS = None
_CROSS_ENCODER = None  # cache reranker


def _get_bm25_index():
    """Build và cache BM25 index từ toàn bộ chunks."""
    global _BM25_INDEX, _BM25_CORPUS
    if _BM25_INDEX is not None:
        return _BM25_INDEX, _BM25_CORPUS

    try:
        from rank_bm25 import BM25Okapi
        all_chunks = _get_all_chunks()
        if not all_chunks:
            return None, None

        # Tokenize đơn giản: split whitespace + lowercase
        tokenized = [c["text"].lower().split() for c in all_chunks]
        _BM25_CORPUS = all_chunks
        _BM25_INDEX = BM25Okapi(tokenized)
        return _BM25_INDEX, _BM25_CORPUS
    except ImportError:
        return None, None


def retrieve_bm25(query: str, top_k: int = DEFAULT_TOP_K) -> list:
    """BM25 sparse retrieval — tốt cho exact match (tên, số, mã)."""
    bm25, corpus = _get_bm25_index()
    if bm25 is None or not corpus:
        return []

    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    # Lấy top_k indices
    import numpy as np
    top_indices = np.argsort(scores)[::-1][:top_k]

    chunks = []
    max_score = scores[top_indices[0]] if len(top_indices) > 0 else 1.0
    for idx in top_indices:
        if scores[idx] <= 0:
            break
        c = corpus[idx]
        chunks.append({
            "text": c["text"],
            "source": c["source"],
            "score": round(float(scores[idx]) / max(max_score, 1e-9), 4),  # normalize 0-1
            "metadata": c.get("metadata", {}),
        })
    return chunks


def retrieve_hybrid(query: str, top_k: int = DEFAULT_TOP_K) -> list:
    """
    Hybrid retrieval: Dense + BM25 với Reciprocal Rank Fusion (RRF).

    RRF score = sum(1 / (k + rank_i)) cho mỗi retriever
    k=60 là constant chuẩn từ paper gốc.
    """
    K = 60
    dense_results = retrieve_dense(query, top_k=top_k * 2)
    bm25_results = retrieve_bm25(query, top_k=top_k * 2)

    # Build RRF score map keyed by text[:80]
    rrf_scores: dict = {}
    chunk_map: dict = {}

    for rank, chunk in enumerate(dense_results):
        key = chunk["text"][:80]
        rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (K + rank + 1)
        chunk_map[key] = chunk

    for rank, chunk in enumerate(bm25_results):
        key = chunk["text"][:80]
        rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (K + rank + 1)
        if key not in chunk_map:
            chunk_map[key] = chunk

    # Sort by RRF score
    sorted_keys = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)

    results = []
    for key in sorted_keys[:top_k]:
        chunk = chunk_map[key].copy()
        chunk["score"] = round(rrf_scores[key], 4)
        results.append(chunk)

    return results


def rerank(query: str, chunks: list, top_k: int = 5) -> list:
    """
    Cross-encoder reranker với model cache.
    Chỉ áp dụng khi query có từ tiếng Anh — model ms-marco train trên English.
    Với query thuần tiếng Việt, trả về hybrid RRF results trực tiếp.
    """
    if not chunks:
        return chunks

    # Detect nếu query có đủ từ tiếng Anh để reranker có ích
    import re
    ascii_words = re.findall(r'[a-zA-Z]{3,}', query)
    if len(ascii_words) < 2:
        # Query thuần tiếng Việt — skip reranker, dùng RRF score
        return chunks[:top_k]

    global _CROSS_ENCODER
    try:
        from sentence_transformers import CrossEncoder
        if _CROSS_ENCODER is None:
            _CROSS_ENCODER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        pairs = [(query, c["text"]) for c in chunks]
        scores = _CROSS_ENCODER.predict(pairs)
        for i, chunk in enumerate(chunks):
            chunk["rerank_score"] = float(scores[i])
        return sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)[:top_k]
    except Exception:
        return chunks[:top_k]


# Preload reranker cùng lúc với embedding model
try:
    rerank("warmup", [{"text": "warmup", "source": "", "score": 0}], top_k=1)
except Exception:
    pass


def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Args:
        state: AgentState dict

    Returns:
        Updated AgentState với retrieved_chunks và retrieved_sources
    """
    task = state.get("task", "")
    top_k = state.get("retrieval_top_k", DEFAULT_TOP_K)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])

    state["workers_called"].append(WORKER_NAME)

    # Log worker IO (theo contract)
    worker_io = {
        "worker": WORKER_NAME,
        "input": {"task": task, "top_k": top_k},
        "output": None,
        "error": None,
    }

    try:
        # Hybrid retrieval: Dense + BM25 + RRF fusion
        chunks = retrieve_hybrid(task, top_k=top_k * 2)

        # Rerank để tăng precision
        chunks = rerank(task, chunks, top_k=top_k)

        task_lower = task.lower()

        # Query expansion: semantic sub-queries thay vì hardcode chunk IDs
        extra_queries = []

        # P1 notification channels
        if any(kw in task_lower for kw in ["thông báo", "kênh", "notification", "pagerduty", "ai nhận"]):
            extra_queries.append("PagerDuty Slack email kênh liên lạc incident P1")
            extra_queries.append("escalate Senior Engineer không phản hồi P1")

        # Temporal / policy version scoping
        if any(kw in task_lower for kw in ["31/01", "01/02", "phiên bản", "version", "áp dụng từ"]):
            extra_queries.append("chính sách hoàn tiền effective date phiên bản áp dụng từ ngày")

        # IT FAQ — cross-lingual expansion (embedding model yếu với tiếng Việt)
        if any(kw in task_lower for kw in ["mật khẩu", "password", "đổi mật khẩu", "cảnh báo"]):
            extra_queries.append("password change policy days warning notification")
            extra_queries.append("mật khẩu thay đổi định kỳ ngày cảnh báo")

        # Dedup và merge extra chunks
        existing = {c.get("text", "")[:60] for c in chunks}
        for eq in extra_queries:
            for ec in retrieve_hybrid(eq, top_k=3):
                key = ec.get("text", "")[:60]
                if key not in existing:
                    chunks.append(ec)
                    existing.add(key)

        sources = list({c["source"] for c in chunks})

        state["retrieved_chunks"] = chunks
        state["retrieved_sources"] = sources

        worker_io["output"] = {
            "chunks_count": len(chunks),
            "sources": sources,
        }
        state["history"].append(
            f"[{WORKER_NAME}] retrieved {len(chunks)} chunks from {sources}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "RETRIEVAL_FAILED", "reason": str(e)}
        state["retrieved_chunks"] = []
        state["retrieved_sources"] = []
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    # Ghi worker IO vào state để trace
    state.setdefault("worker_io_logs", []).append(worker_io)

    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Retrieval Worker — Standalone Test")
    print("=" * 50)

    test_queries = [
        "SLA ticket P1 là bao lâu?",
        "Điều kiện được hoàn tiền là gì?",
        "Ai phê duyệt cấp quyền Level 3?",
    ]

    for query in test_queries:
        print(f"\n▶ Query: {query}")
        result = run({"task": query})
        chunks = result.get("retrieved_chunks", [])
        print(f"  Retrieved: {len(chunks)} chunks")
        for c in chunks[:2]:
            print(f"    [{c['score']:.3f}] {c['source']}: {c['text'][:80]}...")
        print(f"  Sources: {result.get('retrieved_sources', [])}")

    print("\n✅ retrieval_worker test done.")
