from datetime import datetime
from datetime import timedelta
from functools import wraps
import json
import logging
import os
import tempfile
import time
import uuid

from bson.objectid import ObjectId
from flask import Blueprint
from flask import jsonify
from flask import make_response
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import url_for
from flask_jwt_extended import create_access_token
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import set_access_cookies
from flask_jwt_extended import unset_jwt_cookies
from flask_jwt_extended import verify_jwt_in_request
from werkzeug.utils import secure_filename

from utils.blog_generator import BlogGenerator
from utils.mongo_client import get_mongo_client
from utils.task_manager import task_manager

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates/admin")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):
        is_api_request = request.path.startswith("/admin/api/")
        try:
            verify_jwt_in_request(locations=["headers", "cookies"])
            identity = get_jwt_identity()
            if identity != "admin":
                logging.warning("A non-admin identity was found in a valid JWT.")
                if is_api_request:
                    return jsonify(msg="需要管理员权限"), 403
                else:
                    return redirect(url_for("admin.login"))
        except Exception as e:
            logging.warning(f"JWT validation failed for path '{request.path}': {e}")
            if is_api_request:
                return jsonify(msg="Token无效或已过期"), 401
            else:
                return redirect(url_for("admin.login"))
        return fn(*args, **kwargs)

    return wrapper


@admin_bp.route("/")
@admin_required
def dashboard():
    """仪表盘路由，展示统计数据"""
    client = get_mongo_client()
    if not client:
        logging.error("仪表盘无法连接到数据库")
        return render_template("dashboard.html", error="数据库连接失败")

    db = client.RunJPLib
    stats = {}

    try:
        # 1. 收录的学校入学信息数量
        stats["university_count"] = db.universities.count_documents({})

        # 2. blog数量
        stats["blog_count"] = db.blogs.count_documents({})

        # 定义24小时的时间范围
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        query_24h = {"timestamp": {"$gte": twenty_four_hours_ago}}

        # 3. 最近24小时访问的唯一ip数量
        # 使用 distinct 方法获取唯一的IP地址列表，然后计算其长度
        unique_ips = db.access_logs.distinct("ip", query_24h)
        stats["unique_ip_count_24h"] = len(unique_ips)

        # 4. 最近24小时入学信息页的被访问次数
        query_uni_24h = {
            "timestamp": {
                "$gte": twenty_four_hours_ago
            },
            "page_type": "university",
        }
        stats["university_views_24h"] = db.access_logs.count_documents(query_uni_24h)

        # 5. 最近24小时blog页的被访问次数
        query_blog_24h = {
            "timestamp": {
                "$gte": twenty_four_hours_ago
            },
            "page_type": "blog",
        }
        stats["blog_views_24h"] = db.access_logs.count_documents(query_blog_24h)

    except Exception as e:
        logging.error(f"查询仪表盘统计数据时出错: {e}", exc_info=True)
        return render_template("dashboard.html", error="查询统计数据时出错")

    return render_template("dashboard.html", stats=stats)


@admin_bp.route("/login")
def login():
    return render_template("login.html")


@admin_bp.route("/logout")
def logout():
    response = make_response(redirect(url_for("admin.login")))
    unset_jwt_cookies(response)
    return response


@admin_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    if not data:
        logging.error("登录失败: 请求体不是有效的JSON或Content-Type头缺失。")
        return jsonify({"msg": "无效的请求格式"}), 400
    access_code = data.get("access_code")
    env_access_code = os.getenv("ACCESS_CODE")
    if not env_access_code:
        logging.error("严重安全配置错误: 环境变量 ACCESS_CODE 未设置。")
        return jsonify({"msg": "服务器配置错误"}), 500
    if not access_code or access_code != env_access_code:
        logging.warning("收到一个错误的访问码。")
        return jsonify({"msg": "访问码错误"}), 401
    logging.info("管理员登录成功。")
    access_token = create_access_token(identity="admin")
    response = jsonify(msg="登录成功")
    set_access_cookies(response, access_token)
    return response


@admin_bp.route("/api/verify_token")
@admin_required
def verify_token():
    return jsonify(status="ok")


# --- Data Management Pages ---
@admin_bp.route("/manage/universities")
@admin_required
def manage_universities_page():
    return render_template("manage_universities.html")


@admin_bp.route("/manage/blogs")
@admin_required
def manage_blogs_page():
    return render_template("manage_blogs.html")


# --- Data Management APIs ---
@admin_bp.route("/api/universities", methods=["GET"])
@admin_required
def get_universities():
    client = get_mongo_client()
    if not client:
        logging.error("[Admin API] Get universities failed: DB connection error.")
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    try:
        logging.debug("[Admin API] Fetching universities from database...")
        projection = {"content": 0, "source_path": 0}
        # 优化排序：按 _id 逆序排列，实现按创建时间倒序
        cursor = db.universities.find({}, projection).sort("_id", -1)

        universities = list(cursor)

        for u in universities:
            u["_id"] = str(u["_id"])

        logging.info(f"[Admin API] Successfully fetched {len(universities)} university documents.")
        if universities:
            logging.debug(f"[Admin API] First university document sample: {universities[0]}")

        return jsonify(universities)
    except Exception as e:
        logging.error(
            f"[Admin API] An exception occurred while fetching universities: {e}",
            exc_info=True,
        )
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/edit_university/<university_id>", methods=["GET", "POST"])
@admin_required
def edit_university(university_id):
    """
    编辑大学信息的页面和处理逻辑
    GET: 显示编辑表单
    POST: 更新大学信息
    """
    client = get_mongo_client()
    if not client:
        return render_template("edit_university.html", error="数据库连接失败")
    db = client.RunJPLib

    try:
        object_id = ObjectId(university_id)
    except Exception:
        return render_template("404.html"), 404

    if request.method == "POST":
        university_name = request.form.get("university_name", "").strip()
        is_premium = request.form.get("is_premium") == "true"
        basic_analysis_report = request.form.get("basic_analysis_report", "").strip()

        if not university_name:
            university = db.universities.find_one({"_id": object_id})
            return render_template("edit_university.html", university=university, error="大学名称不能为空")

        update_data = {
            "$set": {
                "university_name": university_name,
                "is_premium": is_premium,
                "content.report_md": basic_analysis_report,
                "last_modified": datetime.utcnow(),
            }
        }

        db.universities.update_one({"_id": object_id}, update_data)
        logging.info(f"University with ID {university_id} was updated.")
        return redirect(url_for("admin.manage_universities_page"))

    # GET 请求
    university = db.universities.find_one({"_id": object_id})
    if not university:
        return render_template("404.html"), 404

    return render_template("edit_university.html", university=university)


@admin_bp.route("/api/universities/<item_id>", methods=["DELETE"])
@admin_required
def delete_university(item_id):
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    db.universities.delete_one({"_id": ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route("/api/universities", methods=["DELETE"])
@admin_required
def clear_universities():
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    db.universities.delete_many({})
    return jsonify({"message": "数据集合已清空"})


@admin_bp.route("/api/blogs", methods=["GET"])
@admin_required
def get_blogs():
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    cursor = db.blogs.find({}).sort("publication_date", -1)
    blogs = []
    for b in cursor:
        b["_id"] = str(b["_id"])
        html_status = "未生成"
        md_last_updated = b.get("md_last_updated")
        html_last_updated = b.get("html_last_updated")
        if html_last_updated:
            html_status = "最新"
            if md_last_updated and md_last_updated > html_last_updated:
                html_status = "待更新"
        b["html_status"] = html_status
        if md_last_updated:
            b["md_last_updated"] = md_last_updated.strftime("%Y-%m-%d %H:%M:%S")
        if html_last_updated:
            b["html_last_updated"] = html_last_updated.strftime("%Y-%m-%d %H:%M:%S")
        b.pop("content_md", None)
        b.pop("content_html", None)
        blogs.append(b)
    return jsonify(blogs)


@admin_bp.route("/api/blogs/<item_id>", methods=["DELETE"])
@admin_required
def delete_blog(item_id):
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    db.blogs.delete_one({"_id": ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route("/api/blogs", methods=["DELETE"])
@admin_required
def clear_blogs():
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    db.blogs.delete_many({})
    return jsonify({"message": "数据集合已清空"})


# --- Blog Creator ---


@admin_bp.route("/blog/create")
@admin_required
def create_blog_page():
    """Renders the blog creation page."""
    return render_template("create_blog.html")


@admin_bp.route("/api/universities/search", methods=["GET"])
@admin_required
def search_universities():
    """
    Searches for universities by name.
    Accepts a 'q' query parameter for the search term.
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    try:
        # Search for universities where the name contains the query string (case-insensitive)
        universities = list(db.universities.find(
            {
                "university_name": {
                    "$regex": query,
                    "$options": "i"
                }
            },
            {
                "_id": 1,
                "university_name": 1
            },
        ).limit(20))  # Limit to 20 results for performance

        for u in universities:
            u["_id"] = str(u["_id"])

        return jsonify(universities)
    except Exception as e:
        logging.error(f"[Admin API] University search failed: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/blog/generate", methods=["POST"])
@admin_required
def generate_blog():
    """
    Generates blog content using the AI generator.
    Expects a JSON payload with 'university_ids', 'user_prompt', and 'system_prompt'.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求格式"}), 400

    university_ids = data.get("university_ids", [])
    user_prompt = data.get("user_prompt", "")
    system_prompt = data.get("system_prompt", "")
    mode = data.get("mode", "expand")  # Default to expand for safety

    if not system_prompt:
        return jsonify({"error": "系统提示词不能为空"}), 400

    # Validate inputs based on mode
    if mode in ["expand", "compare"] and not university_ids:
        return jsonify({"error": "该模式需要至少选择一所大学"}), 400
    if mode == "compare" and len(university_ids) < 2:
        return jsonify({"error": "对比分析模式需要至少选择两所大学"}), 400
    if mode == "user_prompt_only" and not user_prompt:
        return jsonify({"error": "该模式需要填写用户提示词"}), 400

    try:
        generator = BlogGenerator()
        result = generator.generate_blog_content(mode, university_ids, user_prompt, system_prompt)
        if result:
            return jsonify(result)
        else:
            return jsonify({"error": "生成文章失败"}), 500
    except Exception as e:
        logging.error(f"[Admin API] Blog generation failed: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/blog/save", methods=["POST"])
@admin_required
def save_blog():
    """
    Saves a new blog post to the database.
    Expects a JSON payload with 'title' and 'content_md'.
    """
    data = request.get_json()
    if not data or "title" not in data or "content_md" not in data:
        return jsonify({"error": "无效的请求格式，需要'title'和'content_md'"}), 400

    title = data["title"].strip()
    content_md = data["content_md"].strip()

    if not title or not content_md:
        return jsonify({"error": "标题和内容不能为空"}), 400

    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    try:
        # Create a URL-friendly title
        url_title = title.lower().replace(" ", "-").replace("/", "-")
        # Remove any characters that are not safe for URLs
        url_title = "".join(c for c in url_title if c.isalnum() or c == "-")

        new_blog = {
            "title": title,
            "url_title": url_title,
            "publication_date": datetime.now().strftime("%Y-%m-%d"),
            "created_at": datetime.now(),
            "md_last_updated": datetime.now(),
            "html_last_updated": None,
            "content_md": content_md,
            "content_html": None,
        }

        result = db.blogs.insert_one(new_blog)
        logging.info(f"New blog post created with ID: {result.inserted_id}")

        return jsonify({"message": "文章保存成功", "blog_id": str(result.inserted_id)})
    except Exception as e:
        logging.error(f"[Admin API] Failed to save blog: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/blog/edit/<blog_id>", methods=["GET", "POST"])
@admin_required
def edit_blog(blog_id):
    """
    Handles editing of a blog post.
    GET: Displays the edit form.
    POST: Updates the blog post in the database.
    """
    client = get_mongo_client()
    if not client:
        return render_template("edit_blog.html", error="数据库连接失败")
    db = client.RunJPLib

    try:
        object_id = ObjectId(blog_id)
    except Exception:
        return render_template("404.html"), 404

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content_md = request.form.get("content_md", "").strip()

        if not title or not content_md:
            blog = db.blogs.find_one({"_id": object_id})
            return render_template("edit_blog.html", blog=blog, error="标题和内容不能为空")

        # Create a URL-friendly title
        url_title = title.lower().replace(" ", "-").replace("/", "-")
        url_title = "".join(c for c in url_title if c.isalnum() or c == "-")

        update_data = {
            "$set": {
                "title": title,
                "url_title": url_title,
                "content_md": content_md,
                "md_last_updated": datetime.now(),
            }
        }

        db.blogs.update_one({"_id": object_id}, update_data)
        logging.info(f"Blog post with ID {blog_id} was updated.")
        return redirect(url_for("admin.manage_blogs_page"))

    # For GET request
    blog = db.blogs.find_one({"_id": object_id})
    if not blog:
        return render_template("404.html"), 404

    # To ensure ObjectId is JSON serializable for the template if needed, though we're passing the raw object
    blog["_id"] = str(blog["_id"])

    return render_template("edit_blog.html", blog=blog)


# --- PDF Processing Pages ---
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


# --- PDF Processing APIs ---
@admin_bp.route("/api/pdf/upload", methods=["POST"])
@admin_required
def upload_pdf():
    """上传PDF文件并开始处理"""
    try:
        # 检查文件
        if "pdf_file" not in request.files:
            return jsonify({"error": "没有上传文件"}), 400

        file = request.files["pdf_file"]
        if file.filename == "":
            return jsonify({"error": "没有选择文件"}), 400

        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "只支持PDF文件"}), 400

        # 获取大学名称
        university_name = request.form.get("university_name", "").strip()
        if not university_name:
            return jsonify({"error": "请输入大学名称"}), 400

        # 保存文件到临时目录
        original_filename = secure_filename(file.filename)
        temp_filename = f"{uuid.uuid4().hex}_{original_filename}"

        # 创建临时目录
        temp_dir = os.path.join(tempfile.gettempdir(), "pdf_uploads")
        os.makedirs(temp_dir, exist_ok=True)

        temp_filepath = os.path.join(temp_dir, temp_filename)
        file.save(temp_filepath)

        # 创建处理任务
        task_id = task_manager.create_task(
            university_name=university_name,
            pdf_file_path=temp_filepath,
            original_filename=original_filename,
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


@admin_bp.route("/api/pdf/tasks", methods=["GET"])
@admin_required
def get_pdf_tasks():
    """获取PDF处理任务列表"""
    try:
        limit = request.args.get("limit", 50, type=int)
        tasks = task_manager.get_all_tasks(limit=limit)

        # 格式化时间
        for task in tasks:
            if "created_at" in task:
                task["created_at_str"] = task["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            if "updated_at" in task:
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


@admin_bp.route("/api/pdf/task-stream")
@admin_required
def task_stream():
    """使用SSE推送任务列表和队列状态的更新"""

    def event_stream():
        last_tasks_data = None
        last_queue_data = None
        while True:
            try:
                # 获取最新数据
                tasks = task_manager.get_all_tasks(limit=50)
                queue_status = task_manager.get_queue_status()

                # 准备要发送的数据
                current_tasks_data = json.dumps(tasks, default=str)
                current_queue_data = json.dumps(queue_status)

                # 检查数据是否有变化
                if (current_tasks_data != last_tasks_data or current_queue_data != last_queue_data):
                    # 发送合并的数据
                    combined_data = {"tasks": tasks, "queue_status": queue_status}
                    # 使用 default=str 来处理 ObjectId 和 datetime 对象
                    json_data = json.dumps(combined_data, default=str)
                    yield f"data: {json_data}\n\n"

                    # 更新最后的数据状态
                    last_tasks_data = current_tasks_data
                    last_queue_data = current_queue_data

            except Exception as e:
                logging.error(f"Error in SSE task stream: {e}", exc_info=True)
                # 如果发生错误，可以发送一个错误事件
                error_data = json.dumps({"error": "An internal error occurred"})
                yield f"event: error\ndata: {error_data}\n\n"

            # 等待一段时间再检查
            time.sleep(2)

    return Response(event_stream(), mimetype="text/event-stream")


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
                    # 格式化时间戳以便JS可以直接使用
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

                # 如果任务完成或失败，则停止发送
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

            time.sleep(2)

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
