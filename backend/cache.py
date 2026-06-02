import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, List, Callable
import logging

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "data" / ".cache"

def _ensure_cache_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "embeddings").mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "llm_responses").mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "pagerank").mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "stats").mkdir(parents=True, exist_ok=True)

_ensure_cache_dirs()


class InMemoryCache:
    """LRU-based in-memory cache with optional TTL eviction."""

    def __init__(self, maxsize: int = 1000, ttl: int = 60):
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._order: List[str] = []

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if self._ttl > 0 and time.time() - ts > self._ttl:
            del self._cache[key]
            if key in self._order:
                self._order.remove(key)
            return None
        # Move to end (most recently used)
        if key in self._order:
            self._order.remove(key)
            self._order.append(key)
        return value

    def set(self, key: str, value: Any):
        if key in self._cache:
            self._cache[key] = (time.time(), value)
            # Move to end (most recently used)
            if key in self._order:
                self._order.remove(key)
            self._order.append(key)
            return
        if len(self._order) >= self._maxsize:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[key] = (time.time(), value)
        self._order.append(key)

    def invalidate(self, key: str):
        self._cache.pop(key, None)
        if key in self._order:
            self._order.remove(key)

    def clear(self):
        self._cache.clear()
        self._order.clear()

    def __len__(self):
        return len(self._cache)


class DiskCache:
    """Two-tier cache: in-memory L1 (fast) + disk L2 (persistent).
    Keys are SHA-256 hashed for safe filenames.
    """

    def __init__(self, cache_dir: Path, l1_size: int = 500, l1_ttl: int = 300, l2_ttl: int = 86400):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._l1 = InMemoryCache(maxsize=l1_size, ttl=l1_ttl)
        self._l2_ttl = l2_ttl

    def _key_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()
        return self._cache_dir / f"{h}.json"

    def get(self, key: str) -> Optional[Any]:
        val = self._l1.get(key)
        if val is not None:
            return val
        path = self._key_path(key)
        if not path.exists():
            return None
        if self._l2_ttl > 0:
            age = time.time() - path.stat().st_mtime
            if age > self._l2_ttl:
                try:
                    path.unlink()
                except OSError:
                    pass
                return None
        try:
            with open(path, "r") as f:
                val = json.load(f)
            self._l1.set(key, val)
            return val
        except Exception:
            return None

    def set(self, key: str, value: Any):
        self._l1.set(key, value)
        path = self._key_path(key)
        try:
            with open(path, "w") as f:
                json.dump(value, f, default=str)
        except Exception as e:
            logger.warning(f"Disk cache write failed for {path.name}: {e}")

    def invalidate(self, key: str):
        self._l1.invalidate(key)
        path = self._key_path(key)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    def clear(self):
        self._l1.clear()
        count = 0
        for f in self._cache_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
        logger.info(f"Cleared {count} disk cache entries from {self._cache_dir.name}")


_embedding_cache: Optional[DiskCache] = None
_llm_cache: Optional[DiskCache] = None
_pagerank_cache: Optional[DiskCache] = None
_stats_cache: Optional[InMemoryCache] = None


def get_embedding_cache() -> DiskCache:
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = DiskCache(
            cache_dir=CACHE_DIR / "embeddings",
            l1_size=1000,
            l1_ttl=3600,
            l2_ttl=86400 * 7,
        )
    return _embedding_cache


def get_llm_cache() -> DiskCache:
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = DiskCache(
            cache_dir=CACHE_DIR / "llm_responses",
            l1_size=200,
            l1_ttl=1800,
            l2_ttl=86400 * 30,
        )
    return _llm_cache


def get_pagerank_cache() -> DiskCache:
    global _pagerank_cache
    if _pagerank_cache is None:
        _pagerank_cache = DiskCache(
            cache_dir=CACHE_DIR / "pagerank",
            l1_size=50,
            l1_ttl=60,
            l2_ttl=3600,
        )
    return _pagerank_cache


def get_stats_cache() -> InMemoryCache:
    global _stats_cache
    if _stats_cache is None:
        _stats_cache = InMemoryCache(maxsize=20, ttl=5)
    return _stats_cache


def cached_embedding(text: str) -> List[float]:
    """Compute or retrieve cached embedding for a text string.
    Cache key = SHA-256 of text. Deterministic for same input.
    """
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cache = get_embedding_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached
    return None


def store_embedding(text: str, vector: List[float]):
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    get_embedding_cache().set(key, vector)


def cached_llm_response(cache_key: str) -> Optional[Dict[str, Any]]:
    return get_llm_cache().get(cache_key)


def store_llm_response(cache_key: str, response: Dict[str, Any]):
    get_llm_cache().set(cache_key, response)


def clear_all_caches():
    """Invalidate all caches. Used after document ingestion or model retrain."""
    for name in ["embeddings", "llm_responses", "pagerank", "stats"]:
        d = CACHE_DIR / name
        if d.exists():
            count = 0
            for f in d.glob("*.json"):
                try:
                    f.unlink()
                    count += 1
                except OSError:
                    pass
            logger.info(f"Cleared {count} cache files from {name}")
    global _embedding_cache, _llm_cache, _pagerank_cache, _stats_cache
    _embedding_cache = None
    _llm_cache = None
    _pagerank_cache = None
    _stats_cache = None


def memoize(maxsize: int = 128, ttl: int = 60):
    """Decorator that caches function return values in-memory with LRU + TTL."""
    caches: Dict[str, InMemoryCache] = {}

    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{hash(repr(args))}:{hash(repr(kwargs))}"
            if func.__name__ not in caches:
                caches[func.__name__] = InMemoryCache(maxsize=maxsize, ttl=ttl)
            cache = caches[func.__name__]
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result
        return wrapper
    return decorator
