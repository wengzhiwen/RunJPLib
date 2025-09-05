from flask import Blueprint

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')

from . import chat_api, security

__all__ = ['chat_bp']
