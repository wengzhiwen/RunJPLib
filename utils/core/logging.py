"""
日志配置 - 为应用程序提供统一的日志记录设置
"""
import logging
import os
import re
from logging.handlers import TimedRotatingFileHandler

_LOG_DIR = 'log'
_FORMATTER = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_TASK_FORMATTER = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')


class _DailyRotatingFileHandler(TimedRotatingFileHandler):
    """按自然日切分、自动清理旧文件的处理器。

    Python 3.11 的 getFilesToDelete 不支持改变分隔符的 namer，
    必须子类化并覆盖 getFilesToDelete 才能正确识别 name_YYYYMMDD.log 格式。
    """

    def namer(self, default_name: str) -> str:
        base, date_suffix = default_name.rsplit('.', 1)
        log_dirname, log_basename = os.path.split(base)
        prefix, ext = os.path.splitext(log_basename)
        return os.path.join(log_dirname, f'{prefix}_{date_suffix}{ext}')

    def getFilesToDelete(self):
        log_dir, base = os.path.split(self.baseFilename)
        prefix, _ = os.path.splitext(base)
        pattern = re.compile(rf'^{re.escape(prefix)}_(\d{{8}})\.log$')

        candidates = sorted(
            os.path.join(log_dir, f)
            for f in os.listdir(log_dir or '.')
            if pattern.match(f)
        )

        if len(candidates) <= self.backupCount:
            return []
        return candidates[:len(candidates) - self.backupCount]


def _make_daily_handler(log_file: str, backup_count: int = 14) -> _DailyRotatingFileHandler:
    """按自然日切分、保留 backup_count 天、自动清理旧文件的文件处理器。"""
    os.makedirs(_LOG_DIR, exist_ok=True)
    handler = _DailyRotatingFileHandler(
        os.path.join(_LOG_DIR, log_file),
        when='midnight',
        backupCount=backup_count,
        encoding='utf-8',
    )
    handler.suffix = '%Y%m%d'
    return handler


def _is_production() -> bool:
    return os.getenv('LOG_LEVEL', 'INFO').upper() == 'INFO'


def setup_logger(logger_name: str = 'AppLogger', log_level: str = 'INFO',
                 log_file: str = 'app.log') -> logging.Logger:
    """配置并返回一个按天轮换的日志记录器。"""
    logger = logging.getLogger(logger_name)
    effective_level = getattr(logging, os.getenv('LOG_LEVEL', log_level).upper(), logging.INFO)
    logger.setLevel(effective_level)

    if logger.handlers:
        return logger

    handler = _make_daily_handler(log_file)
    handler.setLevel(effective_level)
    handler.setFormatter(_FORMATTER)
    logger.addHandler(handler)

    if not _is_production():
        console = logging.StreamHandler()
        console.setLevel(effective_level)
        console.setFormatter(_FORMATTER)
        logger.addHandler(console)

    return logger


def setup_task_logger(logger_name: str = 'TaskManager', log_level: str = 'INFO') -> logging.Logger:
    """为任务模块配置按天轮换的日志记录器。"""
    logger = logging.getLogger(logger_name)
    effective_level = getattr(logging, os.getenv('LOG_LEVEL', log_level).upper(), logging.INFO)
    logger.setLevel(effective_level)
    logger.propagate = False

    if logger.handlers:
        return logger

    handler = _make_daily_handler(f'{logger_name}.log')
    handler.setLevel(effective_level)
    handler.setFormatter(_TASK_FORMATTER)
    logger.addHandler(handler)

    if not _is_production():
        console = logging.StreamHandler()
        console.setLevel(effective_level)
        console.setFormatter(_TASK_FORMATTER)
        logger.addHandler(console)

    return logger


def setup_retrieval_logger() -> logging.Logger:
    """配置检索操作专用日志记录器。"""
    logger_name = 'retrieval'
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    fmt = logging.Formatter('%(asctime)s - %(message)s')
    handler = _make_daily_handler(f'{logger_name}.log')
    handler.setLevel(logging.INFO)
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    return logger
