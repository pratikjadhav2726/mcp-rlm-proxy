"""
Executor manager for offloading CPU-bound operations to thread pool.

Prevents blocking the event loop during intensive computations like
BM25 ranking, fuzzy matching, and JSON parsing.
"""

import asyncio
import concurrent.futures
import os
from typing import Any, Callable, Optional

from mcp_proxy.logging_config import get_logger

logger = get_logger(__name__)


class ExecutorManager:
    """Manages thread pool executor for CPU-bound operations."""

    def __init__(self, max_workers: Optional[int] = None):
        """
        Initialize executor manager.

        Args:
            max_workers: Number of worker threads. Defaults to min(32, CPU count + 4)
        """
        if max_workers is None:
            max_workers = min(32, (os.cpu_count() or 1) + 4)

        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="mcp-cpu-worker"
        )
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        logger.info("ExecutorManager initialized with %d workers", max_workers)

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop for executor operations."""
        self._loop = loop

    async def run_cpu_bound(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """
        Run a CPU-bound function in the thread pool.

        Args:
            func: Synchronous function to run
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func(*args, **kwargs)
        """
        loop = self._loop or asyncio.get_event_loop()
        
        # If function accepts kwargs, use functools.partial
        if kwargs:
            from functools import partial
            func = partial(func, **kwargs)
        
        return await loop.run_in_executor(self.executor, func, *args)

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor."""
        logger.debug("Shutting down executor (wait=%s)", wait)
        self.executor.shutdown(wait=wait)

