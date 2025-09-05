from flask import Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder="../../templates/admin")

from . import analytics, auth, blogs, chat_logs, dashboard, pdf_processor, universities

__all__ = ['admin_bp']
