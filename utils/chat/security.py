"""
聊天系统安全模块
提供API保护、防外站调用、速率限制等功能
"""
from functools import wraps
import hmac
import logging
import os
import secrets
import time
from urllib.parse import urlparse

from cachetools import TTLCache
import dotenv
from flask import jsonify
from flask import request

logger = logging.getLogger(__name__)

# 速率限制缓存 - IP地址 -> (调用次数, 时间窗口开始时间)
rate_limit_cache = TTLCache(maxsize=10000, ttl=3600)  # 1小时TTL

# CSRF令牌缓存 - 会话ID -> 令牌
csrf_token_cache = TTLCache(maxsize=1000, ttl=1800)  # 30分钟TTL

dotenv.load_dotenv()

# 获取允许的域名列表
ALLOWED_DOMAINS = os.getenv('ALLOWED_DOMAINS', 'localhost,127.0.0.1,100.88.88.88').split(',')
ALLOWED_PORTS = os.getenv('ALLOWED_PORTS', '5000,3000,8080,5070,80,443').split(',')


class ChatSecurityGuard:
    """聊天系统安全守护者"""

    def __init__(self):
        self.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-secret-key')

    def generate_csrf_token(self, session_id: str) -> str:
        """生成CSRF令牌"""
        token = secrets.token_urlsafe(32)
        csrf_token_cache[session_id] = token
        logger.debug(f"生成CSRF令牌: {session_id}")
        return token

    def validate_csrf_token(self, session_id: str, token: str) -> bool:
        """验证CSRF令牌"""
        stored_token = csrf_token_cache.get(session_id)
        if not stored_token:
            logger.warning(f"CSRF令牌不存在: {session_id}")
            return False

        is_valid = hmac.compare_digest(stored_token, token)
        if is_valid:
            logger.debug(f"CSRF令牌验证成功: {session_id}")
        else:
            logger.warning(f"CSRF令牌验证失败: {session_id}")

        return is_valid

    def is_request_from_allowed_origin(self, req) -> bool:
        """检查请求是否来自允许的源"""
        # 通过LOG_LEVEL=DEBUG判断是否为开发环境
        debug_mode = os.getenv('LOG_LEVEL', '').upper() == 'DEBUG'

        # 检查Origin头
        origin = req.headers.get('Origin')
        if origin:
            parsed = urlparse(origin)
            domain = parsed.hostname
            port = str(parsed.port) if parsed.port else ('443' if parsed.scheme == 'https' else '80')

            if domain in ALLOWED_DOMAINS:
                if port in ALLOWED_PORTS or port in ['80', '443']:
                    logger.debug(f"请求来自允许的Origin: {origin}")
                    return True

            # 开发环境下允许内网地址
            if debug_mode and (domain.startswith('192.168.') or domain.startswith('10.') or domain.startswith('172.') or domain == 'localhost'
                               or domain == '127.0.0.1'):
                logger.debug(f"开发环境允许内网Origin: {origin}")
                return True

            logger.warning(f"请求来自不允许的Origin: {origin} (domain: {domain}, port: {port})")
            logger.warning(f"允许的域名: {ALLOWED_DOMAINS}, 允许的端口: {ALLOWED_PORTS}")
            return False

        # 检查Referer头（作为备选）
        referer = req.headers.get('Referer')
        if referer:
            parsed = urlparse(referer)
            domain = parsed.hostname
            port = str(parsed.port) if parsed.port else ('443' if parsed.scheme == 'https' else '80')

            if domain in ALLOWED_DOMAINS:
                if port in ALLOWED_PORTS or port in ['80', '443']:
                    logger.debug(f"请求来自允许的Referer: {referer}")
                    return True

            # 开发环境下允许内网地址
            if debug_mode and (domain.startswith('192.168.') or domain.startswith('10.') or domain.startswith('172.') or domain == 'localhost'
                               or domain == '127.0.0.1'):
                logger.debug(f"开发环境允许内网Referer: {referer}")
                return True

            logger.warning(f"请求来自不允许的Referer: {referer} (domain: {domain}, port: {port})")
            return False

        # 对于直接访问（没有Origin和Referer），在开发环境下更宽松
        remote_addr = req.remote_addr
        if remote_addr in ['127.0.0.1', '::1', 'localhost'
                           ] or (debug_mode and (remote_addr.startswith('192.168.') or remote_addr.startswith('10.') or remote_addr.startswith('172.'))):
            logger.debug(f"允许来自本地/内网的直接访问: {remote_addr}")
            return True

        logger.warning(f"请求缺少Origin和Referer头，来源IP: {remote_addr}")
        return False

    def check_rate_limit(self, identifier: str, max_requests: int = 60, time_window: int = 60) -> bool:
        """检查速率限制"""
        current_time = time.time()
        key = f"rate_limit_{identifier}"

        if key in rate_limit_cache:
            request_count, window_start = rate_limit_cache[key]

            # 如果在时间窗口内
            if current_time - window_start < time_window:
                if request_count >= max_requests:
                    logger.warning(f"速率限制触发: {identifier}, 请求数: {request_count}")
                    return False
                else:
                    # 增加请求计数
                    rate_limit_cache[key] = (request_count + 1, window_start)
            else:
                # 新的时间窗口
                rate_limit_cache[key] = (1, current_time)
        else:
            # 首次请求
            rate_limit_cache[key] = (1, current_time)

        return True

    def get_client_identifier(self, req) -> str:
        """获取客户端标识符（用于速率限制）"""
        # 优先使用X-Forwarded-For（考虑代理）
        x_forwarded_for = req.headers.get('X-Forwarded-For')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()

        # 使用X-Real-IP
        x_real_ip = req.headers.get('X-Real-IP')
        if x_real_ip:
            return x_real_ip

        # 最后使用remote_addr
        return req.remote_addr or 'unknown'


# 全局安全管理器实例
# 使用新类名实例化以提高代码清晰度，但导出时使用旧名称以保持向后兼容
security_manager = ChatSecurityGuard()


def chat_api_protection(max_requests: int = 60, time_window: int = 60):
    """
    聊天API保护装饰器
    
    Args:
        max_requests: 时间窗口内的最大请求数
        time_window: 时间窗口（秒）
    """

    def decorator(f):

        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. 检查请求来源
            if not security_manager.is_request_from_allowed_origin(request):
                logger.warning(f"拒绝来自不允许源的请求: {request.remote_addr}")
                return jsonify({"success": False, "error": "请求来源不被允许", "error_code": "FORBIDDEN_ORIGIN"}), 403

            # 2. 速率限制检查
            client_id = security_manager.get_client_identifier(request)
            if not security_manager.check_rate_limit(client_id, max_requests, time_window):
                logger.warning(f"速率限制: {client_id}")
                return jsonify({"success": False, "error": "请求过于频繁，请稍后再试", "error_code": "RATE_LIMIT_EXCEEDED"}), 429

            # 3. 对于POST请求，检查CSRF令牌
            if request.method == 'POST':
                csrf_token = request.headers.get('X-CSRF-Token') or request.json.get('csrf_token') if request.json else None
                session_id = request.headers.get('X-Session-ID') or (request.json.get('session_id') if request.json else None)

                if session_id and csrf_token:
                    if not security_manager.validate_csrf_token(session_id, csrf_token):
                        logger.warning(f"CSRF令牌验证失败: {client_id}")
                        return jsonify({"success": False, "error": "安全令牌验证失败", "error_code": "CSRF_TOKEN_INVALID"}), 403
                elif request.endpoint not in ['chat.create_session'] and 'create-session' not in request.path:  # 创建会话时不需要CSRF令牌
                    logger.warning(f"缺少CSRF令牌: {client_id}")
                    return jsonify({"success": False, "error": "缺少安全令牌", "error_code": "CSRF_TOKEN_MISSING"}), 403

            # 4. 记录安全日志
            logger.info(f"安全检查通过: {client_id} -> {request.endpoint}")

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def public_chat_api_protection(max_requests: int = 30, time_window: int = 60):
    """
    公共聊天API保护装饰器（更严格的限制）
    """
    return chat_api_protection(max_requests, time_window)


def get_csrf_token_for_session(session_id: str) -> str:
    """为指定会话获取CSRF令牌"""
    return security_manager.generate_csrf_token(session_id)


def add_security_headers(response):
    """添加安全头"""
    # 防止XSS
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # CSP策略
    csp_policy = ("default-src 'self'; "
                  "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                  "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                  "font-src 'self' https://cdn.jsdelivr.net; "
                  "img-src 'self' data:; "
                  "connect-src 'self'")
    response.headers['Content-Security-Policy'] = csp_policy

    return response


def log_security_event(event_type: str, details: dict):
    """记录安全事件"""
    logger.warning(f"安全事件 [{event_type}]: {details}")


# 清理过期缓存的函数
def cleanup_security_caches():
    """清理过期的安全缓存"""
    current_time = time.time()

    # 清理速率限制缓存中的过期条目
    expired_keys = []
    for key, (_, window_start) in rate_limit_cache.items():
        if current_time - window_start > 3600:  # 1小时过期
            expired_keys.append(key)

    for key in expired_keys:
        del rate_limit_cache[key]

    logger.info(f"清理了 {len(expired_keys)} 个过期的速率限制缓存条目")
