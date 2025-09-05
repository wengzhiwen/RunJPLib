"""
University Chat 路由模块
包含大学聊天相关的所有路由
所有导入都应该直接使用文件路径，例如：
- from routes.university_chat.chat_api import chat_api_route
- from routes.university_chat.security import get_client_ip
"""

from ..blueprints import chat_bp

__all__ = ['chat_bp']
