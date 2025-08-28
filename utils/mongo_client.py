import logging
import os
import threading
from typing import Optional

from pymongo import MongoClient
from pymongo.server_api import ServerApi

# 全局MongoDB客户端实例
_mongo_client: Optional[MongoClient] = None
_client_lock = threading.Lock()


def get_mongo_client():
    """
    获取MongoDB客户端实例 - 使用单例模式和连接池
    """
    global _mongo_client
    
    # 如果客户端已存在且连接有效，直接返回
    if _mongo_client is not None:
        try:
            # 简单的健康检查，不使用ping命令减少网络开销
            _mongo_client.admin.command('ismaster')
            return _mongo_client
        except Exception:
            # 连接已断开，需要重新创建
            _mongo_client = None
    
    # 使用锁确保线程安全
    with _client_lock:
        # 双重检查，防止并发创建多个客户端
        if _mongo_client is not None:
            try:
                _mongo_client.admin.command('ismaster')
                return _mongo_client
            except Exception:
                _mongo_client = None
        
        # 创建新的客户端连接
        mongo_uri = os.getenv("MONGODB_URI")
        if not mongo_uri:
            logging.error("MONGODB_URI environment variable not set.")
            return None

        try:
            # 创建客户端时配置连接池参数
            _mongo_client = MongoClient(
                mongo_uri, 
                server_api=ServerApi('1'),
                maxPoolSize=10,  # 最大连接池大小
                minPoolSize=1,   # 最小连接池大小
                maxIdleTimeMS=300000,  # 连接最大空闲时间（5分钟）
                waitQueueTimeoutMS=10000,  # 等待连接超时时间
                serverSelectionTimeoutMS=5000,  # 服务器选择超时时间
                connectTimeoutMS=10000,  # 连接超时时间
                socketTimeoutMS=30000,   # Socket超时时间
            )
            
            # 测试连接 - 只在初次创建时执行一次ping
            _mongo_client.admin.command('ping')
            logging.info("Successfully connected to MongoDB with connection pooling!")
            return _mongo_client
            
        except Exception as e:
            logging.error(f"Error connecting to MongoDB: {e}")
            _mongo_client = None
            return None


def get_db():
    """
    返回RunJPLib数据库实例
    """
    client = get_mongo_client()
    return client.get_database("RunJPLib") if client else None


def close_mongo_client():
    """
    关闭MongoDB客户端连接（在应用程序结束时调用）
    """
    global _mongo_client
    with _client_lock:
        if _mongo_client is not None:
            _mongo_client.close()
            _mongo_client = None
            logging.info("MongoDB client connection closed.")


# 应用程序结束时的清理函数
import atexit
atexit.register(close_mongo_client)