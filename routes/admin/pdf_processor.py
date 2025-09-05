from datetime import datetime
import errno
import json
import logging
import os
import tempfile
import time
import uuid

from bson.objectid import ObjectId
from flask import jsonify
from flask import render_template
from flask import request
from flask import Response
from werkzeug.utils import secure_filename

from . import admin_bp
from routes.admin.auth import admin_required
from utils.mongo_client import get_db
from utils.task_manager import task_manager


@admin_bp.route("/pdf/processor")
@admin_required
def pdf_processor_page():
    """PDF处理器页面"""
    return render_template("pdf_processor.html")


@admin_bp.route("/pdf/tasks")
@admin_required
def pdf_tasks_page():
    """PDF任务列表页面"""
    return render_template("pdf_tasks.html")


@admin_bp.route("/pdf/task/<task_id>")
@admin_required
def pdf_task_detail_page(task_id):
    """PDF任务详情页面"""
    task = task_manager.get_task_status(task_id)
    if not task:
        return render_template("404.html"), 404
    return render_template("pdf_task_detail.html", task=task)


@admin_bp.route("/api/pdf/upload", methods=["POST"])
@admin_required
def upload_pdf():
    """上传PDF文件并开始处理"""
    try:
        if "pdf_file" not in request.files:
            return jsonify({"error": "没有上传文件"}), 400

        file = request.files["pdf_file"]
        if file.filename == "":
            return jsonify({"error": "没有选择文件"}), 400

        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "只支持PDF文件"}), 400

        university_name = request.form.get("university_name", "").strip()
        if not university_name:
            return jsonify({"error": "请输入大学名称"}), 400

        # 获取处理模式
        processing_mode = request.form.get("processing_mode", "normal").strip()
        if processing_mode not in ["normal", "batch"]:
            return jsonify({"error": "无效的处理模式"}), 400

        # 保存文件到临时目录
        original_filename = file.filename
        safe_filename = secure_filename(file.filename)
        temp_filename = f"{uuid.uuid4().hex}_{safe_filename}"

        temp_dir = os.path.join(tempfile.gettempdir(), "pdf_uploads")
        os.makedirs(temp_dir, exist_ok=True)

        temp_filepath = os.path.join(temp_dir, temp_filename)
        file.save(temp_filepath)

        # 创建处理任务
        task_id = task_manager.create_pdf_processing_task(
            university_name=university_name,
            pdf_file_path=temp_filepath,
            original_filename=original_filename,
            processing_mode=processing_mode,
        )

        if task_id:
            return jsonify({"message": "任务创建成功", "task_id": task_id})
        else:
            # 清理临时文件
            try:
                os.remove(temp_filepath)
            except OSError:
                pass
            return jsonify({"error": "创建任务失败"}), 500

    except Exception as e:
        logging.error(f"[Admin API] PDF上传失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


def is_pid_running(pid: int) -> bool:
    """检查给定PID的进程是否仍在运行。"""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        # 发送信号0不会影响进程，但可以检查其是否存在
        os.kill(pid, 0)
    except OSError as err:
        if err.errno == errno.ESRCH:
            # 进程不存在
            return False
        elif err.errno == errno.EPERM:
            # 没有权限，但意味着进程存在
            return True
        else:
            # 其他操作系统错误
            raise
    return True


@admin_bp.route("/api/pdf/tasks", methods=["GET"])
@admin_required
def get_pdf_tasks():
    """获取PDF处理任务列表"""
    try:
        limit = request.args.get("limit", 50, type=int)
        tasks = task_manager.get_all_tasks(limit=limit)
        db = get_db()

        if db is not None:
            for task in tasks:
                # 检查卡在"处理中"状态的任务
                if task.get("status") == "processing":
                    pid = task.get("pid")
                    # 如果任务是"处理中"状态，但没有PID（是旧的卡住的任务），
                    # 或者有PID但进程已不存在，都标记为"已中断"
                    if not pid or not is_pid_running(pid):
                        # 进程不存在，说明任务已中断
                        task["status"] = "interrupted"
                        db.processing_tasks.update_one({"_id": ObjectId(task["_id"])}, {
                            "$set": {
                                "status": "interrupted",
                                "updated_at": datetime.utcnow(),
                                "error_message": "Task process was interrupted due to service restart or crash."
                            }
                        })
                        logging.warning(f"Task {task['_id']} was marked as interrupted because its process (PID: {pid}) is no longer running.")

                # 格式化时间
                if "created_at" in task and isinstance(task["created_at"], datetime):
                    task["created_at_str"] = task["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                if "updated_at" in task and isinstance(task["updated_at"], datetime):
                    task["updated_at_str"] = task["updated_at"].strftime("%Y-%m-%d %H:%M:%S")

        return jsonify(tasks)

    except Exception as e:
        logging.error(f"[Admin API] 获取PDF任务列表失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/pdf/task/<task_id>", methods=["GET"])
@admin_required
def get_pdf_task(task_id):
    """获取单个PDF处理任务的详细信息"""
    try:
        task = task_manager.get_task_status(task_id)
        if not task:
            return jsonify({"error": "任务不存在"}), 404

        # 格式化时间
        if "created_at" in task:
            task["created_at_str"] = task["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if "updated_at" in task:
            task["updated_at_str"] = task["updated_at"].strftime("%Y-%m-%d %H:%M:%S")

        # 格式化日志时间
        if "logs" in task:
            for log in task["logs"]:
                if "timestamp" in log:
                    log["timestamp_str"] = log["timestamp"].strftime("%H:%M:%S")

        return jsonify(task)

    except Exception as e:
        logging.error(f"[Admin API] 获取PDF任务详情失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/pdf/queue_status", methods=["GET"])
@admin_required
def get_queue_status():
    """获取处理队列状态"""
    try:
        status = task_manager.get_queue_status()
        return jsonify(status)
    except Exception as e:
        logging.error(f"[Admin API] 获取队列状态失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/pdf/task-stream/<task_id>")
@admin_required
def task_detail_stream(task_id):
    """使用SSE推送单个任务的详细更新"""

    def event_stream():
        last_task_data = None
        while True:
            try:
                task = task_manager.get_task_status(task_id)
                if not task:
                    error_data = json.dumps({"error": "Task not found"})
                    yield f"event: error\ndata: {error_data}\n\n"
                    break

                current_task_data = json.dumps(task, default=str)

                if current_task_data != last_task_data:
                    # 格式化时间戳
                    if "created_at" in task and hasattr(task["created_at"], "strftime"):
                        task["created_at_str"] = task["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                    if "updated_at" in task and hasattr(task["updated_at"], "strftime"):
                        task["updated_at_str"] = task["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
                    if "logs" in task:
                        for log in task["logs"]:
                            if "timestamp" in log and hasattr(log["timestamp"], "strftime"):
                                log["timestamp_str"] = log["timestamp"].strftime("%H:%M:%S")

                    json_data = json.dumps(task, default=str)
                    yield f"data: {json_data}\n\n"
                    last_task_data = current_task_data

                # 如果任务完成或失败，则停止推送
                if task.get("status") in ["completed", "failed"]:
                    break

            except Exception as e:
                logging.error(
                    f"Error in SSE task detail stream for task {task_id}: {e}",
                    exc_info=True,
                )
                error_data = json.dumps({"error": "An internal error occurred"})
                yield f"event: error\ndata: {error_data}\n\n"
                break

            time.sleep(30)

    return Response(event_stream(), mimetype="text/event-stream")


@admin_bp.route("/api/pdf/task/<task_id>/restart", methods=["POST"])
@admin_required
def restart_task(task_id):
    """从指定步骤重启任务"""
    try:
        data = request.get_json()

        if not data or "step_name" not in data:
            return jsonify({"error": "缺少步骤名称参数"}), 400

        step_name = data["step_name"]

        # 验证步骤名称
        valid_steps = [
            "01_pdf2img",
            "02_ocr",
            "03_translate",
            "04_analysis",
            "05_output",
        ]
        if step_name not in valid_steps:
            return jsonify({"error": f"无效的步骤名称，有效步骤: {valid_steps}"}), 400

        success = task_manager.restart_task_from_step(task_id, step_name)

        if success:
            return jsonify({"message": f"任务已设置为从步骤 {step_name} 重启"})
        else:
            return jsonify({"error": "重启任务失败"}), 500

    except Exception as e:
        logging.error(f"[Admin API] 重启任务失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/pdf/task/<task_id>/start", methods=["POST"])
@admin_required
def start_pending_task(task_id):
    """手动启动待处理的任务"""
    try:
        success = task_manager.start_pending_task(task_id)

        if success:
            return jsonify({"message": "任务已添加到处理队列"})
        else:
            return jsonify({"error": "启动任务失败"}), 500

    except Exception as e:
        logging.error(f"[Admin API] 启动任务失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/pdf/queue/process", methods=["POST"])
@admin_required
def process_queue():
    """手动触发队列处理"""
    try:
        # 恢复待处理任务到队列
        task_manager.recover_pending_tasks()
        # 处理队列
        task_manager.process_queue()
        # 获取队列状态
        queue_status = task_manager.get_queue_status()

        return jsonify({"message": "队列处理已触发", "queue_status": queue_status})

    except Exception as e:
        logging.error(f"[Admin API] 手动处理队列失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500
