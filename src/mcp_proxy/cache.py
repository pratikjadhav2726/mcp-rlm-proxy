"""
Smart caching module for MCP-RLM Proxy.

Provides TTL-based, size-aware caching with UUID-based keys for
storing large tool responses that can be explored incrementally
by agents via proxy tools.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from mcp.types import Content, TextContent

from mcp_proxy.logging_config import get_logger

logger = get_logger(__name__)


@runtime_checkable
class AsyncCacheManager(Protocol):
    async def put(
        self,
        content: List[Content],
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        ...

    async def get(self, cache_id: str) -> Optional[List[Content]]:
        ...

    async def get_entry(self, cache_id: str) -> Optional["CacheEntry"]:
        ...

    async def remove(self, cache_id: str) -> bool:
        ...

    async def clear(self, agent_id: Optional[str] = None) -> None:
        ...

    async def size(self, agent_id: Optional[str] = None) -> int:
        ...

    async def stats(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        ...


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
        self._lock = asyncio.Lock()  # Async lock for thread-safe access

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def put(self, content: List[Content], tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Store content and return a short UUID-based cache_id.

        Args:
            content: MCP Content list to cache.
            tool_name: Fully-qualified tool name (e.g. ``filesystem_read_file``).
            arguments: Original arguments used for the tool call.

        Returns:
            A short cache ID string (first 12 chars of UUID4).
        """
        async with self._lock:
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

    async def get(self, cache_id: str) -> Optional[List[Content]]:
        """
        Retrieve cached content by cache_id.

        Returns ``None`` if the entry has expired or does not exist.
        """
        async with self._lock:
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

    async def get_entry(self, cache_id: str) -> Optional[CacheEntry]:
        """
        Retrieve the full CacheEntry (including metadata) by cache_id.

        Returns ``None`` if expired or missing.
        """
        async with self._lock:
            entry = self._entries.get(cache_id)
            if entry is None:
                return None

            if entry.age_seconds > self.ttl_seconds:
                del self._entries[cache_id]
                return None

            entry.access_count += 1
            entry.last_accessed_at = time.monotonic()
            return entry

    async def remove(self, cache_id: str) -> bool:
        """Remove a specific entry. Returns True if it existed."""
        async with self._lock:
            return self._entries.pop(cache_id, None) is not None

    async def clear(self, agent_id: Optional[str] = None) -> None:
        """Remove all cache entries. `agent_id` is ignored for simple caches."""
        async with self._lock:
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

    async def size_async(self) -> int:
        """Thread-safe async version of size property."""
        async with self._lock:
            return len(self._entries)

    async def stats_async(self) -> Dict[str, Any]:
        """Thread-safe async version of stats method."""
        async with self._lock:
            total_bytes = sum(e.size_bytes for e in self._entries.values())
            return {
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "total_cached_bytes": total_bytes,
            }

    async def size(self, agent_id: Optional[str] = None) -> int:
        """Async size method to satisfy AsyncCacheManager protocol."""
        return await self.size_async()

    async def stats(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Async stats method to satisfy AsyncCacheManager protocol."""
        return await self.stats_async()


# ---------------------------------------------------------------------------
# Agent-aware cache manager
# ---------------------------------------------------------------------------

@dataclass
class AgentCacheInfo:
    """Metadata for an agent's cache."""
    agent_id: str
    cache: SmartCacheManager
    last_accessed_at: float
    entry_count: int = 0
    total_memory_bytes: int = 0


class AgentAwareCacheManager:
    """
    Cache manager with per-agent isolation and memory limits.
    
    Provides:
    - Per-agent cache quotas (entries and memory)
    - Agent isolation (one agent's cache doesn't affect others)
    - Memory-aware eviction
    - LRU agent eviction when max agents reached
    - Thread-safe operations
    """

    def __init__(
        self,
        max_entries_per_agent: int = 20,
        max_memory_per_agent: int = 100 * 1024 * 1024,  # 100MB per agent
        ttl_seconds: int = 300,
        max_total_agents: int = 1000,
        enable_agent_isolation: bool = True,
    ):
        """
        Initialize agent-aware cache manager.

        Args:
            max_entries_per_agent: Maximum cache entries per agent.
            max_memory_per_agent: Maximum memory (bytes) per agent cache.
            ttl_seconds: Time-to-live for cache entries.
            max_total_agents: Maximum number of concurrent agent caches.
            enable_agent_isolation: If False, all agents share one cache (backward compat).
        """
        self.max_entries_per_agent = max_entries_per_agent
        self.max_memory_per_agent = max_memory_per_agent
        self.ttl_seconds = ttl_seconds
        self.max_total_agents = max_total_agents
        self.enable_agent_isolation = enable_agent_isolation

        # Agent-specific caches
        self._agent_caches: Dict[str, AgentCacheInfo] = {}
        self._global_lock = asyncio.Lock()
        
        # Fallback shared cache for backward compatibility
        if not enable_agent_isolation:
            self._shared_cache = SmartCacheManager(
                max_entries=max_entries_per_agent * 10,  # Scale up for shared
                ttl_seconds=ttl_seconds,
            )

    async def put(
        self,
        content: List[Content],
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: Optional[str] = None,
    ) -> str:
        """
        Store content with agent isolation.

        Args:
            content: MCP Content list to cache.
            tool_name: Fully-qualified tool name.
            arguments: Original arguments used for the tool call.
            agent_id: Optional agent identifier. If None, uses "default".

        Returns:
            A cache ID string (prefixed with agent_id if isolation enabled).
        """
        if not self.enable_agent_isolation:
            # Backward compatibility: use shared cache
            cache_id = await self._shared_cache.put(content, tool_name, arguments)
            return cache_id

        if agent_id is None:
            agent_id = "default"

        # Calculate content size
        size_bytes = sum(
            len(item.text) for item in content if isinstance(item, TextContent)
        )

        # Check if entry would exceed agent's memory limit
        if size_bytes > self.max_memory_per_agent:
            logger.warning(
                "Cache entry too large (%d bytes) for agent %s (limit: %d bytes). "
                "Entry will not be cached.",
                size_bytes,
                agent_id,
                self.max_memory_per_agent,
            )
            # Return a cache_id anyway, but it won't be stored
            return f"{agent_id}:{uuid.uuid4().hex[:12]}"

        # Get or create agent-specific cache
        async with self._global_lock:
            agent_info = self._agent_caches.get(agent_id)
            
            if agent_info is None:
                # Check if we need to evict an agent
                if len(self._agent_caches) >= self.max_total_agents:
                    await self._evict_oldest_agent()
                
                # Create new agent cache
                agent_cache = SmartCacheManager(
                    max_entries=self.max_entries_per_agent,
                    ttl_seconds=self.ttl_seconds,
                )
                agent_info = AgentCacheInfo(
                    agent_id=agent_id,
                    cache=agent_cache,
                    last_accessed_at=time.monotonic(),
                )
                self._agent_caches[agent_id] = agent_info
                logger.debug("Created cache for agent: %s", agent_id)
            
            agent_info.last_accessed_at = time.monotonic()

        # Check memory limit for this agent
        async with agent_info.cache._lock:
            current_memory = sum(
                e.size_bytes for e in agent_info.cache._entries.values()
            )
            
            # Evict entries until we have space
            while (
                current_memory + size_bytes > self.max_memory_per_agent
                or len(agent_info.cache._entries) >= self.max_entries_per_agent
            ):
                if not agent_info.cache._entries:
                    break
                await self._evict_one_from_agent(agent_info)
                current_memory = sum(
                    e.size_bytes for e in agent_info.cache._entries.values()
                )

        # Store in agent's cache
        cache_id = await agent_info.cache.put(content, tool_name, arguments)
        
        # Update agent metadata
        async with self._global_lock:
            agent_info.entry_count = await agent_info.cache.size_async()
            agent_info.total_memory_bytes = sum(
                e.size_bytes for e in agent_info.cache._entries.values()
            )

        # Return prefixed cache ID for identification
        return f"{agent_id}:{cache_id}"

    async def get(self, cache_id: str) -> Optional[List[Content]]:
        """
        Retrieve cached content with agent isolation.

        Args:
            cache_id: Cache ID (may be prefixed with agent_id if isolation enabled).

        Returns:
            Cached content or None if not found/expired.
        """
        if not self.enable_agent_isolation:
            # Backward compatibility
            return await self._shared_cache.get(cache_id)

        # Parse agent_id from cache_id
        if ":" not in cache_id:
            # Legacy format without agent prefix
            logger.debug("Cache ID without agent prefix, trying default agent")
            agent_id = "default"
            actual_cache_id = cache_id
        else:
            agent_id, actual_cache_id = cache_id.split(":", 1)

        # Get agent cache
        async with self._global_lock:
            agent_info = self._agent_caches.get(agent_id)
            if agent_info is None:
                logger.debug("Agent cache not found: %s", agent_id)
                return None
            agent_info.last_accessed_at = time.monotonic()

        # Retrieve from agent's cache
        result = await agent_info.cache.get(actual_cache_id)
        return result

    async def get_entry(self, cache_id: str) -> Optional[CacheEntry]:
        """Retrieve full CacheEntry with agent isolation."""
        if not self.enable_agent_isolation:
            return await self._shared_cache.get_entry(cache_id)

        if ":" not in cache_id:
            agent_id = "default"
            actual_cache_id = cache_id
        else:
            agent_id, actual_cache_id = cache_id.split(":", 1)

        async with self._global_lock:
            agent_info = self._agent_caches.get(agent_id)
            if agent_info is None:
                return None

        return await agent_info.cache.get_entry(actual_cache_id)

    async def remove(self, cache_id: str) -> bool:
        """Remove a specific entry with agent isolation."""
        if not self.enable_agent_isolation:
            return await self._shared_cache.remove(cache_id)

        if ":" not in cache_id:
            agent_id = "default"
            actual_cache_id = cache_id
        else:
            agent_id, actual_cache_id = cache_id.split(":", 1)

        async with self._global_lock:
            agent_info = self._agent_caches.get(agent_id)
            if agent_info is None:
                return False

        return await agent_info.cache.remove(actual_cache_id)

    async def clear(self, agent_id: Optional[str] = None) -> None:
        """
        Clear cache entries.

        Args:
            agent_id: If provided, clear only this agent's cache. Otherwise clear all.
        """
        if not self.enable_agent_isolation:
            await self._shared_cache.clear()
            return

        async with self._global_lock:
            if agent_id:
                agent_info = self._agent_caches.get(agent_id)
                if agent_info:
                    await agent_info.cache.clear()
                    del self._agent_caches[agent_id]
            else:
                # Clear all agent caches
                for agent_info in self._agent_caches.values():
                    await agent_info.cache.clear()
                self._agent_caches.clear()
            logger.debug("Cache cleared for agent: %s", agent_id or "all")

    async def size(self, agent_id: Optional[str] = None) -> int:
        """Get cache size for agent or total."""
        if not self.enable_agent_isolation:
            return await self._shared_cache.size_async()

        async with self._global_lock:
            if agent_id:
                agent_info = self._agent_caches.get(agent_id)
                if agent_info:
                    return await agent_info.cache.size_async()
                return 0
            else:
                return sum(
                    await agent_info.cache.size_async()
                    for agent_info in self._agent_caches.values()
                )

    async def stats(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get cache statistics for agent or aggregate."""
        if not self.enable_agent_isolation:
            return await self._shared_cache.stats_async()

        async with self._global_lock:
            if agent_id:
                agent_info = self._agent_caches.get(agent_id)
                if agent_info:
                    stats = await agent_info.cache.stats_async()
                    stats["agent_id"] = agent_id
                    stats["last_accessed_at"] = agent_info.last_accessed_at
                    return stats
                return {"agent_id": agent_id, "entries": 0}

            # Aggregate stats
            total_entries = 0
            total_bytes = 0
            agent_stats = []
            
            for agent_info in self._agent_caches.values():
                stats = await agent_info.cache.stats_async()
                total_entries += stats["entries"]
                total_bytes += stats["total_cached_bytes"]
                agent_stats.append({
                    "agent_id": agent_info.agent_id,
                    "entries": stats["entries"],
                    "memory_bytes": stats["total_cached_bytes"],
                    "last_accessed_at": agent_info.last_accessed_at,
                })

            return {
                "total_agents": len(self._agent_caches),
                "total_entries": total_entries,
                "total_cached_bytes": total_bytes,
                "max_agents": self.max_total_agents,
                "max_entries_per_agent": self.max_entries_per_agent,
                "max_memory_per_agent": self.max_memory_per_agent,
                "agents": agent_stats,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _evict_oldest_agent(self) -> None:
        """Evict the agent cache with oldest last access."""
        if not self._agent_caches:
            return

        # Find oldest agent
        oldest_agent_id = min(
            self._agent_caches.keys(),
            key=lambda aid: self._agent_caches[aid].last_accessed_at,
        )

        agent_info = self._agent_caches[oldest_agent_id]
        logger.info(
            "Evicting agent cache: %s (last accessed: %.1fs ago, entries: %d)",
            oldest_agent_id,
            time.monotonic() - agent_info.last_accessed_at,
            await agent_info.cache.size_async(),
        )

        await agent_info.cache.clear()
        del self._agent_caches[oldest_agent_id]

    async def _evict_one_from_agent(self, agent_info: AgentCacheInfo) -> None:
        """Evict one entry from an agent's cache using smart eviction."""
        if not agent_info.cache._entries:
            return

        # Smart eviction: prioritize large, idle, rarely-accessed entries
        worst_id = max(
            agent_info.cache._entries,
            key=lambda cid: (
                agent_info.cache._entries[cid].idle_seconds
                * agent_info.cache._entries[cid].size_bytes
                / max(agent_info.cache._entries[cid].access_count, 1)
            ),
        )

        entry = agent_info.cache._entries[worst_id]
        logger.debug(
            "Evicting entry %s from agent %s (idle=%.1fs, size=%d bytes, accesses=%d)",
            worst_id,
            agent_info.agent_id,
            entry.idle_seconds,
            entry.size_bytes,
            entry.access_count,
        )
        del agent_info.cache._entries[worst_id]

