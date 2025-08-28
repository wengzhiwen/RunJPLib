"""
线程池管理器 - 管理不同类型的后台任务
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any
import time

from utils.logging_config import setup_logger

logger = setup_logger(logger_name="ThreadPoolManager", log_level="INFO")


class ThreadPoolManager:
    """线程池管理器 - 单例模式，支持多个独立线程池"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ThreadPoolManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True

        # 从环境变量获取线程池配置
        self.blog_max_workers = self._get_env_int('BLOG_UPDATE_THREAD_POOL_SIZE', 8)
        self.admin_max_workers = self._get_env_int('ADMIN_THREAD_POOL_SIZE', 4)
        self.analytics_max_workers = self._get_env_int('ANALYTICS_THREAD_POOL_SIZE', 6)

        # 创建三个独立的线程池
        self.blog_update_executor = ThreadPoolExecutor(max_workers=self.blog_max_workers, thread_name_prefix="BlogUpdate")

        self.admin_executor = ThreadPoolExecutor(max_workers=self.admin_max_workers, thread_name_prefix="AdminOps")

        self.analytics_executor = ThreadPoolExecutor(max_workers=self.analytics_max_workers, thread_name_prefix="Analytics")

        # 统计信息 - 分线程池统计
        self.stats = {
            'blog': {
                'submitted': 0,
                'completed': 0,
                'failed': 0,
                'sync_fallback': 0
            },
            'admin': {
                'submitted': 0,
                'completed': 0,
                'failed': 0,
                'sync_fallback': 0
            },
            'analytics': {
                'submitted': 0,
                'completed': 0,
                'failed': 0,
                'sync_fallback': 0
            }
        }

        logger.info(f"线程池管理器初始化完成 - 博客更新:{self.blog_max_workers}, Admin:{self.admin_max_workers}, Analytics:{self.analytics_max_workers}")

    def _get_env_int(self, env_name: str, default: int) -> int:
        """安全地从环境变量获取整数值"""
        try:
            value = int(os.getenv(env_name, str(default)))
            if value <= 0:
                raise ValueError(f"{env_name}必须大于0")
            return value
        except (ValueError, TypeError) as e:
            logger.warning(f"{env_name}配置无效: {e}，使用默认值{default}")
            return default

    def submit_blog_update(self, func, *args, **kwargs) -> bool:
        """提交博客更新任务到专用线程池"""
        return self._submit_task('blog', self.blog_update_executor, func, *args, **kwargs)

    def submit_admin_task(self, func, *args, **kwargs) -> bool:
        """提交Admin操作任务到专用线程池"""
        return self._submit_task('admin', self.admin_executor, func, *args, **kwargs)

    def submit_analytics_task(self, func, *args, **kwargs) -> bool:
        """提交Analytics日志任务到专用线程池"""
        return self._submit_task('analytics', self.analytics_executor, func, *args, **kwargs)

    def _submit_task(self, pool_type: str, executor: ThreadPoolExecutor, func, *args, **kwargs) -> bool:
        """
        内部方法：提交任务到指定线程池
        
        Args:
            pool_type: 线程池类型 ('blog', 'admin', 'analytics')
            executor: 线程池执行器
            func: 要执行的函数
            *args, **kwargs: 函数参数
            
        Returns:
            bool: True表示成功提交到线程池，False表示线程池满，需要同步执行
        """
        try:
            # 尝试提交到线程池
            executor.submit(self._task_wrapper, pool_type, func, *args, **kwargs)
            self.stats[pool_type]['submitted'] += 1
            logger.debug(f"{pool_type}任务已提交到线程池，当前活跃线程: {self._get_active_thread_count(executor)}")
            return True

        except Exception as e:
            logger.warning(f"{pool_type}线程池提交失败: {e}，将使用同步执行")
            self.stats[pool_type]['sync_fallback'] += 1
            return False

    def _task_wrapper(self, pool_type: str, func, *args, **kwargs):
        """
        任务包装器，用于统计和错误处理
        """
        try:
            start_time = time.time()
            result = func(*args, **kwargs)
            self.stats[pool_type]['completed'] += 1
            duration = time.time() - start_time
            logger.debug(f"{pool_type}任务执行完成，耗时: {duration:.3f}秒")
            return result
        except Exception as e:
            self.stats[pool_type]['failed'] += 1
            logger.error(f"{pool_type}线程池任务执行失败: {e}")
            raise

    def get_pool_stats(self) -> Dict[str, Any]:
        """
        获取所有线程池的统计信息
        
        Returns:
            dict: 包含所有线程池状态的字典
        """
        return {
            "blog_pool": {
                "max_workers": self.blog_max_workers,
                "active_threads": self._get_active_thread_count(self.blog_update_executor),
                "queue_size": self._get_queue_size(self.blog_update_executor),
                **self.stats['blog']
            },
            "admin_pool": {
                "max_workers": self.admin_max_workers,
                "active_threads": self._get_active_thread_count(self.admin_executor),
                "queue_size": self._get_queue_size(self.admin_executor),
                **self.stats['admin']
            },
            "analytics_pool": {
                "max_workers": self.analytics_max_workers,
                "active_threads": self._get_active_thread_count(self.analytics_executor),
                "queue_size": self._get_queue_size(self.analytics_executor),
                **self.stats['analytics']
            },
            # 为了向后兼容，保留原有的总计字段
            "max_workers": self.blog_max_workers,  # 兼容性
            "active_threads": self._get_active_thread_count(self.blog_update_executor),  # 兼容性
            "submitted_tasks": sum(pool['submitted'] for pool in self.stats.values()),
            "completed_tasks": sum(pool['completed'] for pool in self.stats.values()),
            "failed_tasks": sum(pool['failed'] for pool in self.stats.values()),
            "sync_fallback_count": sum(pool['sync_fallback'] for pool in self.stats.values()),
            "queue_size": self._get_queue_size(self.blog_update_executor)  # 兼容性
        }

    def _get_active_thread_count(self, executor: ThreadPoolExecutor) -> int:
        """
        获取指定线程池当前活跃的线程数
        """
        try:
            # 获取线程池中活跃线程数
            return len(getattr(executor, '_threads', []))
        except Exception:
            return 0

    def _get_queue_size(self, executor: ThreadPoolExecutor) -> int:
        """
        获取指定线程池当前等待队列大小
        """
        try:
            # 获取线程池中等待的任务数
            work_queue = getattr(executor, '_work_queue', None)
            if work_queue:
                return work_queue.qsize()
            return 0
        except Exception:
            return 0

    def shutdown(self, wait: bool = True):
        """
        关闭所有线程池
        
        Args:
            wait: 是否等待所有任务完成
        """
        logger.info("正在关闭所有线程池...")

        self.blog_update_executor.shutdown(wait=wait)
        self.admin_executor.shutdown(wait=wait)
        self.analytics_executor.shutdown(wait=wait)

        logger.info("所有线程池已关闭")

    def __del__(self):
        """析构函数，确保线程池被正确关闭"""
        try:
            self.shutdown(wait=False)
        except Exception:
            pass


# 全局线程池管理器实例
thread_pool_manager = ThreadPoolManager()
