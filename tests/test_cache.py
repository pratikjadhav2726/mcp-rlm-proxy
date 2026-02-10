"""
Unit tests for SmartCacheManager.
"""

import time
import pytest
from mcp.types import TextContent

from mcp_proxy.cache import SmartCacheManager


class TestSmartCacheManager:
    """Tests for the new UUID-based, TTL-aware cache."""

    def test_put_and_get(self):
        cache = SmartCacheManager(max_entries=10, ttl_seconds=60)
        content = [TextContent(type="text", text="hello world")]
        cache_id = cache.put(content, "test_tool", {"arg": "val"})

        assert isinstance(cache_id, str)
        assert len(cache_id) == 12

        retrieved = cache.get(cache_id)
        assert retrieved is not None
        assert retrieved[0].text == "hello world"

    def test_get_missing_returns_none(self):
        cache = SmartCacheManager()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        cache = SmartCacheManager(max_entries=10, ttl_seconds=0)  # 0s TTL
        content = [TextContent(type="text", text="ephemeral")]
        cache_id = cache.put(content, "t", {})
        # Sleep long enough to exceed 0s TTL (Windows timer resolution ~16ms)
        time.sleep(0.05)
        assert cache.get(cache_id) is None

    def test_lru_eviction(self):
        cache = SmartCacheManager(max_entries=2, ttl_seconds=300)
        id1 = cache.put([TextContent(type="text", text="a")], "t1", {})
        id2 = cache.put([TextContent(type="text", text="b")], "t2", {})

        # Let some time pass so idle_seconds diverge after the access
        time.sleep(0.05)

        # Access id1 to keep it fresh (resets last_accessed_at)
        cache.get(id1)

        # This should evict id2 (higher idle time × size score)
        id3 = cache.put([TextContent(type="text", text="c")], "t3", {})

        assert cache.get(id1) is not None
        assert cache.get(id3) is not None
        # id2 was evicted
        assert cache.get(id2) is None

    def test_remove(self):
        cache = SmartCacheManager()
        cid = cache.put([TextContent(type="text", text="x")], "t", {})
        assert cache.remove(cid) is True
        assert cache.get(cid) is None
        assert cache.remove(cid) is False

    def test_clear(self):
        cache = SmartCacheManager()
        cache.put([TextContent(type="text", text="a")], "t1", {})
        cache.put([TextContent(type="text", text="b")], "t2", {})
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_stats(self):
        cache = SmartCacheManager(max_entries=10, ttl_seconds=60)
        cache.put([TextContent(type="text", text="a" * 100)], "t1", {})
        stats = cache.stats()
        assert stats["entries"] == 1
        assert stats["max_entries"] == 10
        assert stats["ttl_seconds"] == 60
        assert stats["total_cached_bytes"] == 100

    def test_get_entry_returns_metadata(self):
        cache = SmartCacheManager()
        cid = cache.put([TextContent(type="text", text="data")], "my_tool", {"k": "v"})
        entry = cache.get_entry(cid)
        assert entry is not None
        assert entry.tool_name == "my_tool"
        assert entry.arguments == {"k": "v"}
        assert entry.size_bytes == 4
        assert entry.access_count == 1

    def test_unique_ids(self):
        cache = SmartCacheManager()
        ids = set()
        for i in range(100):
            cid = cache.put([TextContent(type="text", text=str(i))], "t", {})
            ids.add(cid)
        assert len(ids) == 100  # all unique

