import time
from unittest.mock import MagicMock

from core.cache import CachedEmbedder, TTLCache, normalize_key


def test_normalize_key_unifies_arabic_variants_and_punctuation():
    assert normalize_key("ما هي شروط العقد؟") == normalize_key("ما هى شروط  العقد ؟")
    assert normalize_key("What are the CONDITIONS?") == normalize_key("what are the conditions")


def test_hit_and_miss_counters():
    cache: TTLCache[int] = TTLCache(max_entries=4, ttl_seconds=60)
    assert cache.get("a") is None
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert (cache.hits, cache.misses) == (1, 1)
    assert cache.hit_rate == 0.5


def test_lru_eviction_drops_least_recently_used():
    cache: TTLCache[int] = TTLCache(max_entries=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # refresh 'a'
    cache.set("c", 3)  # evicts 'b'
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_ttl_expiry():
    cache: TTLCache[int] = TTLCache(max_entries=2, ttl_seconds=0.05)
    cache.set("a", 1)
    time.sleep(0.1)
    assert cache.get("a") is None


def test_cached_embedder_calls_inner_once_for_equivalent_queries():
    inner = MagicMock()
    inner.embed_query.return_value = [0.1, 0.2]
    events: list[bool] = []
    embedder = CachedEmbedder(inner, TTLCache(), on_event=events.append)

    v1 = embedder.embed_query("ما هي شروط العقد؟")
    v2 = embedder.embed_query("ما هى شروط العقد")
    assert v1 == v2 == [0.1, 0.2]
    assert inner.embed_query.call_count == 1
    assert events == [False, True]


def test_cached_embedder_does_not_cache_documents():
    inner = MagicMock()
    inner.embed_documents.return_value = [[1.0]]
    embedder = CachedEmbedder(inner, TTLCache())
    embedder.embed_documents(["x"])
    embedder.embed_documents(["x"])
    assert inner.embed_documents.call_count == 2
