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
from utils.chat_logging import chat_logger
from utils.mongo_client import get_db
from utils.mongo_client import get_mongo_client
from utils.task_manager import task_manager
from utils.thread_pool_manager import thread_pool_manager

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates/admin")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# --- 后台管理数据库操作辅助函数 ---


def _update_university_in_db(object_id, update_data, university_id):
    """异步更新大学信息到数据库"""
    try:
        db = get_db()
        if db is None:
            logging.error("Admin异步更新大学信息失败：无法连接数据库")
            return
        db.universities.update_one({"_id": object_id}, update_data)
        logging.info(f"University with ID {university_id} was updated (async).")
    except Exception as e:
        logging.error(f"异步更新大学信息失败: {e}")


def _save_blog_to_db(blog_data):
    """异步保存博客到数据库"""
    try:
        db = get_db()
        if db is None:
            logging.error("Admin异步保存博客失败：无法连接数据库")
            return None

        # 应用Wiki功能：自动识别学校名称并添加超链接
        from utils.blog_wiki_processor import blog_wiki_processor
        original_content = blog_data.get('content_md', '')
        processed_content = blog_wiki_processor.process_blog_content(original_content)

        # 如果内容被处理了，更新blog_data
        if processed_content != original_content:
            blog_data['content_md'] = processed_content
            logging.info("Blog内容已应用Wiki功能，自动添加了学校名称超链接")

        result = db.blogs.insert_one(blog_data)
        logging.info(f"New blog post created with ID: {result.inserted_id} (async).")

        # 清除推荐博客缓存，确保新博客能及时出现在推荐中
        from routes.blog import clear_recommended_blogs_cache
        clear_recommended_blogs_cache()

        return str(result.inserted_id)
    except Exception as e:
        logging.error(f"异步保存博客失败: {e}")
        return None


def _update_blog_in_db(object_id, update_data, blog_id):
    """异步更新博客到数据库"""
    try:
        db = get_db()
        if db is None:
            logging.error("Admin异步更新博客失败：无法连接数据库")
            return

        # 应用Wiki功能：自动识别学校名称并添加超链接
        if 'content_md' in update_data['$set']:
            from utils.blog_wiki_processor import blog_wiki_processor
            original_content = update_data['$set']['content_md']
            processed_content = blog_wiki_processor.process_blog_content(original_content)

            # 如果内容被处理了，更新update_data
            if processed_content != original_content:
                update_data['$set']['content_md'] = processed_content
                logging.info("Blog内容已应用Wiki功能，自动添加了学校名称超链接")

        db.blogs.update_one({"_id": object_id}, update_data)
        logging.info(f"Blog post with ID {blog_id} was updated (async).")

        # 清除推荐博客缓存，确保更新的博客能及时反映在推荐中
        from routes.blog import clear_recommended_blogs_cache
        clear_recommended_blogs_cache()
    except Exception as e:
        logging.error(f"异步更新博客失败: {e}")


def admin_required(fn):
    """管理员权限验证装饰器"""

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


def _get_dashboard_stats():
    """获取仪表盘核心统计数据的辅助函数"""
    db = get_db()
    if db is None:
        logging.error("仪表盘无法连接到数据库")
        return {"error": "数据库连接失败"}
    stats = {}
    try:
        stats["university_count"] = db.universities.count_documents({})
        stats["blog_count"] = db.blogs.count_documents({})
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        query_24h = {"timestamp": {"$gte": twenty_four_hours_ago}}

        # 访问日志统计
        unique_ips = db.access_logs.distinct("ip", query_24h)
        stats["unique_ip_count_24h"] = len(unique_ips)
        query_uni_24h = {
            "timestamp": {
                "$gte": twenty_four_hours_ago
            },
            "page_type": "university",
        }
        stats["university_views_24h"] = db.access_logs.count_documents(query_uni_24h)
        query_blog_24h = {
            "timestamp": {
                "$gte": twenty_four_hours_ago
            },
            "page_type": "blog",
        }
        stats["blog_views_24h"] = db.access_logs.count_documents(query_blog_24h)

        # 对话功能统计
        chat_query_24h = {"last_activity": {"$gte": twenty_four_hours_ago}}
        stats["chat_count_24h"] = db.chat_sessions.count_documents(chat_query_24h)
        unique_chat_ips = db.chat_sessions.distinct("user_ip", chat_query_24h)
        stats["unique_chat_ip_count_24h"] = len(unique_chat_ips)

    except Exception as e:
        logging.error(f"查询仪表盘统计数据时出错: {e}", exc_info=True)
        return {"error": "查询统计数据时出错"}
    return stats


@admin_bp.route("/")
@admin_required
def dashboard():
    """仪表盘路由，展示统计数据"""
    stats = _get_dashboard_stats()
    if "error" in stats:
        return render_template("dashboard.html", error=stats["error"])

    client = get_mongo_client()
    expired_premium_universities = []
    if client is not None:

        try:
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            pipeline = [
                {
                    "$group": {
                        "_id": "$university_name",
                        "max_deadline": {
                            "$max": "$deadline"
                        },
                        "has_premium": {
                            "$max": "$is_premium"
                        },
                    }
                },
                {
                    "$match": {
                        "has_premium": True,
                        "max_deadline": {
                            "$lt": today
                        }
                    }
                },
                {
                    "$sort": {
                        "max_deadline": 1
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "university_name": "$_id",
                        "deadline": "$max_deadline",
                    }
                },
            ]
            expired_premium_universities = list(client.RunJPLib.universities.aggregate(pipeline))
        except Exception as e:
            logging.error(f"查询过期Premium学校时出错: {e}", exc_info=True)

    return render_template(
        "dashboard.html",
        stats=stats,
        expired_premium_universities=expired_premium_universities,
    )


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


# --- 聊天记录管理API ---


@admin_bp.route("/chat-logs")
@admin_required
def chat_logs_page():
    """聊天记录管理页面"""
    db = get_db()
    if db is None:
        return render_template("chat_logs.html", error="数据库连接失败", sessions=[])

    try:
        # 查询所有会话，按最后活动时间排序
        sessions = list(db.chat_sessions.find().sort("last_activity", -1))

        # 转换数据格式以匹配模板期望
        formatted_sessions = []
        for session in sessions:
            formatted_sessions.append({
                "_id": session["session_id"],  # 使用session_id作为_id
                "session_id": session["session_id"],
                "last_activity": session["last_activity"],
                "ip_address": session["user_ip"],
                "message_count": session["total_messages"],
                "university_name": session.get("university_name", "未知"),
                "user_agent": session.get("user_agent", "")
            })

        return render_template("chat_logs.html", sessions=formatted_sessions)
    except Exception as e:
        logging.error(f"获取聊天会话列表失败: {e}", exc_info=True)
        return render_template("chat_logs.html", error="查询会话列表失败", sessions=[])


@admin_bp.route("/chat_log/<session_id>")
@admin_required
def chat_log_detail(session_id):
    """显示特定会话的聊天记录"""
    db = get_db()
    if db is None:
        return render_template("chat_log_detail.html", error="数据库连接失败", logs=[])

    try:
        # 查询特定会话
        session = db.chat_sessions.find_one({"session_id": session_id})
        if not session:
            return render_template("chat_log_detail.html", error="会话不存在", logs=[])

        # 获取会话中的消息
        messages = session.get("messages", [])

        # 转换消息格式以匹配模板期望
        formatted_logs = []
        for msg in messages:
            formatted_logs.append({
                "timestamp": msg.get("timestamp"),
                "message": msg.get("user_input", ""),
                "response": msg.get("ai_response", ""),
                "processing_time": msg.get("processing_time", 0)
            })

        return render_template("chat_log_detail.html", logs=formatted_logs, session_id=session_id)
    except Exception as e:
        logging.error(f"获取会话 {session_id} 的聊天记录失败: {e}", exc_info=True)
        return render_template("chat_log_detail.html", error="查询聊天记录失败", logs=[])


@admin_bp.route("/api/chat-sessions", methods=["GET"])
@admin_required
def get_chat_sessions():
    """获取聊天会话列表"""
    try:
        skip = int(request.args.get("skip", 0))
        limit = int(request.args.get("limit", 20))
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        university = request.args.get("university")
        user_ip = request.args.get("user_ip")

        # 构建查询条件
        query = {}
        if start_date:
            query["start_time"] = {"$gte": datetime.fromisoformat(start_date)}
        if end_date:
            end_datetime = datetime.fromisoformat(end_date)
            if "start_time" in query:
                query["start_time"]["$lte"] = end_datetime
            else:
                query["start_time"] = {"$lte": end_datetime}
        if university:
            query["university_name"] = university
        if user_ip:
            query["user_ip"] = {"$regex": user_ip, "$options": "i"}

        # 获取会话列表
        db = get_db()
        if db is None:
            return jsonify({"success": False, "error": "数据库连接失败"}), 500

        sessions = list(
            db.chat_sessions.find(query, {
                "session_id": 1,
                "user_ip": 1,
                "university_name": 1,
                "start_time": 1,
                "last_activity": 1,
                "total_messages": 1
            }).sort("start_time", -1).skip(skip).limit(limit))

        # 获取总数
        total = db.chat_sessions.count_documents(query)

        # 转换ObjectId为字符串
        for session in sessions:
            session["_id"] = str(session["_id"])

        return jsonify({"success": True, "sessions": sessions, "total": total})

    except Exception as e:
        logging.error(f"获取聊天会话列表失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/chat-sessions/<session_id>", methods=["GET"])
@admin_required
def get_chat_session_detail(session_id):
    """获取聊天会话详情"""
    try:
        session = chat_logger.get_chat_session_detail(session_id)

        if session:
            return jsonify({"success": True, "session": session})
        else:
            return jsonify({"success": False, "error": "会话不存在"}), 404

    except Exception as e:
        logging.error(f"获取聊天会话详情失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/chat-statistics", methods=["GET"])
@admin_required
def get_chat_statistics():
    """获取聊天统计信息"""
    try:
        statistics = chat_logger.get_chat_statistics()

        return jsonify({"success": True, "statistics": statistics})

    except Exception as e:
        logging.error(f"获取聊天统计信息失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/chat-universities", methods=["GET"])
@admin_required
def get_chat_universities():
    """获取聊天涉及的大学列表"""
    try:
        db = get_db()
        if db is None:
            return jsonify({"success": False, "error": "数据库连接失败"}), 500

        universities = db.chat_sessions.distinct("university_name")
        universities = [uni for uni in universities if uni]  # 过滤空值

        return jsonify({"success": True, "universities": sorted(universities)})

    except Exception as e:
        logging.error(f"获取聊天大学列表失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/chat-cleanup", methods=["POST"])
@admin_required
def cleanup_chat_sessions():
    """清理旧的聊天会话"""
    try:
        data = request.get_json()
        days = data.get("days", 90) if data else 90

        deleted_count = chat_logger.cleanup_old_sessions(days)

        return jsonify({"success": True, "deleted_count": deleted_count, "message": f"已清理 {deleted_count} 个超过 {days} 天的聊天会话"})

    except Exception as e:
        logging.error(f"清理聊天会话失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# --- 数据管理页面 ---
@admin_bp.route("/manage/universities")
@admin_required
def manage_universities_page():
    return render_template("manage_universities.html")


@admin_bp.route("/manage/blogs")
@admin_required
def manage_blogs_page():
    return render_template("manage_blogs.html")


# --- 数据管理API ---
@admin_bp.route("/api/universities", methods=["GET"])
@admin_required
def get_universities():
    db = get_db()
    if db is None:
        logging.error("[Admin API] Get universities failed: DB connection error.")
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        logging.debug("[Admin API] Fetching universities from database...")
        projection = {"content": 0, "source_path": 0}
        # 优化排序：按 _id 逆序排列，实现按创建时间倒序
        cursor = db.universities.find({}, projection).sort("_id", -1)

        universities = list(cursor)

        for u in universities:
            u["_id"] = str(u["_id"])
            # 确保 deadline 字段是 ISO 格式的字符串，方便前端解析
            if u.get("deadline") and isinstance(u["deadline"], datetime):
                u["deadline"] = u["deadline"].isoformat()

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
    db = get_db()
    if db is None:
        return render_template("edit_university.html", error="数据库连接失败")

    try:
        object_id = ObjectId(university_id)
    except Exception:
        return render_template("404.html"), 404

    if request.method == "POST":
        university_name = request.form.get("university_name", "").strip()
        university_name_zh = request.form.get("university_name_zh", "").strip()
        is_premium = request.form.get("is_premium") == "true"
        deadline_str = request.form.get("deadline", "")
        basic_analysis_report = request.form.get("basic_analysis_report", "").strip()

        if not university_name:
            university = db.universities.find_one({"_id": object_id})
            return render_template("edit_university.html", university=university, error="大学名称不能为空")

        update_data = {
            "$set": {
                "university_name": university_name,
                "university_name_zh": university_name_zh,
                "is_premium": is_premium,
                "content.report_md": basic_analysis_report,
                "last_modified": datetime.utcnow(),
            }
        }

        if deadline_str:
            try:
                # 将 YYYY-MM-DD 格式的字符串转换为 datetime 对象
                update_data["$set"]["deadline"] = datetime.strptime(deadline_str, "%Y-%m-%d")
            except ValueError:
                # 如果日期格式不正确，返回错误信息
                university = db.universities.find_one({"_id": object_id})
                return render_template(
                    "edit_university.html",
                    university=university,
                    error="日期格式不正确，请使用 YYYY-MM-DD 格式。",
                )

        # 尝试异步更新数据库
        success = thread_pool_manager.submit_admin_task(_update_university_in_db, object_id, update_data, university_id)

        if not success:
            # 线程池满，同步执行
            logging.warning("Admin线程池繁忙，同步更新大学信息")
            try:
                db.universities.update_one({"_id": object_id}, update_data)
                logging.info(f"University with ID {university_id} was updated (sync).")
            except Exception as e:
                logging.error(f"同步更新大学信息失败: {e}")
                return render_template(
                    "edit_university.html",
                    university=db.universities.find_one({"_id": object_id}),
                    error="更新失败，请重试",
                )
        else:
            logging.info(f"University with ID {university_id} update task submitted to thread pool.")

        return redirect(url_for("admin.manage_universities_page"))

    # GET 请求
    university = db.universities.find_one({"_id": object_id})
    if not university:
        return render_template("404.html"), 404

    return render_template("edit_university.html", university=university)


@admin_bp.route("/api/universities/<item_id>", methods=["DELETE"])
@admin_required
def delete_university(item_id):
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    db.universities.delete_one({"_id": ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route("/api/universities", methods=["DELETE"])
@admin_required
def clear_universities():
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    db.universities.delete_many({})
    return jsonify({"message": "数据集合已清空"})


@admin_bp.route("/api/blogs", methods=["GET"])
@admin_required
def get_blogs():
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

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
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    db.blogs.delete_one({"_id": ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route("/api/blogs", methods=["DELETE"])
@admin_required
def clear_blogs():
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    db.blogs.delete_many({})
    return jsonify({"message": "数据集合已清空"})


# --- 博客创建工具 ---


@admin_bp.route("/blog/create")
@admin_required
def create_blog_page():
    """渲染博客创建页面"""
    return render_template("create_blog.html")


@admin_bp.route("/api/universities/search", methods=["GET"])
@admin_required
def search_universities():
    """
    根据名称搜索大学。
    接受'q'作为查询参数。
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        # 根据名称模糊搜索（不区分大小写）
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
        ).limit(20))  # 限制20条结果以提高性能

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
    使用AI生成博客内容。
    需要包含'university_ids', 'user_prompt', 'system_prompt'的JSON。
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求格式"}), 400

    university_ids = data.get("university_ids", [])
    user_prompt = data.get("user_prompt", "")
    system_prompt = data.get("system_prompt", "")
    mode = data.get("mode", "expand")  # 默认为expand模式

    if not system_prompt:
        return jsonify({"error": "系统提示词不能为空"}), 400

    # 根据模式验证输入
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
    保存新博客文章到数据库。
    需要包含'title'和'content_md'的JSON。
    """
    data = request.get_json()
    if not data or "title" not in data or "content_md" not in data:
        return jsonify({"error": "无效的请求格式，需要'title'和'content_md'"}), 400

    title = data["title"].strip()
    content_md = data["content_md"].strip()

    if not title or not content_md:
        return jsonify({"error": "标题和内容不能为空"}), 400

    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        # 创建URL友好标题
        url_title = title.lower().replace(" ", "-").replace("/", "-")
        # 移除不安全的URL字符
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

        # 尝试异步保存博客
        success = thread_pool_manager.submit_admin_task(_save_blog_to_db, new_blog)

        if not success:
            # 线程池满，同步执行
            logging.warning("Admin线程池繁忙，同步保存博客")
            try:
                # 应用Wiki功能
                from utils.blog_wiki_processor import blog_wiki_processor
                original_content = new_blog.get('content_md', '')
                processed_content = blog_wiki_processor.process_blog_content(original_content)

                if processed_content != original_content:
                    new_blog['content_md'] = processed_content
                    logging.info("Blog内容已应用Wiki功能，自动添加了学校名称超链接")

                result = db.blogs.insert_one(new_blog)
                logging.info(f"New blog post created with ID: {result.inserted_id} (sync).")

                # 清除推荐博客缓存，确保新博客能及时出现在推荐中
                from routes.blog import clear_recommended_blogs_cache
                clear_recommended_blogs_cache()

                return jsonify({"message": "文章保存成功", "blog_id": str(result.inserted_id)})
            except Exception as sync_e:
                logging.error(f"同步保存博客失败: {sync_e}")
                return jsonify({"error": "保存失败，请重试"}), 500
        else:
            # 异步任务已提交
            logging.info("Blog save task submitted to thread pool.")
            return jsonify({"message": "文章保存任务已提交", "blog_id": "pending"})
    except Exception as e:
        logging.error(f"[Admin API] Failed to save blog: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/blog/edit/<blog_id>", methods=["GET", "POST"])
@admin_required
def edit_blog(blog_id):
    """
    处理博客文章编辑。
    GET: 显示编辑表单。
    POST: 更新数据库中的文章。
    """
    db = get_db()
    if db is None:
        return render_template("edit_blog.html", error="数据库连接失败")

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

        # 创建URL友好标题
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

        # 尝试异步更新博客
        success = thread_pool_manager.submit_admin_task(_update_blog_in_db, object_id, update_data, blog_id)

        if not success:
            # 线程池满，同步执行
            logging.warning("Admin线程池繁忙，同步更新博客")
            try:
                # 应用Wiki功能
                if 'content_md' in update_data['$set']:
                    from utils.blog_wiki_processor import blog_wiki_processor
                    original_content = update_data['$set']['content_md']
                    processed_content = blog_wiki_processor.process_blog_content(original_content)

                    if processed_content != original_content:
                        update_data['$set']['content_md'] = processed_content
                        logging.info("Blog内容已应用Wiki功能，自动添加了学校名称超链接")

                db.blogs.update_one({"_id": object_id}, update_data)
                logging.info(f"Blog post with ID {blog_id} was updated (sync).")

                # 清除推荐博客缓存，确保更新的博客能及时反映在推荐中
                from routes.blog import clear_recommended_blogs_cache
                clear_recommended_blogs_cache()
            except Exception as e:
                logging.error(f"同步更新博客失败: {e}")
                return render_template(
                    "edit_blog.html",
                    blog=db.blogs.find_one({"_id": object_id}),
                    error="更新失败，请重试",
                )
        else:
            logging.info(f"Blog post with ID {blog_id} update task submitted to thread pool.")

        return redirect(url_for("admin.manage_blogs_page"))

    # GET请求
    blog = db.blogs.find_one({"_id": object_id})
    if not blog:
        return render_template("404.html"), 404

    blog["_id"] = str(blog["_id"])

    return render_template("edit_blog.html", blog=blog)


# --- PDF处理页面 ---
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


# --- 分析：最近24小时独立IP ---
@admin_bp.route("/analytics/unique_ips")
@admin_required
def unique_ips_page():
    """展示最近24小时的独立IP列表及相关信息（无SSE）。"""
    db = get_db()
    if db is None:
        return render_template("unique_ips.html", error="数据库连接失败", items=[])

    # 确保mmdb文件可用
    from utils.ip_geo import ip_geo_manager

    logging.info("🔧 检查mmdb文件可用性...")
    mmdb_available = ip_geo_manager.ensure_mmdb_available()
    logging.info(f"📁 mmdb文件状态: {'可用' if mmdb_available else '不可用'}")

    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    logging.info(f"⏰ 查询时间范围: {twenty_four_hours_ago} 至今")

    try:
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": twenty_four_hours_ago
                    }
                }
            },
            {
                "$group": {
                    "_id": "$ip",
                    "first_seen": {
                        "$min": "$timestamp"
                    },
                    "last_seen": {
                        "$max": "$timestamp"
                    },
                    "visit_count": {
                        "$sum": 1
                    },
                    "page_types": {
                        "$addToSet": "$page_type"
                    },
                }
            },
            {
                "$sort": {
                    "last_seen": -1
                }
            },
        ]

        logging.info("🔍 执行MongoDB聚合查询...")
        results = list(db.access_logs.aggregate(pipeline))
        logging.info(f"📊 查询到 {len(results)} 个独立IP")

        items = []
        ips_to_lookup = []

        for r in results:
            ip = r.get("_id")

            # 检查该IP是否已有地理信息
            geo_info = None
            if mmdb_available:
                # 从访问记录中查找
                sample_log = db.access_logs.find_one({"ip": ip, "geo_info": {"$exists": True}})
                if sample_log and sample_log.get("geo_info"):
                    geo_info = sample_log["geo_info"]
                    logging.debug(f"✅ 从访问记录中找到地理信息: {ip} -> {geo_info.get('city', 'N/A')}")
                else:
                    ips_to_lookup.append(ip)
                    logging.debug(f"❓ IP需要解析地理信息: {ip}")

            item = {
                "ip": ip,
                "first_seen": r.get("first_seen"),
                "last_seen": r.get("last_seen"),
                "visit_count": r.get("visit_count", 0),
                "page_types": r.get("page_types", []),
                "geo_info": geo_info,
            }
            items.append(item)

        logging.info(f"🎯 准备处理 {len(ips_to_lookup)} 个IP的地理信息")

        # 批量查询地理信息并更新数据库
        if mmdb_available and ips_to_lookup:
            _batch_update_geo_info(db, ips_to_lookup, items)
        else:
            logging.info("⏭️ 跳过地理信息处理 (mmdb不可用或无IP需要处理)")

        logging.info(f"✅ 页面渲染完成，共 {len(items)} 个IP")
        return render_template("unique_ips.html", items=items, mmdb_available=mmdb_available)
    except Exception as e:
        logging.error(f"查询独立IP统计失败: {e}", exc_info=True)
        return render_template("unique_ips.html", error="查询失败", items=[])


def _batch_update_geo_info(db, ips_to_lookup, items):
    """批量更新IP地理信息到数据库（嵌入方案）"""
    from utils.ip_geo import ip_geo_manager

    try:
        logging.info(f"🔍 开始批量更新地理信息，总IP数量: {len(ips_to_lookup)}")

        # 限制批量处理数量
        batch_size = 200
        processed_count = 0
        skipped_count = 0

        logging.info(f"⚙️ 批量处理限制: {batch_size} 个IP")

        for ip in ips_to_lookup:
            if processed_count >= batch_size:
                logging.info(f"⏹️ 达到批量处理限制 {batch_size}，跳过剩余 {len(ips_to_lookup) - processed_count} 个IP")
                break

            # 处理多IP地址的情况
            original_ip = ip
            if "," in ip or " " in ip:
                # 取第一个IP进行解析
                first_ip = ip.split(",")[0].strip()
                logging.debug(f"🔄 多IP地址处理: '{ip}' -> 使用第一个IP '{first_ip}' 进行地理信息解析")
                ip = first_ip
            elif not ip:
                logging.warning("跳过空IP地址")
                skipped_count += 1
                continue

            logging.debug(f"🔍 查询IP: {ip}")
            geo_data = ip_geo_manager.lookup_ip(ip)

            if geo_data:
                logging.debug(f"📍 解析成功: {ip} -> {geo_data.get('city', 'N/A')}, {geo_data.get('country_name', 'N/A')}")

                geo_info = {
                    "country_code": geo_data.get("country_code"),
                    "country_name": geo_data.get("country_name"),
                    "city": geo_data.get("city"),
                    "latitude": geo_data.get("latitude"),
                    "longitude": geo_data.get("longitude"),
                    "mmdb_version": "1.0",
                    "geo_updated_at": datetime.utcnow(),
                }

                try:
                    # 更新所有该IP的访问记录
                    update_result = db.access_logs.update_many({"ip": original_ip}, {"$set": {"geo_info": geo_info}})
                    logging.debug(f"💾 更新访问记录: '{original_ip}' -> {update_result.modified_count} 条记录")

                    # 保存到缓存
                    geo_doc = {"ip": ip, **geo_info}
                    db.ip_geo_cache.replace_one({"ip": ip}, geo_doc, upsert=True)
                    logging.debug(f"💾 保存到缓存: {ip}")

                    # 更新items中的地理信息
                    for item in items:
                        if item["ip"] == original_ip:
                            item["geo_info"] = geo_info
                            break

                    processed_count += 1

                except Exception as e:
                    logging.warning(f"❌ 更新IP {ip} 地理信息失败: {e}")
                    skipped_count += 1
            else:
                logging.debug(f"❓ 无法解析IP: {ip} (可能是私有IP或无记录)")
                skipped_count += 1

        # 总结日志
        logging.info("📊 批量更新完成:")
        logging.info(f"  - 新解析并嵌入: {processed_count} 个IP")
        logging.info(f"  - 跳过/失败: {skipped_count} 个IP")
        logging.info(f"  - 剩余未处理: {len(ips_to_lookup) - processed_count} 个IP")

        if processed_count > 0:
            logging.info(f"🎉 成功更新了 {processed_count} 个IP的地理信息到访问记录中")

    except Exception as e:
        logging.error(f"❌ 批量更新地理信息失败: {e}", exc_info=True)


# --- PDF处理API ---
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
        task_id = task_manager.create_task(
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


@admin_bp.route("/api/thread_pool/status", methods=["GET"])
@admin_required
def get_thread_pool_status():
    """获取线程池状态"""
    try:
        stats = thread_pool_manager.get_pool_stats()
        return jsonify(stats)
    except Exception as e:
        logging.error(f"[Admin API] 获取线程池状态失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/dashboard-stream")
@admin_required
def dashboard_stream():
    """使用SSE推送仪表盘的实时数据"""

    def event_stream():
        last_data = None
        while True:
            try:
                stats_data = _get_dashboard_stats()
                pool_data = thread_pool_manager.get_pool_stats()
                combined_data = {"stats": stats_data, "pools": pool_data}
                current_data = json.dumps(combined_data, default=str)

                # 仅在数据变化时发送
                if current_data != last_data:
                    yield f"data: {current_data}\n\n"
                    last_data = current_data

            except Exception as e:
                logging.error(f"Error in SSE dashboard stream: {e}", exc_info=True)
                error_data = json.dumps({"error": "An internal error occurred"})
                yield f"event: error\ndata: {error_data}\n\n"

            # 每30秒检查一次
            time.sleep(30)

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
