"""Redis-backed conversation continuity for the Gemini agent loop."""

import os

import redis.asyncio as redis

_client: redis.Redis | None = None

# How long a conversation can sit idle before it's forgotten (the next
# message under the same conversation_id then just starts fresh). 30
# minutes is a reasonable compromise for a realistic sales/support
# back-and-forth without letting Redis accumulate keys from abandoned
# conversations indefinitely.
SESSION_TTL_SECONDS = 30 * 60

_KEY_PREFIX = "acme:conversation:"


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=int(os.environ["REDIS_PORT"]),
            decode_responses=True,
        )
    return _client


async def get_previous_interaction_id(conversation_id: str) -> str | None:
    """Returns the last Gemini interaction id for this conversation, or
    `None` if the conversation is unknown or its TTL has expired -- either
    way, the caller treats that the same as "start a fresh conversation."
    """
    return await _get_client().get(_KEY_PREFIX + conversation_id)


async def set_previous_interaction_id(conversation_id: str, interaction_id: str) -> None:
    """Stores (or refreshes) the interaction id for this conversation,
    resetting the TTL so an actively-used conversation doesn't expire
    mid-use.
    """
    await _get_client().set(
        _KEY_PREFIX + conversation_id, interaction_id, ex=SESSION_TTL_SECONDS
    )
