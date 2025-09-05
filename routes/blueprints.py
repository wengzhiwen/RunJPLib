"""
Routes Blueprint 定义
集中管理所有路由的Blueprint定义
"""

from flask import Blueprint

# Admin Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder="../templates/admin")

# Blog Blueprint
blog_bp = Blueprint('blog', __name__, url_prefix='/blog')

# Chat Blueprint
chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')
