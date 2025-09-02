import datetime
import logging
import os


def setup_logger(logger_name="app", log_dir="log", log_level="INFO") -> logging.Logger:
    """
    设置通用日志记录器

    参数:
        logger_name (str): 日志记录器名称
        log_dir (str): 日志文件保存目录
        log_level (str): 日志级别，默认为INFO

    返回:
        logging.Logger: 配置好的日志记录器
    """
    app_logger = logging.getLogger(logger_name)
    level = os.getenv("LOG_LEVEL", log_level)
    app_logger.setLevel(level)

    # 关键修复：清除已存在的handlers，确保每次都使用正确的配置
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    formatter = logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{logger_name}_{datetime.datetime.now().strftime('%Y%m%d')}.log")

    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.propagate = False

    return app_logger


def setup_retrieval_logger() -> logging.Logger:
    """
    设置专门用于记录检索操作的日志记录器

    返回:
        logging.Logger: 配置好的检索日志记录器
    """
    logger_name = "retrieval"
    log_dir = "log"
    log_file_path = os.path.join(log_dir, f"{logger_name}_{datetime.datetime.now().strftime('%Y%m%d')}.log")

    retrieval_logger = logging.getLogger(logger_name)
    retrieval_logger.setLevel(logging.INFO)

    # 关键修复：清除已存在的handlers，确保文件handler总是被正确添加
    if retrieval_logger.hasHandlers():
        retrieval_logger.handlers.clear()

    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s - %(message)s")

    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)

    retrieval_logger.addHandler(file_handler)
    retrieval_logger.propagate = False

    return retrieval_logger
