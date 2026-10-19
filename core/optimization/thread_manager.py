"""Thread pool management for recovery operations."""

import threading
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional, Callable, Any, List

logger = logging.getLogger(__name__)


class ThreadManager:
    """Manages thread pool for recovery operations."""
    
    def __init__(self, max_workers: int = 4):
        """Initialize thread manager."""
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._active_tasks: List[Future] = []
        self._lock = threading.Lock()
        logger.info(f"Thread manager initialized with {max_workers} workers")
    
    def submit(self, func: Callable, *args, **kwargs) -> Future:
        """Submit a task to the thread pool."""
        with self._lock:
            future = self.executor.submit(func, *args, **kwargs)
            self._active_tasks.append(future)
        return future
    
    def wait_all(self, timeout: Optional[float] = None) -> bool:
        """Wait for all tasks to complete."""
        with self._lock:
            tasks = self._active_tasks[:]
        
        for future in tasks:
            try:
                future.result(timeout=timeout)
            except Exception as e:
                logger.error(f"Task error: {e}")
        
        return True
    
    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the thread pool."""
        self.executor.shutdown(wait=wait)
        logger.info("Thread pool shutdown")
    
    def get_active_count(self) -> int:
        """Get number of active tasks."""
        with self._lock:
            return len([f for f in self._active_tasks if not f.done()])