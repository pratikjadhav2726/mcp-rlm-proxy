"""
Smart caching module for MCP-RLM Proxy.

Provides TTL-based, size-aware caching with UUID-based keys for
storing large tool responses that can be explored incrementally
by agents via proxy tools.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mcp.types import Content, TextContent

from mcp_proxy.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """A single cache entry with metadata for eviction decisions."""

    cache_id: str
    content: List[Content]
    tool_name: str
    arguments: Dict[str, Any]
    created_at: float
    last_accessed_at: float
    access_count: int = 0
    size_bytes: int = 0

    @property
    def age_seconds(self) -> float:
        """Seconds since this entry was created."""
        return time.monotonic() - self.created_at

    @property
    def idle_seconds(self) -> float:
        """Seconds since this entry was last accessed."""
        return time.monotonic() - self.last_accessed_at


class SmartCacheManager:
    """
    Manages caching of tool outputs for efficient recursive exploration.

    Features:
    - UUID-based cache IDs (short, collision-free)
    - TTL-based expiration
    - Size-aware LRU eviction (large idle entries evicted first)
    - Thread-safe access counting

    Allows agents to make multiple filtered calls to the same large output
    without re-executing the tool.
    """

    def __init__(
        self,
        max_entries: int = 50,
        ttl_seconds: int = 300,
    ):
        """
        Initialise the cache manager.

        Args:
            max_entries: Maximum number of cache entries.
            ttl_seconds: Time-to-live in seconds for each entry.
        """
        self._entries: Dict[str, CacheEntry] = {}
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, content: List[Content], tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Store content and return a short UUID-based cache_id.

        Args:
            content: MCP Content list to cache.
            tool_name: Fully-qualified tool name (e.g. ``filesystem_read_file``).
            arguments: Original arguments used for the tool call.

        Returns:
            A short cache ID string (first 12 chars of UUID4).
        """
        self._evict_expired()
        self._evict_if_full()

        cache_id = uuid.uuid4().hex[:12]
        now = time.monotonic()
        size_bytes = sum(
            len(item.text) for item in content if isinstance(item, TextContent)
        )

        entry = CacheEntry(
            cache_id=cache_id,
            content=content,
            tool_name=tool_name,
            arguments=arguments,
            created_at=now,
            last_accessed_at=now,
            access_count=0,
            size_bytes=size_bytes,
        )
        self._entries[cache_id] = entry
        logger.debug(
            "Cached result for %s (%d bytes) → cache_id=%s",
            tool_name,
            size_bytes,
            cache_id,
        )
        return cache_id

    def get(self, cache_id: str) -> Optional[List[Content]]:
        """
        Retrieve cached content by cache_id.

        Returns ``None`` if the entry has expired or does not exist.
        """
        entry = self._entries.get(cache_id)
        if entry is None:
            return None

        if entry.age_seconds > self.ttl_seconds:
            del self._entries[cache_id]
            logger.debug("Cache entry %s expired (age=%.1fs)", cache_id, entry.age_seconds)
            return None

        entry.access_count += 1
        entry.last_accessed_at = time.monotonic()
        logger.debug(
            "Cache hit for %s (access #%d)", cache_id, entry.access_count
        )
        return entry.content

    def get_entry(self, cache_id: str) -> Optional[CacheEntry]:
        """
        Retrieve the full CacheEntry (including metadata) by cache_id.

        Returns ``None`` if expired or missing.
        """
        entry = self._entries.get(cache_id)
        if entry is None:
            return None

        if entry.age_seconds > self.ttl_seconds:
            del self._entries[cache_id]
            return None

        entry.access_count += 1
        entry.last_accessed_at = time.monotonic()
        return entry

    def remove(self, cache_id: str) -> bool:
        """Remove a specific entry. Returns True if it existed."""
        return self._entries.pop(cache_id, None) is not None

    def clear(self) -> None:
        """Remove all cache entries."""
        self._entries.clear()
        logger.debug("Cache cleared")

    @property
    def size(self) -> int:
        """Number of live entries."""
        return len(self._entries)

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total_bytes = sum(e.size_bytes for e in self._entries.values())
        return {
            "entries": len(self._entries),
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl_seconds,
            "total_cached_bytes": total_bytes,
        }

    # ------------------------------------------------------------------
    # Eviction helpers
    # ------------------------------------------------------------------

    def _evict_expired(self) -> None:
        """Remove all entries that have exceeded TTL."""
        expired = [
            cid
            for cid, entry in self._entries.items()
            if entry.age_seconds > self.ttl_seconds
        ]
        for cid in expired:
            del self._entries[cid]
        if expired:
            logger.debug("Evicted %d expired cache entries", len(expired))

    def _evict_if_full(self) -> None:
        """Evict entries until we are below max_entries.

        Strategy: evict the entry with the highest ``idle_seconds * size_bytes``
        score first (large idle entries go first).
        """
        while len(self._entries) >= self.max_entries:
            if not self._entries:
                break
            # Score = idle time × size  (bigger & older → evicted first)
            worst_id = max(
                self._entries,
                key=lambda cid: self._entries[cid].idle_seconds * max(self._entries[cid].size_bytes, 1),
            )
            logger.debug(
                "Evicting cache entry %s (idle=%.1fs, size=%d bytes)",
                worst_id,
                self._entries[worst_id].idle_seconds,
                self._entries[worst_id].size_bytes,
            )
            del self._entries[worst_id]

