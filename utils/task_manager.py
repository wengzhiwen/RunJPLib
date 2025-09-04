"""
任务管理器 - 管理PDF处理任务的异步执行
"""
from datetime import datetime
from datetime import timedelta
import os
import threading
import time
from typing import Dict, List, Optional

from bson.objectid import ObjectId

from utils.logging_config import setup_task_logger
from utils.mongo_client import get_db
from utils.pdf_processor import run_pdf_processor

task_logger = setup_task_logger("TaskManager")


class TaskManager:
    """任务管理器 - 单例模式"""
    _instance = None
    _lock = threading.Lock()

    # 将并发数和初始化标志提升为类变量，以避免多线程初始化时的竞争条件
    _initialized = False
    try:
        max_concurrent_tasks = int(os.getenv("PDF_MAX_CONCURRENT_TASKS", 1))
    except (ValueError, TypeError):
        max_concurrent_tasks = 1

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TaskManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        with self._lock:
            if self._initialized:
                return

            self.running_tasks: Dict[str, threading.Thread] = {}
            self.task_queue: List[str] = []
            task_logger.info(f"Task Manager initialized. Max concurrent tasks set to: {self.max_concurrent_tasks}")

            self.cleanup_thread = None
            self.queue_processor_thread = None
            self.start_cleanup_service()
            self.start_queue_processor()
            self.recover_pending_tasks()
            
            self.__class__._initialized = True

    def notify_task_is_waiting(self, task_id: str):
        """
        由工作线程调用，通知管理器一个任务已进入等待状态。
        这会触发一次队列检查，以决定是否可以启动新任务。
        """
        task_logger.info(f"Notification received: Task {task_id} is waiting. Checking queue...")
        self.process_queue()

    def start_cleanup_service(self):
        """启动清理服务，定期清理过期任务"""

        def cleanup_worker():
            while True:
                try:
                    self.cleanup_old_tasks()
                    time.sleep(3600)  # 每小时检查一次
                except Exception as e:
                    task_logger.error(f"Cleanup service error: {e}")
                    time.sleep(300)  # 错误时5分钟后重试

        if not self.cleanup_thread or not self.cleanup_thread.is_alive():
            self.cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True, name="CleanupThread")
            self.cleanup_thread.start()
            task_logger.info("Task cleanup service started.")

    def cleanup_old_tasks(self):
        """清理7天前的任务记录"""
        try:
            db = get_db()
            if db is None:
                return

            cutoff_date = datetime.utcnow() - timedelta(days=7)

            # 只删除已完成或失败的任务
            result = db.processing_tasks.delete_many({"created_at": {"$lt": cutoff_date}, "status": {"$in": ["completed", "failed"]}})

            if result.deleted_count > 0:
                task_logger.info(f"Cleaned up {result.deleted_count} old tasks.")

        except Exception as e:
            task_logger.error(f"Failed to clean up old tasks: {e}")

    def recover_pending_tasks(self):
        """恢复数据库中的待处理任务到队列中"""
        try:
            db = get_db()
            if db is None:
                task_logger.warning("Cannot connect to DB, skipping task recovery.")
                return

            # 查找所有待处理的任务，按创建时间排序
            pending_tasks = db.processing_tasks.find({"status": "pending"}, {"_id": 1}).sort("created_at", 1)

            recovered_count = 0
            for task_doc in pending_tasks:
                task_id = str(task_doc["_id"])
                if task_id not in self.task_queue:
                    self.task_queue.append(task_id)
                    recovered_count += 1

            if recovered_count > 0:
                task_logger.info(f"Recovered {recovered_count} pending tasks to the queue.")
                self.process_queue()
            else:
                task_logger.info("No pending tasks to recover.")

        except Exception as e:
            task_logger.error(f"Failed to recover pending tasks: {e}")

    def start_queue_processor(self):
        """启动队列处理服务，定期检查和处理队列"""

        def queue_processor_worker():
            consecutive_errors = 0
            while True:
                try:
                    # 队列为空时检查新的待处理任务
                    if not self.task_queue:
                        self.recover_pending_tasks()

                    self.process_queue()

                    # 根据系统负载动态调整检查频率
                    if self.running_tasks or self.task_queue:
                        time.sleep(30)  # 忙碌时30秒检查一次
                    else:
                        time.sleep(300)  # 空闲时5分钟检查一次

                    consecutive_errors = 0  # 重置错误计数

                except Exception as e:
                    consecutive_errors += 1
                    task_logger.error(f"Queue processor service error: {e}")

                    # 指数退避策略
                    sleep_time = min(30 * (2**consecutive_errors), 600)  # 最大10分钟
                    time.sleep(sleep_time)

        if not self.queue_processor_thread or not self.queue_processor_thread.is_alive():
            self.queue_processor_thread = threading.Thread(target=queue_processor_worker, daemon=True, name="QueueProcessorThread")
            self.queue_processor_thread.start()
            task_logger.info("Task queue processor service started.")

    def create_task(self, university_name: str, pdf_file_path: str, original_filename: str, processing_mode: str = "normal") -> Optional[str]:
        """
        创建新的处理任务
        
        参数:
            university_name: 大学名称
            pdf_file_path: PDF文件路径
            original_filename: 原始文件名
            processing_mode: 处理模式 ("normal" | "batch")
            
        返回:
            任务ID字符串，失败时返回None
        """
        try:
            db = get_db()
            if db is None:
                task_logger.error("Cannot connect to DB, failed to create task.")
                return None

            # 创建任务文档
            task_doc = {
                "university_name": university_name,
                "original_filename": original_filename,
                "pdf_file_path": pdf_file_path,
                "processing_mode": processing_mode,  # 处理模式: normal, batch
                "status": "pending",  # 任务状态: pending, processing, completed, failed
                "current_step": "",
                "progress": 0,
                "error_message": "",
                "logs": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            result = db.processing_tasks.insert_one(task_doc)
            task_id = str(result.inserted_id)

            task_logger.info(f"Task created: {task_id} for {university_name}, mode: {processing_mode}.")

            # 将任务添加到队列
            self.task_queue.append(task_id)
            task_logger.info(f"Task {task_id} added to queue. Queue size: {len(self.task_queue)}.")
            self.process_queue()

            return task_id

        except Exception as e:
            task_logger.error(f"Failed to create task: {e}")
            return None

    def process_queue(self):
        """处理任务队列"""
        with self._lock:
            # 清理已完成的线程
            finished_tasks = [task_id for task_id, thread in self.running_tasks.items() if not thread.is_alive()]
            for task_id in finished_tasks:
                task_logger.info(f"Task {task_id} thread finished. Removing from running tasks.")
                del self.running_tasks[task_id]

            # 检查是否可以启动新任务
            available_slots = self.max_concurrent_tasks - len(self.running_tasks)
            if available_slots <= 0:
                task_logger.info(f"No available slots. Running tasks: {len(self.running_tasks)}, Max: {self.max_concurrent_tasks}.")
                return

            if not self.task_queue:
                task_logger.info("Queue is empty. No new tasks to start.")
                return

            task_logger.info(f"Available slots: {available_slots}. Queue size: {len(self.task_queue)}. Attempting to start new task(s).")

            # 启动新任务
            num_to_start = min(available_slots, len(self.task_queue))
            for _ in range(num_to_start):
                task_id = self.task_queue.pop(0)
                self._start_task(task_id)

    def _start_task(self, task_id: str):
        """启动单个任务"""
        try:
            db = get_db()
            if db is None:
                task_logger.error(f"Cannot connect to DB, unable to start task {task_id}.")
                return
            task = db.processing_tasks.find_one({"_id": ObjectId(task_id)})

            if not task:
                task_logger.error(f"Task {task_id} not found in DB.")
                return

            # 更新任务状态为处理中
            db.processing_tasks.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "processing", "updated_at": datetime.utcnow()}})

            # 创建处理线程
            def process_worker():
                try:
                    task_logger.info(f"Worker starts processing task: {task_id}")
                    restart_from_step = task.get("restart_from_step")
                    processing_mode = task.get("processing_mode", "normal")
                    success = run_pdf_processor(task_id=task_id,
                                                university_name=task["university_name"],
                                                pdf_file_path=task["pdf_file_path"],
                                                restart_from_step=restart_from_step,
                                                processing_mode=processing_mode,
                                                task_manager_instance=self)

                    if success:
                        task_logger.info(f"Task processing completed successfully: {task_id}")
                    else:
                        task_logger.error(f"Task processing failed: {task_id}")

                except Exception as e:
                    task_logger.error(f"Exception in task worker {task_id}: {e}", exc_info=True)
                    # 更新任务状态为失败
                    try:
                        db_conn = get_db()
                        if db_conn:
                            db_conn.processing_tasks.update_one({"_id": ObjectId(task_id)},
                                                                {"$set": {
                                                                    "status": "failed",
                                                                    "error_message": str(e),
                                                                    "updated_at": datetime.utcnow()
                                                                }})
                    except Exception as update_e:
                        task_logger.error(f"Failed to update task status to 'failed' for {task_id}: {update_e}")
                finally:
                    # 任务完成后，再次触发队列处理
                    task_logger.info(f"Task {task_id} finished. Triggering queue processing.")
                    self.process_queue()

            thread = threading.Thread(target=process_worker, daemon=True, name=f"TaskThread-{task_id}")
            self.running_tasks[task_id] = thread
            thread.start()

            task_logger.info(f"Task {task_id} started in a new thread. Running tasks: {len(self.running_tasks)}.")

        except Exception as e:
            task_logger.error(f"Failed to start task {task_id}: {e}", exc_info=True)

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        try:
            db = get_db()
            if db is None:
                return None
            task = db.processing_tasks.find_one({"_id": ObjectId(task_id)})

            if task:
                task["_id"] = str(task["_id"])
                return task
            return None

        except Exception as e:
            task_logger.error(f"Failed to get task status for {task_id}: {e}")
            return None

    def get_all_tasks(self, limit: int = 50) -> List[dict]:
        """获取所有任务列表"""
        try:
            db = get_db()
            if db is None:
                return []
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
            task_logger.error(f"Failed to get all tasks: {e}")
            return []

    def restart_task_from_step(self, task_id: str, step_name: str) -> bool:
        """从指定步骤重启任务"""
        try:
            db = get_db()
            if db is None:
                task_logger.error("Cannot connect to DB, failed to restart task.")
                return False
            task = db.processing_tasks.find_one({"_id": ObjectId(task_id)})

            if not task:
                task_logger.error(f"Task {task_id} not found, cannot restart.")
                return False

            # 只有完成或失败的任务才能重启
            if task["status"] not in ["completed", "failed"]:
                task_logger.error(f"Task {task_id} is not in a restartable state: {task['status']}")
                return False

            # 验证步骤名称
            valid_steps = ["01_pdf2img", "02_ocr", "03_translate", "04_analysis", "05_output"]
            if step_name not in valid_steps:
                task_logger.error(f"Invalid restart step name: {step_name}")
                return False

            # 更新任务状态，设置重启步骤
            db.processing_tasks.update_one({"_id": ObjectId(task_id)}, {
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
                        "message": f"Task scheduled to restart from step: {step_name}"
                    }
                }
            })

            # 将任务添加到队列
            self.task_queue.append(task_id)
            self.process_queue()

            task_logger.info(f"Task {task_id} has been scheduled to restart from step {step_name}.")
            return True

        except Exception as e:
            task_logger.error(f"Failed to restart task {task_id}: {e}")
            return False

    def start_pending_task(self, task_id: str) -> bool:
        """手动启动待处理的任务"""
        try:
            db = get_db()
            if db is None:
                task_logger.error("Cannot connect to DB, failed to start pending task.")
                return False
            task = db.processing_tasks.find_one({"_id": ObjectId(task_id)})

            if not task:
                task_logger.error(f"Task {task_id} not found, cannot start.")
                return False

            # 只有待处理的任务才能手动启动
            if task["status"] != "pending":
                task_logger.error(f"Task {task_id} is not in pending state: {task['status']}")
                return False

            if task_id in self.task_queue:
                task_logger.info(f"Task {task_id} is already in the queue.")
                return True

            # 将任务添加到队列
            self.task_queue.append(task_id)
            self.process_queue()

            # 添加日志
            db.processing_tasks.update_one({"_id": ObjectId(task_id)}, {
                "$push": {
                    "logs": {
                        "timestamp": datetime.utcnow(),
                        "level": "INFO",
                        "message": "Task manually added to the processing queue"
                    }
                },
                "$set": {
                    "updated_at": datetime.utcnow()
                }
            })

            task_logger.info(f"Task {task_id} has been manually added to the queue.")
            return True

        except Exception as e:
            task_logger.error(f"Failed to manually start task {task_id}: {e}")
            return False

    def cancel_task(self, task_id: str) -> bool:
        """取消任务（暂不实现）"""
        # 根据需求文档，暂不提供中断任务的功能
        task_logger.warning(f"Task cancellation is not implemented. Request for task {task_id} ignored.")
        return False

    def get_queue_status(self) -> dict:
        """获取队列状态"""
        return {"running_tasks": len(self.running_tasks), "queued_tasks": len(self.task_queue), "max_concurrent": self.max_concurrent_tasks}


# 全局任务管理器实例
task_manager = TaskManager()
