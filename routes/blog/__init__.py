"""
Blog 路由模块
包含博客相关的所有路由
所有导入都应该直接使用文件路径，例如：
- from routes.blog.views import blog_list_route
- from routes.blog.cache import update_blog_html_in_db
"""

from ..blueprints import blog_bp

__all__ = ['blog_bp']
