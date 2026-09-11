import logging

from app.core.config import settings
from app.db.connector import insert_chat_trace, get_user_full_name

logger = logging.getLogger(__name__)

# Rough public per-1K-token pricing so the admin cost KPI shows a real,
# if approximate, number instead of a random fabricated one. Update this
# if you switch models.
_COST_PER_1K_TOKENS_USD = 0.00005


def log_chat_trace(*, user_id: str, user_role: str, query: str, response: str,
                    agent: str, sentiment: dict | None = None,
                    usage: dict | None = None, kind: str = "chat"):
    """Persist a chat interaction so the admin dashboard can show real
    activity, and forward it to Langfuse if configured.

    `kind` distinguishes an actual back-and-forth chat turn ("chat") from
    quiz bookkeeping events ("quiz_event") that are logged for
    observability but were never a message in the chat window — this is
    what lets us replay a user's real conversation later without pulling
    in "[quiz generated for ...]" lines."""
    usage = usage or {}
    prompt_tokens = usage.get("prompt_tokens", 0) or 0
    completion_tokens = usage.get("completion_tokens", 0) or 0
    latency_ms = usage.get("latency_ms")
    cost_usd = round(((prompt_tokens + completion_tokens) / 1000) * _COST_PER_1K_TOKENS_USD, 6)
    full_name = get_user_full_name(user_id)

    doc = {
        "user_id": user_id,
        "user_role": user_role,
        "full_name": full_name,
        "query": query,
        "response": response,
        "agent": agent,
        "sentiment": sentiment,
        "kind": kind,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
    }
    logger.info(f"[trace] {agent} | user={user_id} | q={query[:60]!r}")
    insert_chat_trace(doc)

    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        try:
            from langfuse import Langfuse
            lf = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_HOST,
            )
            lf.trace(name="kayfa_chat", metadata=doc)
        except Exception as e:
            logger.warning(f"Langfuse trace failed: {e}")