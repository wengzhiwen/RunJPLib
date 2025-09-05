"""
聊天相关模块
包含聊天管理、安全控制、日志记录、搜索策略等功能
"""

from .logging import ChatSessionLogger
from .manager import ChatManager
from .search_strategy import HybridSearchEngine
from .security import ChatSecurityGuard

# 向后兼容的别名
ChatSecurityManager = ChatSecurityGuard
ChatLoggingManager = ChatSessionLogger
EnhancedSearchStrategy = HybridSearchEngine

__all__ = ['ChatManager', 'ChatSecurityGuard', 'ChatSecurityManager', 'ChatSessionLogger', 'ChatLoggingManager', 'HybridSearchEngine', 'EnhancedSearchStrategy']
