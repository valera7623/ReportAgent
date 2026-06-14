"""Self-healing RAG: learn from agent errors and apply known fixes."""

from app.self_healing.config import is_self_healing_enabled
from app.self_healing.healing_decorator import with_self_healing
from app.self_healing.vector_store import ErrorKnowledgeBase, get_knowledge_base

__all__ = [
    "ErrorKnowledgeBase",
    "get_knowledge_base",
    "is_self_healing_enabled",
    "with_self_healing",
]
