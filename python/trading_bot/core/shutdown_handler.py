"""Graceful shutdown handler for Docker environment."""

import asyncio
import logging
import signal
import sys
from typing import List, Callable, Optional

logger = logging.getLogger(__name__)

class ShutdownHandler:
    """Handles graceful shutdown of the application in Docker environment."""
    
    def __init__(self):
        """Initialize the shutdown handler."""
        self.shutdown_requested = False
        self.shutdown_callbacks: List[Callable] = []
        self.cleanup_tasks: List[asyncio.Task] = []
        self.shutdown_timeout = 30  # seconds
        
    def add_shutdown_callback(self, callback: Callable):
        """Add a callback to be executed during shutdown."""
        self.shutdown_callbacks.append(callback)
        logger.debug(f"Added shutdown callback: {callback.__name__}")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        # Handle SIGTERM (Docker stop)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Handle SIGINT (Ctrl+C)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Handle SIGHUP (reload)
        signal.signal(signal.SIGHUP, self._signal_handler)
        
        logger.info("Signal handlers setup for graceful shutdown")
    
    def _signal_handler(self, signum: int, frame):
        """Handle shutdown signals."""
        signal_names = {
            int(signal.SIGTERM): "SIGTERM",
            int(signal.SIGINT): "SIGINT",
            int(signal.SIGHUP): "SIGHUP"
        }
        
        signal_name = signal_names.get(signum, f"Signal {signum}")
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        
        self.shutdown_requested = True
        
        # For SIGHUP, we might want to reload instead of shutdown
        if signum == signal.SIGHUP:
            logger.info("SIGHUP received - configuration reload requested")
            # Could implement config reload here
        
        # Create shutdown task if we're in an event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_shutdown())
        except RuntimeError:
            # No event loop running, perform synchronous shutdown
            self._sync_shutdown()
    
    async def _async_shutdown(self):
        """Perform asynchronous shutdown."""
        logger.info("Starting asynchronous shutdown sequence...")
        
        try:
            # Execute shutdown callbacks
            for callback in self.shutdown_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                    logger.debug(f"Executed shutdown callback: {callback.__name__}")
                except Exception as e:
                    logger.error(f"Error in shutdown callback {callback.__name__}: {e}")
            
            # Cancel any remaining tasks
            await self._cancel_remaining_tasks()
            
            logger.info("Graceful shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during async shutdown: {e}")
        finally:
            # Force exit if needed
            sys.exit(0)
    
    def _sync_shutdown(self):
        """Perform synchronous shutdown."""
        logger.info("Starting synchronous shutdown sequence...")
        
        try:
            # Execute non-async shutdown callbacks
            for callback in self.shutdown_callbacks:
                try:
                    if not asyncio.iscoroutinefunction(callback):
                        callback()
                        logger.debug(f"Executed shutdown callback: {callback.__name__}")
                except Exception as e:
                    logger.error(f"Error in shutdown callback {callback.__name__}: {e}")
            
            logger.info("Synchronous shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during sync shutdown: {e}")
        finally:
            sys.exit(0)
    
    async def _cancel_remaining_tasks(self):
        """Cancel all remaining asyncio tasks."""
        try:
            # Get all running tasks
            tasks = [task for task in asyncio.all_tasks() if not task.done()]
            
            if not tasks:
                return
            
            logger.info(f"Cancelling {len(tasks)} remaining tasks...")
            
            # Cancel all tasks
            for task in tasks:
                task.cancel()
            
            # Wait for tasks to complete cancellation
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self.shutdown_timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Some tasks did not complete within {self.shutdown_timeout}s timeout")
            
            logger.info("Task cancellation completed")
            
        except Exception as e:
            logger.error(f"Error cancelling tasks: {e}")
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self.shutdown_requested
    
    def wait_for_shutdown(self, check_interval: float = 0.1):
        """Wait for shutdown signal (blocking)."""
        import time
        
        while not self.shutdown_requested:
            time.sleep(check_interval)
    
    async def async_wait_for_shutdown(self, check_interval: float = 0.1):
        """Wait for shutdown signal (async)."""
        while not self.shutdown_requested:
            await asyncio.sleep(check_interval)

# Global shutdown handler instance
_shutdown_handler: Optional[ShutdownHandler] = None

def get_shutdown_handler() -> ShutdownHandler:
    """Get the global shutdown handler instance."""
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = ShutdownHandler()
    return _shutdown_handler

def setup_graceful_shutdown():
    """Setup graceful shutdown for the application."""
    handler = get_shutdown_handler()
    handler.setup_signal_handlers()
    return handler

def add_shutdown_callback(callback: Callable):
    """Add a shutdown callback to the global handler."""
    handler = get_shutdown_handler()
    handler.add_shutdown_callback(callback)

def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested."""
    handler = get_shutdown_handler()
    return handler.is_shutdown_requested()

async def wait_for_shutdown():
    """Wait for shutdown signal."""
    handler = get_shutdown_handler()
    await handler.async_wait_for_shutdown()