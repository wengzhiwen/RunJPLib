from flask import Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder="../../templates/admin")

from . import analytics
from . import auth
from . import blogs
from . import chat_logs
from . import dashboard
from . import pdf_processor
from . import universities

__all__ = ['admin_bp']
