"""
系统管理模块
包含任务管理、线程池管理、访问分析等系统功能
"""

from .analytics import log_access
from .task_manager import TaskManager, task_manager
from .thread_pool import ConcurrentTaskExecutor

# 向后兼容的别名
ThreadPoolManager = ConcurrentTaskExecutor

__all__ = ['TaskManager', 'task_manager', 'ConcurrentTaskExecutor', 'ThreadPoolManager', 'log_access']
