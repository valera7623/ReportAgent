"""ChromaDB-backed knowledge base for error fixes."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.self_healing.config import (
    CHROMA_PERSIST_DIR,
    EMBEDDING_MODEL,
    SIMILARITY_THRESHOLD,
    ensure_chroma_dir,
)
from app.utils.logger import get_logger

logger = get_logger("self_healing_kb", "log_self_healing.json")

COLLECTION_NAME = "error_fixes"
_kb_instance: "ErrorKnowledgeBase | None" = None
_kb_lock = threading.Lock()
_chroma_unavailable = False


class EmbeddingFunction:
    """Local sentence-transformers embeddings (no OpenAI API)."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        model = self._load_model()
        embeddings = model.encode(input, show_progress_bar=False, normalize_embeddings=True)
        return embeddings.tolist()


class ErrorKnowledgeBase:
    """Vector store for error → fix mappings."""

    def __init__(self, persist_dir: str, embedding_model: str) -> None:
        import chromadb
        from chromadb.config import Settings

        ensure_chroma_dir()
        self._embedding_fn = EmbeddingFunction(embedding_model)
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ErrorKnowledgeBase initialized at %s (%d records)",
            persist_dir,
            self._collection.count(),
        )

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_record(self, doc_id: str, document: str, metadata: dict[str, Any]) -> dict[str, Any]:
        context_raw = metadata.get("context", "{}")
        try:
            context = json.loads(context_raw) if isinstance(context_raw, str) else context_raw
        except json.JSONDecodeError:
            context = {}

        return {
            "id": doc_id,
            "error_text": document,
            "error_type": metadata.get("error_type", "unknown"),
            "agent_name": metadata.get("agent_name", "unknown"),
            "stack_trace": metadata.get("stack_trace", ""),
            "solution_prompt": metadata.get("solution_prompt", ""),
            "solution_code": metadata.get("solution_code", ""),
            "was_successful": metadata.get("was_successful") in (True, "true", "True", 1, "1"),
            "success_count": int(metadata.get("success_count", 0)),
            "fail_count": int(metadata.get("fail_count", 0)),
            "context": context,
            "created_at": metadata.get("created_at", ""),
            "last_used_at": metadata.get("last_used_at", ""),
            "similarity": float(metadata.get("_similarity", 0)),
        }

    def add_error(self, error_record: dict[str, Any]) -> str:
        """Add or update an error fix record. Returns document id."""
        doc_id = error_record.get("id") or str(uuid.uuid4())
        error_text = error_record.get("error_text", "")
        if not error_text:
            raise ValueError("error_text is required")

        metadata = {
            "error_type": error_record.get("error_type", "unknown"),
            "agent_name": error_record.get("agent_name", "unknown"),
            "stack_trace": (error_record.get("stack_trace") or "")[:500],
            "solution_prompt": error_record.get("solution_prompt", ""),
            "solution_code": error_record.get("solution_code", ""),
            "was_successful": bool(error_record.get("was_successful", False)),
            "success_count": int(error_record.get("success_count", 0)),
            "fail_count": int(error_record.get("fail_count", 0)),
            "context": json.dumps(error_record.get("context") or {}, ensure_ascii=False),
            "created_at": error_record.get("created_at") or self._now_iso(),
            "last_used_at": error_record.get("last_used_at") or self._now_iso(),
        }

        embedding = self._embedding_fn([error_text])[0]

        existing = self._collection.get(ids=[doc_id])
        if existing and existing.get("ids"):
            self._collection.update(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[error_text],
                metadatas=[metadata],
            )
        else:
            self._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[error_text],
                metadatas=[metadata],
            )

        logger.info("Added error fix record %s (agent=%s)", doc_id, metadata["agent_name"])
        return doc_id

    def search_similar_errors(
        self,
        error_text: str,
        agent_name: str,
        limit: int = 3,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Find similar past errors with optional agent filter."""
        if self._collection.count() == 0:
            return []

        min_score = threshold if threshold is not None else SIMILARITY_THRESHOLD
        query_embedding = self._embedding_fn([error_text])[0]

        where: dict[str, Any] | None = {"agent_name": agent_name} if agent_name else None

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(limit * 3, max(limit, 10)),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("ChromaDB query failed: %s", exc)
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(limit * 3, max(limit, 10)),
                include=["documents", "metadatas", "distances"],
            )

        matches: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_id, doc, meta, distance in zip(ids, docs, metas, distances):
            similarity = 1.0 - float(distance)
            if similarity < min_score:
                continue
            meta = dict(meta or {})
            meta["_similarity"] = similarity
            record = self._parse_record(doc_id, doc or "", meta)
            record["similarity"] = similarity
            matches.append(record)

        matches.sort(
            key=lambda r: (
                r.get("was_successful", False),
                r.get("success_count", 0) - r.get("fail_count", 0),
                r.get("similarity", 0),
            ),
            reverse=True,
        )
        return matches[:limit]

    def _update_counters(self, fix_id: str, *, success_delta: int = 0, fail_delta: int = 0) -> None:
        fetched = self._collection.get(ids=[fix_id], include=["documents", "metadatas"])
        if not fetched.get("ids"):
            logger.warning("Fix record not found: %s", fix_id)
            return

        doc_id = fetched["ids"][0]
        document = fetched["documents"][0]
        metadata = dict(fetched["metadatas"][0])
        metadata["success_count"] = int(metadata.get("success_count", 0)) + success_delta
        metadata["fail_count"] = int(metadata.get("fail_count", 0)) + fail_delta
        metadata["last_used_at"] = self._now_iso()

        self._collection.update(
            ids=[doc_id],
            documents=[document],
            metadatas=[metadata],
        )

    def mark_fix_success(self, fix_id: str) -> None:
        """Increment success_count and mark as successful."""
        fetched = self._collection.get(ids=[fix_id], include=["documents", "metadatas"])
        if not fetched.get("ids"):
            return
        metadata = dict(fetched["metadatas"][0])
        metadata["success_count"] = int(metadata.get("success_count", 0)) + 1
        metadata["was_successful"] = True
        metadata["last_used_at"] = self._now_iso()
        self._collection.update(
            ids=[fix_id],
            documents=[fetched["documents"][0]],
            metadatas=[metadata],
        )

    def mark_fix_failure(self, fix_id: str) -> None:
        """Increment fail_count."""
        self._update_counters(fix_id, fail_delta=1)

    def confirm_fix(self, fix_id: str) -> bool:
        """Manually confirm a fix as working."""
        fetched = self._collection.get(ids=[fix_id], include=["documents", "metadatas"])
        if not fetched.get("ids"):
            return False
        metadata = dict(fetched["metadatas"][0])
        metadata["was_successful"] = True
        metadata["last_used_at"] = self._now_iso()
        self._collection.update(
            ids=[fix_id],
            documents=[fetched["documents"][0]],
            metadatas=[metadata],
        )
        return True

    def get_record(self, fix_id: str) -> dict[str, Any] | None:
        fetched = self._collection.get(ids=[fix_id], include=["documents", "metadatas"])
        if not fetched.get("ids"):
            return None
        return self._parse_record(
            fetched["ids"][0],
            fetched["documents"][0],
            fetched["metadatas"][0],
        )

    def list_all(self) -> list[dict[str, Any]]:
        """Return all records (for stats and learning task)."""
        total = self._collection.count()
        if total == 0:
            return []
        fetched = self._collection.get(include=["documents", "metadatas"])
        records = []
        for doc_id, doc, meta in zip(
            fetched.get("ids", []),
            fetched.get("documents", []),
            fetched.get("metadatas", []),
        ):
            records.append(self._parse_record(doc_id, doc or "", dict(meta or {})))
        return records

    def get_stats(self) -> dict[str, Any]:
        """Return knowledge base statistics."""
        records = self.list_all()
        total = len(records)
        successful = sum(1 for r in records if r.get("was_successful"))
        total_applications = sum(r.get("success_count", 0) + r.get("fail_count", 0) for r in records)

        agent_counts: dict[str, int] = {}
        error_counts: dict[str, int] = {}
        for r in records:
            agent = r.get("agent_name", "unknown")
            agent_counts[agent] = agent_counts.get(agent, 0) + 1
            err_key = (r.get("error_text") or "")[:80]
            error_counts[err_key] = error_counts.get(err_key, 0) + 1

        top_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        most_healed = sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_fixes": total,
            "successful_fixes": successful,
            "success_rate": round(successful / total, 4) if total else 0.0,
            "total_applications": total_applications,
            "top_errors": [{"error": e, "count": c} for e, c in top_errors],
            "most_healed_agents": [{"agent": a, "count": c} for a, c in most_healed],
        }

    def find_stale_failures(self, min_age_days: int = 7) -> list[dict[str, Any]]:
        """Records where fail_count > success_count and last_used_at older than min_age_days."""
        cutoff = datetime.now(timezone.utc).timestamp() - min_age_days * 86400
        stale: list[dict[str, Any]] = []
        for record in self.list_all():
            if record.get("fail_count", 0) <= record.get("success_count", 0):
                continue
            last_used = record.get("last_used_at", "")
            try:
                ts = datetime.fromisoformat(last_used.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                ts = 0
            if ts < cutoff:
                stale.append(record)
        return stale

    def delete_fix(self, fix_id: str) -> bool:
        """Remove a fix record from ChromaDB."""
        fetched = self._collection.get(ids=[fix_id])
        if not fetched.get("ids"):
            return False
        self._collection.delete(ids=[fix_id])
        logger.info("Deleted fix record %s", fix_id)
        return True

    def rebuild_index(self) -> int:
        """Re-fetch all records (ChromaDB persistent client auto-manages index)."""
        count = self._collection.count()
        logger.info("ChromaDB index verified, %d records", count)
        return count

    def get_extended_stats(self) -> dict[str, Any]:
        """Extended stats with top fixes and daily success trend."""
        base = self.get_stats()
        records = self.list_all()

        fix_scores: dict[str, dict[str, Any]] = {}
        daily: dict[str, dict[str, int]] = {}

        for r in records:
            fid = r.get("id", "")
            score = r.get("success_count", 0) - r.get("fail_count", 0)
            fix_scores[fid] = {
                "fix_id": fid,
                "error": (r.get("error_text") or "")[:80],
                "agent": r.get("agent_name"),
                "score": score,
                "success_count": r.get("success_count", 0),
            }
            day = (r.get("last_used_at") or r.get("created_at") or "")[:10]
            if day:
                bucket = daily.setdefault(day, {"attempts": 0, "successes": 0})
                bucket["attempts"] += r.get("success_count", 0) + r.get("fail_count", 0)
                bucket["successes"] += r.get("success_count", 0)

        top_fixes = sorted(fix_scores.values(), key=lambda x: x["score"], reverse=True)[:5]
        top_errors = base.get("top_errors", [])[:5]
        daily_trend = [
            {
                "date": d,
                "attempts": v["attempts"],
                "successes": v["successes"],
                "success_rate": round(v["successes"] / v["attempts"], 4) if v["attempts"] else 0,
            }
            for d, v in sorted(daily.items())
        ][-14:]

        return {
            **base,
            "top_errors": top_errors,
            "top_fixes": top_fixes,
            "daily_success_trend": daily_trend,
        }


def force_seed_knowledge_base(*, overwrite: bool = False) -> tuple[int, int]:
    """Load seed fixes. Returns (imported, skipped)."""
    import json
    from pathlib import Path

    from app.self_healing.init_kb import SEED_FILE

    kb = get_knowledge_base()
    if kb is None:
        return 0, 0

    if not SEED_FILE.is_file():
        return 0, 0

    with open(SEED_FILE, encoding="utf-8") as fh:
        seeds = json.load(fh)

    imported = 0
    skipped = 0
    for entry in seeds:
        fix_id = entry.get("id")
        if not overwrite and fix_id and kb.get_record(fix_id):
            skipped += 1
            continue
        try:
            kb.add_error(entry)
            imported += 1
        except Exception as exc:
            logger.warning("Seed import failed for %s: %s", fix_id, exc)
            skipped += 1
    return imported, skipped


def get_knowledge_base() -> ErrorKnowledgeBase | None:
    """Return singleton knowledge base or None if ChromaDB unavailable."""
    global _kb_instance, _chroma_unavailable

    if _chroma_unavailable:
        return None

    with _kb_lock:
        if _kb_instance is not None:
            return _kb_instance
        try:
            _kb_instance = ErrorKnowledgeBase(
                persist_dir=CHROMA_PERSIST_DIR,
                embedding_model=EMBEDDING_MODEL,
            )
            return _kb_instance
        except Exception as exc:
            logger.error("Failed to initialize ChromaDB: %s — self-healing disabled", exc)
            _chroma_unavailable = True
            return None


def reset_knowledge_base() -> None:
    """Reset singleton (for tests)."""
    global _kb_instance, _chroma_unavailable
    with _kb_lock:
        _kb_instance = None
        _chroma_unavailable = False
