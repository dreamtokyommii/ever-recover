"""Intelligent caching for disk operations."""

import logging
import threading
import time
from typing import Dict, Any, Optional, Tuple, List, Callable
from collections import OrderedDict
from dataclasses import dataclass, field
import weakref
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: bytes
    size: int
    created_at: float
    last_accessed: float
    access_count: int = 0
    priority: int = 0
    
    def touch(self):
        """Update access time."""
        self.last_accessed = time.time()
        self.access_count += 1


class LRUCache:
    """
    Least Recently Used cache with size limits.
    
    Automatically evicts oldest entries when capacity is exceeded.
    """
    
    def __init__(
        self,
        max_size_bytes: int = 100 * 1024 * 1024,  # 100MB default
        ttl_seconds: int = 300,  # 5 minutes
    ):
        """
        Initialize LRU cache.
        
        Args:
            max_size_bytes: Maximum cache size in bytes
            ttl_seconds: Time-to-live for entries
        """
        self.max_size_bytes = max_size_bytes
        self.ttl_seconds = ttl_seconds
        
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._current_size = 0
        self._lock = threading.RLock()
        
        self._hits = 0
        self._misses = 0
        
        logger.info(f"LRU cache initialized: {max_size_bytes / (1024*1024):.1f}MB, TTL={ttl_seconds}s")
    
    def get(self, key: str) -> Optional[bytes]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        with self._lock:
            # Check if entry exists
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # Check TTL
            if time.time() - entry.created_at > self.ttl_seconds:
                self._remove(key)
                self._misses += 1
                return None
            
            # Update access
            entry.touch()
            self._cache.move_to_end(key)
            
            self._hits += 1
            return entry.value
    
    def put(self, key: str, value: bytes, priority: int = 0) -> None:
        """
        Put value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            priority: Entry priority (higher = less likely to evict)
        """
        entry_size = len(value)
        
        with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                self._remove(key)
            
            # Evict if necessary
            while self._current_size + entry_size > self.max_size_bytes and self._cache:
                self._evict_oldest()
            
            # Create entry
            now = time.time()
            entry = CacheEntry(
                key=key,
                value=value,
                size=entry_size,
                created_at=now,
                last_accessed=now,
                priority=priority,
            )
            
            # Add to cache
            self._cache[key] = entry
            self._current_size += entry_size
            
            logger.debug(f"Cached {key}: {entry_size} bytes")
    
    def remove(self, key: str) -> bool:
        """Remove entry from cache."""
        with self._lock:
            return self._remove(key)
    
    def _remove(self, key: str) -> bool:
        """Internal remove."""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._current_size -= entry.size
            return True
        return False
    
    def _evict_oldest(self) -> None:
        """Evict oldest entry."""
        if self._cache:
            key, entry = self._cache.popitem(last=False)
            self._current_size -= entry.size
            logger.debug(f"Evicted {key}: {entry.size} bytes")
    
    def clear(self) -> None:
        """Clear cache."""
        with self._lock:
            self._cache.clear()
            self._current_size = 0
            logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0
            
            return {
                'entries': len(self._cache),
                'current_size_bytes': self._current_size,
                'max_size_bytes': self.max_size_bytes,
                'utilization_percent': (self._current_size / self.max_size_bytes * 100),
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate_percent': hit_rate,
            }


class ChunkCache:
    """
    Specialized cache for disk chunks.
    
    Optimized for sequential and random access patterns.
    """
    
    def __init__(
        self,
        max_size_mb: int = 256,
        chunk_size: int = 1024 * 1024,  # 1MB chunks
        prefetch_count: int = 4,
    ):
        """
        Initialize chunk cache.
        
        Args:
            max_size_mb: Maximum cache size in MB
            chunk_size: Size of each chunk
            prefetch_count: Number of chunks to prefetch
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.chunk_size = chunk_size
        self.prefetch_count = prefetch_count
        
        self._cache = LRUCache(max_size_bytes=self.max_size_bytes)
        self._lock = threading.Lock()
        
        self._last_offset = 0
        self._access_pattern = 'random'  # 'sequential' or 'random'
        self._sequential_count = 0
        
        logger.info(f"Chunk cache initialized: {max_size_mb}MB, chunk={chunk_size/1024:.0f}KB")
    
    def get_chunk(self, disk_reader, offset: int, size: int) -> bytes:
        """
        Get chunk from disk with caching.
        
        Args:
            disk_reader: Disk reader interface
            offset: Offset in disk
            size: Size to read
            
        Returns:
            Data chunk
        """
        # Generate cache key
        cache_key = f"{offset}:{size}"
        
        # Try cache first
        data = self._cache.get(cache_key)
        if data:
            logger.debug(f"Cache hit: {offset}:{size}")
            return data
        
        # Read from disk
        data = disk_reader.read(offset, size)
        
        # Cache the chunk
        self._cache.put(cache_key, data)
        
        # Detect access pattern
        with self._lock:
            if offset > self._last_offset and offset - self._last_offset <= self.chunk_size * 2:
                self._sequential_count += 1
                if self._sequential_count >= 3:
                    self._access_pattern = 'sequential'
            else:
                self._sequential_count = 0
                self._access_pattern = 'random'
            
            self._last_offset = offset
        
        # Prefetch if sequential
        if self._access_pattern == 'sequential':
            self._prefetch(disk_reader, offset, size)
        
        return data
    
    def _prefetch(self, disk_reader, current_offset: int, size: int) -> None:
        """Prefetch next chunks."""
        for i in range(1, self.prefetch_count + 1):
            next_offset = current_offset + (i * self.chunk_size)
            cache_key = f"{next_offset}:{size}"
            
            # Skip if already cached
            if self._cache.get(cache_key):
                continue
            
            # Try to prefetch
            try:
                data = disk_reader.read(next_offset, size)
                self._cache.put(cache_key, data, priority=1)  # Lower priority
                logger.debug(f"Prefetched: {next_offset}:{size}")
            except Exception as e:
                logger.debug(f"Prefetch failed: {e}")
                break
    
    def get_stats(self) -> Dict[str, Any]:
        """Get chunk cache statistics."""
        cache_stats = self._cache.get_stats()
        cache_stats['access_pattern'] = self._access_pattern
        return cache_stats


class MemoryManager:
    """
    Memory management for large file operations.
    
    Features:
    - Streaming large files
    - Memory pressure monitoring
    - Automatic garbage collection
    """
    
    def __init__(
        self,
        max_memory_mb: int = 512,
        gc_threshold: float = 0.8,
    ):
        """
        Initialize memory manager.
        
        Args:
            max_memory_mb: Maximum memory usage
            gc_threshold: GC trigger threshold (0-1)
        """
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.gc_threshold = gc_threshold
        
        self._current_usage = 0
        self._lock = threading.Lock()
        self._tracked_objects: Dict[int, Tuple[weakref.ref, int]] = {}
        
        logger.info(f"Memory manager initialized: {max_memory_mb}MB, GC threshold={gc_threshold:.0%}")
    
    def track(self, obj: Any, size: int) -> int:
        """Track memory usage."""
        obj_id = id(obj)
        
        with self._lock:
            self._tracked_objects[obj_id] = (weakref.ref(obj, lambda ref: self._on_object_deleted(obj_id)), size)
            self._current_usage += size
        
        return obj_id
    
    def _on_object_deleted(self, obj_id: int) -> None:
        """Called when tracked object is deleted."""
        with self._lock:
            if obj_id in self._tracked_objects:
                _, size = self._tracked_objects.pop(obj_id)
                self._current_usage -= size
    
    def get_usage(self) -> Tuple[int, int, float]:
        """Get memory usage."""
        with self._lock:
            usage_percent = (self._current_usage / self.max_memory_bytes * 100)
            return self._current_usage, self.max_memory_bytes, usage_percent
    
    def should_gc(self) -> bool:
        """Check if GC should run."""
        _, _, usage_percent = self.get_usage()
        return usage_percent >= self.gc_threshold * 100
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        current, max_mem, percent = self.get_usage()
        return {
            'current_bytes': current,
            'max_bytes': max_mem,
            'usage_percent': percent,
            'tracked_objects': len(self._tracked_objects),
            'gc_recommended': self.should_gc(),
        }