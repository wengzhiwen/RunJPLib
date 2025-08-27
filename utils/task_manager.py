"""
任务管理器 - 管理PDF处理任务的异步执行
"""
from datetime import datetime
from datetime import timedelta
import threading
import time
from typing import Dict, List, Optional

from bson.objectid import ObjectId

from utils.logging_config import setup_logger
from utils.mongo_client import get_mongo_client
from utils.pdf_processor import run_pdf_processor

logger = setup_logger(logger_name="TaskManager", log_level="INFO")


class TaskManager:
    """任务管理器 - 单例模式"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TaskManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        self.running_tasks: Dict[str, threading.Thread] = {}
        self.task_queue: List[str] = []
        self.max_concurrent_tasks = 1  # 暂时只允许一个任务并发执行
        self.cleanup_thread = None
        self.queue_processor_thread = None
        self.start_cleanup_service()
        self.start_queue_processor()
        self.recover_pending_tasks()

    def start_cleanup_service(self):
        """启动清理服务，定期清理过期任务"""
        def cleanup_worker():
            while True:
                try:
                    self.cleanup_old_tasks()
                    time.sleep(3600)  # 每小时检查一次
                except Exception as e:
                    logger.error(f"清理服务错误: {e}")
                    time.sleep(300)  # 错误时5分钟后重试

        if not self.cleanup_thread or not self.cleanup_thread.is_alive():
            self.cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
            self.cleanup_thread.start()
            logger.info("任务清理服务已启动")

    def cleanup_old_tasks(self):
        """清理7天前的任务记录"""
        try:
            client = get_mongo_client()
            if not client:
                return

            db = client.RunJPLib
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            
            # 只删除已完成或失败的任务
            result = db.processing_tasks.delete_many({
                "created_at": {"$lt": cutoff_date},
                "status": {"$in": ["completed", "failed"]}
            })
            
            if result.deleted_count > 0:
                logger.info(f"已清理 {result.deleted_count} 个过期任务")
                
        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")

    def recover_pending_tasks(self):
        """恢复数据库中的待处理任务到队列中"""
        try:
            client = get_mongo_client()
            if not client:
                logger.warning("无法连接到数据库，跳过任务恢复")
                return

            db = client.RunJPLib
            
            # 查找所有待处理的任务
            pending_tasks = db.processing_tasks.find(
                {"status": "pending"},
                {"_id": 1}
            ).sort("created_at", 1)  # 按创建时间排序，早创建的先处理
            
            recovered_count = 0
            for task_doc in pending_tasks:
                task_id = str(task_doc["_id"])
                if task_id not in self.task_queue:
                    self.task_queue.append(task_id)
                    recovered_count += 1
            
            if recovered_count > 0:
                logger.info(f"已恢复 {recovered_count} 个待处理任务到队列中")
                # 尝试启动任务处理
                self.process_queue()
            else:
                logger.info("没有待恢复的任务")
                
        except Exception as e:
            logger.error(f"恢复待处理任务失败: {e}")

    def start_queue_processor(self):
        """启动队列处理服务，定期检查和处理队列"""
        def queue_processor_worker():
            while True:
                try:
                    # 定期检查是否有新的待处理任务
                    self.recover_pending_tasks()
                    # 尝试处理队列
                    self.process_queue()
                    time.sleep(60)  # 每分钟检查一次
                except Exception as e:
                    logger.error(f"队列处理服务错误: {e}")
                    time.sleep(30)  # 错误时30秒后重试

        if not self.queue_processor_thread or not self.queue_processor_thread.is_alive():
            self.queue_processor_thread = threading.Thread(target=queue_processor_worker, daemon=True)
            self.queue_processor_thread.start()
            logger.info("任务队列处理服务已启动")

    def create_task(self, university_name: str, pdf_file_path: str, original_filename: str) -> Optional[str]:
        """
        创建新的处理任务
        
        Args:
            university_name: 大学名称
            pdf_file_path: PDF文件路径
            original_filename: 原始文件名
            
        Returns:
            str: 任务ID，失败时返回None
        """
        try:
            client = get_mongo_client()
            if not client:
                logger.error("无法连接到数据库")
                return None

            db = client.RunJPLib
            
            # 创建任务文档
            task_doc = {
                "university_name": university_name,
                "original_filename": original_filename,
                "pdf_file_path": pdf_file_path,
                "status": "pending",  # pending, processing, completed, failed
                "current_step": "",
                "progress": 0,
                "error_message": "",
                "logs": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = db.processing_tasks.insert_one(task_doc)
            task_id = str(result.inserted_id)
            
            logger.info(f"任务已创建: {task_id} - {university_name}")
            
            # 将任务添加到队列
            self.task_queue.append(task_id)
            self.process_queue()
            
            return task_id
            
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            return None

    def process_queue(self):
        """处理任务队列"""
        # 清理已完成的线程
        finished_tasks = [task_id for task_id, thread in self.running_tasks.items() 
                         if not thread.is_alive()]
        for task_id in finished_tasks:
            del self.running_tasks[task_id]

        # 检查是否可以启动新任务
        if (len(self.running_tasks) < self.max_concurrent_tasks and 
            self.task_queue):
            
            task_id = self.task_queue.pop(0)
            self._start_task(task_id)

    def _start_task(self, task_id: str):
        """启动单个任务"""
        try:
            client = get_mongo_client()
            if not client:
                logger.error("无法连接到数据库")
                return

            db = client.RunJPLib
            task = db.processing_tasks.find_one({"_id": ObjectId(task_id)})
            
            if not task:
                logger.error(f"任务不存在: {task_id}")
                return

            # 更新任务状态为处理中
            db.processing_tasks.update_one(
                {"_id": ObjectId(task_id)},
                {
                    "$set": {
                        "status": "processing",
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            # 创建处理线程
            def process_worker():
                try:
                    logger.info(f"开始处理任务: {task_id}")
                    restart_from_step = task.get("restart_from_step")
                    success = run_pdf_processor(
                        task_id=task_id,
                        university_name=task["university_name"],
                        pdf_file_path=task["pdf_file_path"],
                        restart_from_step=restart_from_step
                    )
                    
                    if success:
                        logger.info(f"任务处理成功: {task_id}")
                    else:
                        logger.error(f"任务处理失败: {task_id}")
                        
                except Exception as e:
                    logger.error(f"任务处理异常: {task_id} - {e}")
                    # 更新任务状态为失败
                    try:
                        client = get_mongo_client()
                        if client:
                            db = client.RunJPLib
                            db.processing_tasks.update_one(
                                {"_id": ObjectId(task_id)},
                                {
                                    "$set": {
                                        "status": "failed",
                                        "error_message": str(e),
                                        "updated_at": datetime.utcnow()
                                    }
                                }
                            )
                    except Exception as update_e:
                        logger.error(f"更新任务状态失败: {update_e}")
                finally:
                    # 处理队列中的下一个任务
                    self.process_queue()

            thread = threading.Thread(target=process_worker, daemon=True)
            thread.start()
            
            self.running_tasks[task_id] = thread
            logger.info(f"任务线程已启动: {task_id}")

        except Exception as e:
            logger.error(f"启动任务失败: {task_id} - {e}")

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        try:
            client = get_mongo_client()
            if not client:
                return None

            db = client.RunJPLib
            task = db.processing_tasks.find_one({"_id": ObjectId(task_id)})
            
            if task:
                task["_id"] = str(task["_id"])
                return task
            return None
            
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return None

    def get_all_tasks(self, limit: int = 50) -> List[dict]:
        """获取所有任务列表"""
        try:
            client = get_mongo_client()
            if not client:
                return []

            db = client.RunJPLib
            cursor = db.processing_tasks.find().sort("created_at", -1).limit(limit)
            
            tasks = []
            for task in cursor:
                task["_id"] = str(task["_id"])
                # 简化日志，只返回最新的几条
                if "logs" in task and len(task["logs"]) > 10:
                    task["logs"] = task["logs"][-10:]
                tasks.append(task)
                
            return tasks
            
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return []

    def restart_task_from_step(self, task_id: str, step_name: str) -> bool:
        """从指定步骤重启任务"""
        try:
            client = get_mongo_client()
            if not client:
                logger.error("无法连接到数据库")
                return False

            db = client.RunJPLib
            task = db.processing_tasks.find_one({"_id": ObjectId(task_id)})
            
            if not task:
                logger.error(f"任务不存在: {task_id}")
                return False
            
            # 检查任务状态，只有完成或失败的任务才能重启
            if task["status"] not in ["completed", "failed"]:
                logger.error(f"任务状态不允许重启: {task['status']}")
                return False
            
            # 验证步骤名称
            valid_steps = ["01_pdf2img", "02_ocr", "03_translate", "04_analysis", "05_output"]
            if step_name not in valid_steps:
                logger.error(f"无效的步骤名称: {step_name}")
                return False
            
            # 更新任务状态，设置重启步骤
            db.processing_tasks.update_one(
                {"_id": ObjectId(task_id)},
                {
                    "$set": {
                        "status": "pending",
                        "restart_from_step": step_name,
                        "current_step": "",
                        "progress": 0,
                        "error_message": "",
                        "updated_at": datetime.utcnow()
                    },
                    "$push": {
                        "logs": {
                            "timestamp": datetime.utcnow(),
                            "level": "INFO",
                            "message": f"任务被设置为从步骤 {step_name} 重启"
                        }
                    }
                }
            )
            
            # 将任务添加到队列
            self.task_queue.append(task_id)
            self.process_queue()
            
            logger.info(f"任务 {task_id} 已设置为从步骤 {step_name} 重启")
            return True
            
        except Exception as e:
            logger.error(f"重启任务失败: {task_id} - {e}")
            return False

    def start_pending_task(self, task_id: str) -> bool:
        """手动启动待处理的任务"""
        try:
            client = get_mongo_client()
            if not client:
                logger.error("无法连接到数据库")
                return False

            db = client.RunJPLib
            task = db.processing_tasks.find_one({"_id": ObjectId(task_id)})
            
            if not task:
                logger.error(f"任务不存在: {task_id}")
                return False
            
            # 检查任务状态，只有待处理的任务才能手动启动
            if task["status"] != "pending":
                logger.error(f"任务状态不允许启动: {task['status']}")
                return False
            
            # 检查任务是否已在队列中
            if task_id in self.task_queue:
                logger.info(f"任务已在队列中: {task_id}")
                return True
            
            # 将任务添加到队列
            self.task_queue.append(task_id)
            self.process_queue()
            
            # 添加日志
            db.processing_tasks.update_one(
                {"_id": ObjectId(task_id)},
                {
                    "$push": {
                        "logs": {
                            "timestamp": datetime.utcnow(),
                            "level": "INFO",
                            "message": "任务被手动添加到处理队列"
                        }
                    },
                    "$set": {
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"任务 {task_id} 已手动添加到处理队列")
            return True
            
        except Exception as e:
            logger.error(f"手动启动任务失败: {task_id} - {e}")
            return False

    def cancel_task(self, task_id: str) -> bool:
        """取消任务（暂不实现，根据需求文档）"""
        # 根据需求文档，暂不提供中断任务的功能
        logger.warning(f"任务取消功能暂未实现: {task_id}")
        return False

    def get_queue_status(self) -> dict:
        """获取队列状态"""
        return {
            "running_tasks": len(self.running_tasks),
            "queued_tasks": len(self.task_queue),
            "max_concurrent": self.max_concurrent_tasks
        }


# 全局任务管理器实例
task_manager = TaskManager()
