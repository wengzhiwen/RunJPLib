from flask import Blueprint

blog_bp = Blueprint('blog', __name__, url_prefix='/blog')

from . import cache
from . import views

__all__ = ['blog_bp']
