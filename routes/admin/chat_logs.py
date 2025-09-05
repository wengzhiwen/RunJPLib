from datetime import datetime
import logging

from flask import jsonify
from flask import render_template
from flask import request

from routes.admin.auth import admin_required
from utils import add_security_headers
from utils import chat_logger
from utils import ChatManager
from utils import get_csrf_token_for_session
from utils import get_db

from . import admin_bp


@admin_bp.route('/chat', methods=['GET'])
def admin_chat_page():
    """管理端AI对话测试页面（迁移后保留页面路由）"""

    # 延迟应用装饰器，避免在 admin_required 定义之前引用
    def _render():
        return render_template('admin/chat.html')

    protected = admin_required(_render)
    return protected()


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


# 全局ChatManager实例（单例模式）
_admin_chat_manager = None


def get_admin_chat_manager():
    """获取admin聊天管理器实例（单例）"""
    global _admin_chat_manager
    if _admin_chat_manager is None:
        _admin_chat_manager = ChatManager()
    return _admin_chat_manager


# Admin聊天API路由
@admin_bp.route("/chat/api/create-session", methods=["POST"])
@admin_required
def admin_create_chat_session():
    """Admin创建聊天会话"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "无效的请求格式"}), 400

        university_id = data.get("university_id")
        university_name = data.get("university_name", "")

        if not university_id:
            return jsonify({"success": False, "error": "缺少大学ID"}), 400

        # 获取ChatManager实例（单例）
        chat_mgr = get_admin_chat_manager()

        # 创建会话
        session = chat_mgr.create_chat_session(university_id)
        if not session:
            return jsonify({"success": False, "error": "创建会话失败"}), 500

        # 生成CSRF令牌
        csrf_token = get_csrf_token_for_session(session.session_id)

        # 返回会话信息
        response_data = {
            "success": True,
            "session": {
                "session_id": session.session_id,
                "university_name": university_name,
                "csrf_token": csrf_token,
                "created_at": session.created_at.isoformat() if session.created_at else datetime.now().isoformat(),
                "last_activity": session.last_activity.isoformat() if session.last_activity else datetime.now().isoformat(),
                "is_restored": False,
                "message_count": 0,
            },
            "notice": "Admin聊天会话已创建",
        }

        response = jsonify(response_data)
        return add_security_headers(response)

    except Exception as e:
        logging.error(f"Admin创建聊天会话失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": "服务暂时不可用"}), 500


@admin_bp.route("/chat/api/send-message", methods=["POST"])
@admin_required
def admin_send_message():
    """Admin发送消息"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "无效的请求格式"}), 400

        session_id = data.get("session_id")
        message = data.get("message", "").strip()

        if not session_id or not message:
            return jsonify({"success": False, "error": "缺少会话ID或消息内容"}), 400

        # 获取ChatManager实例（单例）
        chat_mgr = get_admin_chat_manager()

        # 获取会话
        session = chat_mgr.get_session(session_id)
        if not session:
            return jsonify({"success": False, "error": "会话不存在"}), 404

        # 发送消息
        result = chat_mgr.process_message(session_id, message)
        if not result.get("success", False):
            return jsonify({"success": False, "error": result.get("error", "发送消息失败")}), 500

        response = result.get("response", "")

        # 返回响应
        response_data = {
            "success": True,
            "response": response,
            "session_info": result.get("session_info", {
                "session_id": session_id,
                "message_count": len(session.messages) if session.messages else 0,
            })
        }

        return jsonify(response_data)

    except Exception as e:
        logging.error(f"Admin发送消息失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": "服务暂时不可用"}), 500
