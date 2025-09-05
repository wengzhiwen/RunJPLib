"""
Admin 路由模块
包含管理员相关的所有路由
所有导入都应该直接使用文件路径，例如：
- from routes.admin.auth import admin_required
- from routes.admin.blogs import save_blog
"""

from ..blueprints import admin_bp

__all__ = ['admin_bp']
