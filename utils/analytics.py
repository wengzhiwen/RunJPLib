from datetime import datetime
import logging

from flask import request

from utils.mongo_client import get_db
from utils.thread_pool_manager import thread_pool_manager


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


def log_access(page_type: str):
    """
    Logs an access event to the database using thread pool to avoid blocking the request.
    :param page_type: The type of page being accessed ('university' or 'blog').
    """
    try:
        # Get the real IP address, considering proxies
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)

        access_log = {"ip": ip_address, "timestamp": datetime.utcnow(), "page_type": page_type}

        # 尝试提交到Analytics专用线程池进行异步写入
        success = thread_pool_manager.submit_user_access_log_task(_write_access_log_to_db, access_log)

        if not success:
            # 线程池繁忙，降级为同步执行（避免丢失日志）
            logging.warning("Thread pool busy, logging access synchronously")
            _write_access_log_to_db(access_log)

    except Exception as e:
        logging.error(f"Error logging access: {e}", exc_info=True)
