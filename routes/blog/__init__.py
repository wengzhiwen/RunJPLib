from flask import Blueprint

blog_bp = Blueprint('blog', __name__, url_prefix='/blog')

from . import cache, views

__all__ = ['blog_bp']
