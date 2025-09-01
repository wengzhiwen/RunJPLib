"""
大学聊天API路由处理器
为特定大学提供聊天API服务
"""

from datetime import datetime
import logging
import time

from flask import jsonify
from flask import request

from routes.index import get_university_details
from utils.chat_logging import chat_logger
from utils.chat_manager import ChatManager
from utils.chat_security import add_security_headers
from utils.chat_security import get_csrf_token_for_session
from utils.chat_security import public_chat_api_protection
from utils.university_document_manager import UniversityDocumentManager

logger = logging.getLogger(__name__)

# 全局实例（懒加载）
chat_manager = None
doc_manager = None


def get_chat_manager():
    """获取聊天管理器实例（懒加载）"""
    global chat_manager
    if chat_manager is None:
        try:
            chat_manager = ChatManager()
            logger.info("大学聊天管理器初始化成功")
        except Exception:
            logger.error("大学聊天管理器初始化失败")
            raise
    return chat_manager


def get_doc_manager():
    """获取文档管理器实例（懒加载）"""
    global doc_manager
    if doc_manager is None:
        doc_manager = UniversityDocumentManager()
        logger.info("大学文档管理器初始化成功")
    return doc_manager


def get_client_ip():
    """获取客户端IP地址"""
    # 优先使用X-Forwarded-For（考虑代理）
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    # 使用X-Real-IP
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip

    # 最后使用remote_addr
    return request.remote_addr or "unknown"


def handle_university_chat_api(university_name: str, endpoint: str, deadline: str = None):
    """
    处理大学聊天API请求

    Args:
        university_name: 大学名称
        endpoint: API端点
        deadline: 截止日期（可选）

    Returns:
        Flask Response
    """
    try:
        # 获取大学信息
        university_doc = get_university_details(university_name, deadline)
        if not university_doc:
            return jsonify({"success": False, "error": "未找到指定的大学信息"}), 404

        university_id = str(university_doc["_id"])
        user_ip = get_client_ip()

        # 路由到具体的API处理函数
        if endpoint == "create-session":
            return create_chat_session(university_id, university_name, user_ip)
        elif endpoint == "send-message":
            return send_chat_message(university_id, university_name, user_ip)
        elif endpoint == "get-history":
            return get_chat_history(university_id, university_name, user_ip)
        elif endpoint == "health":
            return health_check()
        else:
            return jsonify({"success": False, "error": "API端点不存在"}), 404

    except Exception as e:
        logger.error(f"处理大学聊天API时出错: {e}", exc_info=True)
        return jsonify({"success": False, "error": "服务暂时不可用"}), 500


@public_chat_api_protection(max_requests=5, time_window=60)
def create_chat_session(university_id: str, university_name: str, user_ip: str):
    """创建或恢复聊天会话"""
    try:
        # 检查用户是否触发降级
        should_degrade, delay_seconds = chat_logger.should_apply_degradation(user_ip)
        if should_degrade:
            # 后端延迟处理，用户无感知
            logger.info(f"用户 {user_ip} 触发降级，延迟 {delay_seconds} 秒处理")
            time.sleep(delay_seconds)

        chat_mgr = get_chat_manager()
        session = None
        is_restored = False

        # 获取请求数据中的浏览器会话ID
        data = request.get_json() or {}
        browser_session_id = data.get("browser_session_id")

        # 首先尝试查找现有的活跃会话
        existing_session_data = chat_logger.get_active_session_for_university(user_ip, university_id, browser_session_id)

        if existing_session_data:
            # 尝试恢复现有会话
            session = chat_mgr.restore_session_from_db(existing_session_data)
            if session:
                is_restored = True
                logger.info(f"恢复用户 {user_ip} 在大学 {university_name} 的现有会话: {session.session_id}")

        # 如果没有现有会话或恢复失败，创建新会话
        if not session:
            session = chat_mgr.create_chat_session(university_id)
            if not session:
                return jsonify({"success": False, "error": "创建会话失败"}), 500

            # 记录新会话到数据库
            session_data = {
                "session_id": session.session_id,
                "user_ip": user_ip,
                "browser_session_id": browser_session_id,
                "university_name": university_name,
                "university_id": university_id,
                "user_agent": request.headers.get("User-Agent", ""),
                "referer": request.headers.get("Referer", ""),
            }
            chat_logger.log_chat_session(session_data)

        # 生成CSRF令牌
        csrf_token = get_csrf_token_for_session(session.session_id)

        # 返回会话信息
        notice = "继续之前的对话..." if is_restored else "欢迎使用AI对话助手！每日有使用次数限制。"

        response_data = {
            "success": True,
            "session": {
                "session_id": session.session_id,
                "university_name": university_name,
                "csrf_token": csrf_token,
                "created_at": session.created_at.isoformat(),
                "is_restored": is_restored,
                "message_count": len(session.messages) if session.messages else 0,
            },
            "notice": notice,
        }

        response = jsonify(response_data)
        return add_security_headers(response)

    except Exception as e:
        logger.error(f"创建聊天会话时出错: {e}", exc_info=True)
        return jsonify({"success": False, "error": "服务暂时不可用"}), 500


@public_chat_api_protection(max_requests=15, time_window=60)
def send_chat_message(university_id: str, university_name: str, user_ip: str):
    """发送聊天消息"""
    # university_id, university_name 由路由传递，用于上下文识别，在记录函数中使用
    _ = university_id, university_name  # 避免未使用参数警告
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据格式错误"}), 400

        session_id = data.get("session_id")
        message = data.get("message", "").strip()

        if not session_id:
            return jsonify({"success": False, "error": "缺少session_id参数"}), 400

        if not message:
            return jsonify({"success": False, "error": "消息内容不能为空"}), 400

        # 限制消息长度
        if len(message) > 300:
            return jsonify({"success": False, "error": "消息长度不能超过300字符"}), 400

        # 检查用户是否触发降级
        should_degrade, delay_seconds = chat_logger.should_apply_degradation(user_ip)
        if should_degrade:
            # 异步处理：延迟后再处理消息
            logger.info(f"用户 {user_ip} 触发降级，延迟 {delay_seconds} 秒处理")
            time.sleep(delay_seconds)

        # 记录处理开始时间
        start_time = time.time()

        # 处理消息
        chat_mgr = get_chat_manager()
        result = chat_mgr.process_message(session_id, message)

        # 计算处理时间
        processing_time = time.time() - start_time

        if result.get("success"):
            ai_response = result.get("response", "")

            # 记录对话到数据库
            chat_logger.log_chat_message(
                session_id=session_id,
                user_input=message,
                ai_response=ai_response,
                user_ip=user_ip,
                processing_time=processing_time,
            )

            # 过滤返回的信息（不返回sources等敏感信息）
            filtered_result = {
                "success": True,
                "response": ai_response,
                "processing_time": round(processing_time, 2),
                "session_info": {
                    "message_count": result.get("session_info", {}).get("message_count", 0)
                },
            }

        else:
            # 即使失败也要记录
            chat_logger.log_chat_message(
                session_id=session_id,
                user_input=message,
                ai_response=f"错误: {result.get('error', '未知错误')}",
                user_ip=user_ip,
                processing_time=processing_time,
            )

            filtered_result = {
                "success": False,
                "error": result.get("error", "服务暂时不可用"),
                "error_code": result.get("error_code", "UNKNOWN_ERROR"),
            }

        response = jsonify(filtered_result)
        return add_security_headers(response)

    except Exception as e:
        logger.error(f"发送聊天消息时出错: {e}", exc_info=True)
        return jsonify({"success": False, "error": "服务暂时不可用", "error_code": "SERVICE_UNAVAILABLE"}), 500


@public_chat_api_protection(max_requests=10, time_window=60)
def get_chat_history(university_id: str, university_name: str, user_ip: str):  # university_name used for logging context
    """获取聊天历史"""
    _ = university_name  # 避免未使用参数警告
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据格式错误"}), 400

        session_id = data.get("session_id")
        browser_session_id = data.get("browser_session_id")
        if not session_id:
            return jsonify({"success": False, "error": "缺少session_id参数"}), 400

        # 获取会话详情
        session_detail = chat_logger.get_chat_session_detail(session_id)
        if not session_detail:
            return jsonify({"success": False, "error": "会话不存在"}), 404

        # 验证会话归属 - 优先使用浏览器会话ID，回退到IP验证
        session_browser_id = session_detail.get("browser_session_id")
        session_ip = session_detail.get("user_ip")

        # 隐私保护：如果有浏览器会话ID，必须匹配；否则使用IP验证
        if session_browser_id:
            if session_browser_id != browser_session_id:
                return jsonify({"success": False, "error": "无权访问此会话"}), 403
        else:
            # 兼容没有浏览器会话ID的旧会话
            if session_ip != user_ip:
                return jsonify({"success": False, "error": "无权访问此会话"}), 403

        # 验证大学ID
        if session_detail.get("university_id") != university_id:
            return jsonify({"success": False, "error": "无权访问此会话"}), 403

        # 获取历史消息
        db_messages = session_detail.get("messages", [])
        logger.info(f"获取会话 {session_id} 的历史消息，原始消息数量: {len(db_messages)}")

        # 转换消息格式为前端期望的格式
        formatted_messages = []
        for msg in db_messages[-20:]:  # 只取最近20条消息
            # 确保消息包含必要字段
            if not msg.get("timestamp"):
                logger.warning(f"跳过没有时间戳的消息: {msg}")
                continue

            # 添加用户消息
            if msg.get("user_input"):
                formatted_messages.append({
                    "role": "user",
                    "content": msg["user_input"],
                    "timestamp": (msg["timestamp"].isoformat() if hasattr(msg["timestamp"], "isoformat") else str(msg["timestamp"])),
                })

            # 添加AI回复
            if msg.get("ai_response"):
                formatted_messages.append({
                    "role": "assistant",
                    "content": msg["ai_response"],
                    "timestamp": (msg["timestamp"].isoformat() if hasattr(msg["timestamp"], "isoformat") else str(msg["timestamp"])),
                })

        logger.info(f"转换后的消息数量: {len(formatted_messages)}")

        return jsonify({"success": True, "messages": formatted_messages, "total_count": len(formatted_messages)})

    except Exception as e:
        logger.error(f"获取聊天历史时出错: {e}", exc_info=True)
        return jsonify({"success": False, "error": "服务暂时不可用"}), 500


@public_chat_api_protection(max_requests=60, time_window=60)
def health_check():  # university_id, university_name unused but required by router
    """健康检查API"""
    try:
        user_ip = get_client_ip()
        daily_count = chat_logger.get_user_daily_message_count(user_ip)
        should_degrade, delay_seconds = chat_logger.should_apply_degradation(user_ip)

        response = jsonify({
            "success": True,
            "status": "healthy",
            "service": "university_chat",
            "timestamp": datetime.now().isoformat(),
            "user_status": {
                "daily_message_count": daily_count,
                "degraded": should_degrade,
                "delay_seconds": delay_seconds if should_degrade else 0,
            },
        })
        return add_security_headers(response)

    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return jsonify({"success": False, "status": "unhealthy"}), 500
