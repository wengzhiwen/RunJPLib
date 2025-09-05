"""
日志配置 - 为应用程序提供统一的日志记录设置
"""
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


def setup_logger(logger_name="AppLogger", log_level="INFO", log_file="app.log"):
    """
    配置并返回一个通用的、按天轮换的日志记录器。
    """
    log_directory = "log"
    os.makedirs(log_directory, exist_ok=True)
    log_filepath = os.path.join(log_directory, log_file)

    logger = logging.getLogger(logger_name)
    # 从环境变量中获取日志级别，如果未设置则使用默认值
    effective_log_level = os.getenv("LOG_LEVEL", log_level).upper()
    logger.setLevel(effective_log_level)

    # 防止重复添加处理器
    if not logger.handlers:
        # 设置一个按天轮换的文件处理器
        handler = TimedRotatingFileHandler(log_filepath, when="midnight", interval=1, backupCount=7, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # 添加一个控制台处理器，方便在开发时查看日志
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def setup_task_logger(logger_name="TaskManager", log_level="INFO"):
    """
    为特定任务（如PDF处理）配置一个专用的、按天分割的日志记录器。
    """
    log_directory = "log"
    os.makedirs(log_directory, exist_ok=True)

    date_str = datetime.now().strftime("%Y%m%d")
    log_filename = os.path.join(log_directory, f"{logger_name}_{date_str}.log")

    logger = logging.getLogger(logger_name)
    effective_log_level = os.getenv("LOG_LEVEL", log_level).upper()
    logger.setLevel(effective_log_level)

    # 为确保日志句柄的正确性（特别是日期变化时），总是先清空旧的
    if logger.hasHandlers():
        logger.handlers.clear()

    # 添加文件处理器
    handler = logging.FileHandler(log_filename, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(threadName)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # 添加控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 禁止将日志消息传播到父记录器
    logger.propagate = False

    return logger


def setup_retrieval_logger() -> logging.Logger:
    """
    设置专门用于记录检索操作的日志记录器
    """
    logger_name = "retrieval"
    log_dir = "log"
    log_file_path = os.path.join(log_dir, f"{logger_name}_{datetime.now().strftime('%Y%m%d')}.log")

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
