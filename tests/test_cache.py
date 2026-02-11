"""
Unit tests for SmartCacheManager (async).
"""

import time

import pytest
from mcp.types import TextContent

from mcp_proxy.cache import SmartCacheManager


@pytest.mark.asyncio
async def test_put_and_get():
    cache = SmartCacheManager(max_entries=10, ttl_seconds=60)
    content = [TextContent(type="text", text="hello world")]
    cache_id = await cache.put(content, "test_tool", {"arg": "val"})

    assert isinstance(cache_id, str)
    assert len(cache_id) == 12

    retrieved = await cache.get(cache_id)
    assert retrieved is not None
    assert retrieved[0].text == "hello world"


@pytest.mark.asyncio
async def test_get_missing_returns_none():
    cache = SmartCacheManager()
    assert await cache.get("nonexistent") is None


@pytest.mark.asyncio
async def test_ttl_expiration():
    cache = SmartCacheManager(max_entries=10, ttl_seconds=0)  # 0s TTL
    content = [TextContent(type="text", text="ephemeral")]
    cache_id = await cache.put(content, "t", {})
    # Sleep long enough to exceed 0s TTL (Windows timer resolution ~16ms)
    time.sleep(0.05)
    assert await cache.get(cache_id) is None


@pytest.mark.asyncio
async def test_lru_eviction():
    cache = SmartCacheManager(max_entries=2, ttl_seconds=300)
    id1 = await cache.put([TextContent(type="text", text="a")], "t1", {})
    id2 = await cache.put([TextContent(type="text", text="b")], "t2", {})

    # Let some time pass so idle_seconds diverge after the access
    time.sleep(0.05)

    # Access id1 to keep it fresh (resets last_accessed_at)
    await cache.get(id1)

    # This should evict id2 (higher idle time × size score)
    id3 = await cache.put([TextContent(type="text", text="c")], "t3", {})

    assert await cache.get(id1) is not None
    assert await cache.get(id3) is not None
    # id2 was evicted
    assert await cache.get(id2) is None


@pytest.mark.asyncio
async def test_remove():
    cache = SmartCacheManager()
    cid = await cache.put([TextContent(type="text", text="x")], "t", {})
    assert await cache.remove(cid) is True
    assert await cache.get(cid) is None
    assert await cache.remove(cid) is False


@pytest.mark.asyncio
async def test_clear():
    cache = SmartCacheManager()
    await cache.put([TextContent(type="text", text="a")], "t1", {})
    await cache.put([TextContent(type="text", text="b")], "t2", {})
    assert cache.size == 2
    await cache.clear()
    assert cache.size == 0


@pytest.mark.asyncio
async def test_stats():
    cache = SmartCacheManager(max_entries=10, ttl_seconds=60)
    await cache.put([TextContent(type="text", text="a" * 100)], "t1", {})
    stats = cache.stats()
    assert stats["entries"] == 1
    assert stats["max_entries"] == 10
    assert stats["ttl_seconds"] == 60
    assert stats["total_cached_bytes"] == 100


@pytest.mark.asyncio
async def test_get_entry_returns_metadata():
    cache = SmartCacheManager()
    cid = await cache.put([TextContent(type="text", text="data")], "my_tool", {"k": "v"})
    entry = await cache.get_entry(cid)
    assert entry is not None
    assert entry.tool_name == "my_tool"
    assert entry.arguments == {"k": "v"}
    assert entry.size_bytes == 4
    assert entry.access_count == 1


@pytest.mark.asyncio
async def test_unique_ids():
    cache = SmartCacheManager()
    ids = set()
    for i in range(100):
        cid = await cache.put([TextContent(type="text", text=str(i))], "t", {})
        ids.add(cid)
    assert len(ids) == 100  # all unique