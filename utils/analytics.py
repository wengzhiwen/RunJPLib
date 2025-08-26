from datetime import datetime
import logging

from flask import request

from utils.mongo_client import get_db


def log_access(page_type: str):
    """
    Logs an access event to the database.
    :param page_type: The type of page being accessed ('university' or 'blog').
    """
    db = get_db()
    if db is None:
        logging.error("log_access: Failed to get database connection.")
        return

    try:
        # Get the real IP address, considering proxies
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)

        access_log = {
            "ip": ip_address,
            "timestamp": datetime.utcnow(),
            "page_type": page_type
        }
        db.access_logs.insert_one(access_log)
    except Exception as e:
        logging.error(f"Error logging access: {e}", exc_info=True)
