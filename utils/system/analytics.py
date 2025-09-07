from datetime import datetime
import logging

from flask import request

from ..core.database import get_db
from ..system.thread_pool import thread_pool_manager


def _write_access_log_to_db(access_log: dict):
    """
    内部函数：将访问日志写入数据库
    在线程池中执行，避免阻塞主请求
    """
    try:
        db = get_db()
        if db is None:
            logging.error("_write_access_log_to_db: Failed to get database connection.")
            return

        db.access_logs.insert_one(access_log)
        logging.debug(f"Access log written: {access_log['page_type']} from {access_log['ip']}")
    except Exception as e:
        logging.error(f"Error writing access log to database: {e}", exc_info=True)


def log_access(page_type: str, resource_key: str | None = None):
    """
    使用线程池记录访问事件到数据库，以避免阻塞请求。
    :param page_type: 被访问的页面类型 ('university' 或 'blog').
    """
    try:
        # 获取真实的IP地址，考虑代理情况
        # X-Forwarded-For 可能包含多个IP: "client_ip, proxy1_ip, proxy2_ip"
        # 我们只需要第一个 (原始客户端) IP
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            # 按逗号分割并取第一个IP，然后去除空白
            ip_address = forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.remote_addr

        access_log = {
            "ip": ip_address,
            "timestamp": datetime.utcnow(),
            "page_type": page_type,
        }

        if resource_key:
            access_log["resource_key"] = resource_key

        # 尝试提交到Analytics专用线程池进行异步写入
        success = thread_pool_manager.submit_user_access_log_task(_write_access_log_to_db, access_log)

        if not success:
            # 线程池繁忙，降级为同步执行（避免丢失日志）
            logging.warning("Thread pool busy, logging access synchronously")
            _write_access_log_to_db(access_log)

    except Exception as e:
        logging.error(f"Error logging access: {e}", exc_info=True)
