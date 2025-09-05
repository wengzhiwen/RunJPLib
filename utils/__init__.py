"""
Utils 模块 - 向后兼容的导入接口
"""

# AI相关工具
from .ai.analysis_tool import DocumentAnalyzer as AnalysisTool
from .ai.batch_ocr_tool import BatchOcrProcessor as BatchOCRTool
from .ai.blog_generator import ContentGenerator as BlogGenerator
from .ai.ocr_tool import ImageOcrProcessor as OCRTool
from .ai.translate_tool import DocumentTranslator as TranslateTool
from .chat.logging import ChatSessionLogger as ChatLoggingManager
from .chat.logging import chat_logger

# 聊天相关
from .chat.manager import ChatManager
from .chat.search_strategy import HybridSearchEngine as EnhancedSearchStrategy

# 全局实例（保持原有名称）
from .chat.security import ChatSecurityGuard as ChatSecurityManager
from .chat.security import security_manager, add_security_headers, get_csrf_token_for_session, public_chat_api_protection
from .core.config import Config

# 核心功能
from .core.database import ensure_indexes, get_db, get_mongo_client
from .core.logging import setup_logger, setup_retrieval_logger, setup_task_logger

# 文档处理
from .document.pdf_processor import PDFProcessor, run_pdf_processor
from .document.wiki_processor import BlogWikiProcessor, blog_wiki_processor
from .system.analytics import log_access

# 系统管理
from .system.task_manager import TaskManager, task_manager
from .system.thread_pool import ConcurrentTaskExecutor as ThreadPoolManager
from .system.thread_pool import thread_pool_manager

# 工具类
from .tools.cache import blog_list_cache, clear_blog_list_cache, TTLCache
from .tools.ip_geo import GeoLocationResolver as IPGeoManager
from .tools.ip_geo import ip_geo_manager

# 大学相关
from .university.manager import UniversityRepository as UniversityDocumentManager
from .university.search import VectorSearchEngine as LlamaIndexIntegration
from .university.tagger import UniversityClassifier as UniversityTagger

__all__ = [
    # AI工具
    'AnalysisTool',
    'BlogGenerator',
    'OCRTool',
    'BatchOCRTool',
    'TranslateTool',
    # 聊天相关
    'ChatManager',
    'ChatSecurityManager',
    'ChatLoggingManager',
    'EnhancedSearchStrategy',
    # 文档处理
    'PDFProcessor',
    'run_pdf_processor',
    'BlogWikiProcessor',
    'blog_wiki_processor',
    # 大学相关
    'UniversityDocumentManager',
    'UniversityTagger',
    'LlamaIndexIntegration',
    # 系统管理
    'TaskManager',
    'task_manager',
    'ThreadPoolManager',
    'log_access',
    # 工具类
    'blog_list_cache',
    'clear_blog_list_cache',
    'TTLCache',
    'IPGeoManager',
    # 核心功能
    'get_db',
    'get_mongo_client',
    'ensure_indexes',
    'setup_logger',
    'setup_task_logger',
    'setup_retrieval_logger',
    'Config',
    # 全局实例
    'security_manager',
    'chat_logger',
    'ip_geo_manager',
    'thread_pool_manager',
    'add_security_headers',
    'get_csrf_token_for_session',
    'public_chat_api_protection'
]
