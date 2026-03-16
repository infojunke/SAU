"""Parallel execution utilities for batch operations"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


@dataclass
class TaskResult(Generic[T]):
    """Result of a parallel task execution"""
    input: Any
    result: Optional[T] = None
    error: Optional[Exception] = None
    success: bool = True


class ParallelExecutor:
    """Execute multiple operations in parallel using thread pool
    
    This is useful for batch API calls, file operations, or any I/O-bound tasks
    that can benefit from parallelization.
    
    Example:
        executor = ParallelExecutor(max_workers=5)
        
        # Check versions for multiple apps in parallel
        app_ids = ["742", "833", "1876"]
        results = executor.map(
            items=app_ids,
            func=splunkbase_client.get_available_versions,
            description="Checking Splunkbase versions"
        )
        
        for result in results:
            if result.success:
                print(f"App {result.input}: {result.result}")
            else:
                print(f"App {result.input} failed: {result.error}")
    """
    
    def __init__(self, max_workers: int = 5, show_progress: bool = True):
        self.max_workers = max_workers
        self.show_progress = show_progress
    
    def map(
        self, 
        items: List[Any], 
        func: Callable[[Any], T],
        description: str = "Processing",
        on_item_complete: Optional[Callable[[Any, T], None]] = None
    ) -> List[TaskResult[T]]:
        """Execute a function on multiple items in parallel
        
        Args:
            items: List of inputs to process
            func: Function to apply to each item
            description: Description for progress display
            on_item_complete: Optional callback when each item completes
            
        Returns:
            List of TaskResult objects with results or errors
        """
        results: List[TaskResult[T]] = []
        total = len(items)
        completed = 0
        
        if total == 0:
            return results
        
        if self.show_progress:
            print(f"\n{description} ({total} items)...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_input = {
                executor.submit(func, item): item 
                for item in items
            }
            
            # Process results as they complete
            for future in as_completed(future_to_input):
                input_item = future_to_input[future]
                completed += 1
                
                try:
                    result = future.result()
                    task_result = TaskResult(input=input_item, result=result, success=True)
                    
                    if on_item_complete:
                        on_item_complete(input_item, result)
                        
                except Exception as e:
                    logger.warning(f"Task failed for {input_item}: {e}")
                    task_result = TaskResult(input=input_item, error=e, success=False)
                
                results.append(task_result)
                
                if self.show_progress:
                    progress = completed / total * 100
                    print(f"\r  [{completed}/{total}] {progress:.0f}%", end='', flush=True)
        
        if self.show_progress:
            print()  # New line after progress
        
        return results
    
    def map_dict(
        self,
        items: Dict[str, Any],
        func: Callable[[Any], T],
        description: str = "Processing"
    ) -> Dict[str, TaskResult[T]]:
        """Execute a function on dictionary values in parallel
        
        Args:
            items: Dictionary of key -> input
            func: Function to apply to each value
            description: Description for progress display
            
        Returns:
            Dictionary of key -> TaskResult
        """
        keys = list(items.keys())
        values = list(items.values())
        
        results = self.map(values, func, description)
        
        return {key: result for key, result in zip(keys, results)}


class BatchVersionChecker:
    """Efficient batch version checking for multiple apps
    
    Uses parallel execution to check Splunkbase for updates on multiple apps.
    
    Example:
        checker = BatchVersionChecker(splunkbase_client, max_workers=5)
        version_map = checker.get_versions_batch(["742", "833", "1876"])
        
        for app_id, versions in version_map.items():
            print(f"App {app_id}: Latest is {versions[0] if versions else 'unknown'}")
    """
    
    def __init__(self, splunkbase_client, max_workers: int = 5):
        self.client = splunkbase_client
        self.executor = ParallelExecutor(max_workers=max_workers, show_progress=True)
    
    def get_versions_batch(self, app_ids: List[str]) -> Dict[str, List[str]]:
        """Get available versions for multiple apps in parallel
        
        Args:
            app_ids: List of Splunkbase app IDs
            
        Returns:
            Dictionary mapping app_id -> list of versions
        """
        results = self.executor.map(
            items=app_ids,
            func=self.client.get_available_versions,
            description="Checking Splunkbase for updates"
        )
        
        return {
            str(result.input): result.result if result.success and result.result else []
            for result in results
        }
    
    def get_app_info_batch(self, app_ids: List[str]) -> Dict[str, Optional[Dict]]:
        """Get app information for multiple apps in parallel
        
        Args:
            app_ids: List of Splunkbase app IDs
            
        Returns:
            Dictionary mapping app_id -> app info dict
        """
        results = self.executor.map(
            items=app_ids,
            func=self.client.get_app_info,
            description="Fetching app information"
        )
        
        return {
            result.input: result.result if result.success else None
            for result in results
        }


def parallel_map(
    items: List[Any],
    func: Callable[[Any], T],
    max_workers: int = 5,
    description: str = "Processing"
) -> List[TaskResult[T]]:
    """Convenience function for one-off parallel operations
    
    Args:
        items: List of inputs to process
        func: Function to apply to each item
        max_workers: Maximum parallel workers
        description: Description for progress display
        
    Returns:
        List of TaskResult objects
    """
    executor = ParallelExecutor(max_workers=max_workers)
    return executor.map(items, func, description)
