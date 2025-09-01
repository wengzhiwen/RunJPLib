"""
聊天功能路由
"""
import logging
import json
import uuid
import time
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, Response, stream_with_context

from routes.admin import admin_required
from utils.chat_manager import ChatManager
from utils.university_document_manager import UniversityDocumentManager
from utils.llama_index_integration import LlamaIndexIntegration
from utils.chat_security import chat_api_protection, public_chat_api_protection, get_csrf_token_for_session, add_security_headers

logger = logging.getLogger(__name__)

# 创建Blueprint
chat_bp = Blueprint("chat", __name__, url_prefix="/admin/chat")

# 全局实例
chat_manager = None
doc_manager = None
llama_index = None

def get_chat_manager():
    """获取聊天管理器实例（懒加载）"""
    global chat_manager
    if chat_manager is None:
        try:
            chat_manager = ChatManager()
            logger.info("聊天管理器初始化成功")
        except Exception:
            logger.error("聊天管理器初始化失败")
            raise
    return chat_manager

def get_doc_manager():
    """获取文档管理器实例（懒加载）"""
    global doc_manager
    if doc_manager is None:
        doc_manager = UniversityDocumentManager()
        logger.info("文档管理器初始化成功")
    return doc_manager

def get_llama_index():
    """获取LlamaIndex集成器实例（懒加载）"""
    global llama_index
    if llama_index is None:
        try:
            llama_index = LlamaIndexIntegration()
            logger.info("LlamaIndex集成器初始化成功")
        except Exception:
            logger.error("LlamaIndex集成器初始化失败")
            raise
    return llama_index


@chat_bp.route('/', methods=['GET'])
@admin_required
def chat_page():
    """聊天页面"""
    try:
        return render_template('admin/chat.html')
    except Exception as e:
        logger.error(f"渲染聊天页面时出错: {e}")
        return f"页面加载失败: {str(e)}", 500


@chat_bp.route('/api/universities/search', methods=['GET'])
@admin_required
@chat_api_protection(max_requests=30, time_window=60)
def search_universities():
    """搜索大学"""
    try:
        query = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 10))
        
        doc_mgr = get_doc_manager()
        
        if query:
            universities = doc_mgr.search_universities(query, limit)
        else:
            universities = doc_mgr.get_all_universities(limit)
        
        # 格式化返回数据
        results = []
        for uni in universities:
            result = {
                "id": str(uni["_id"]),
                "name": uni.get("university_name", ""),
                "name_zh": uni.get("university_name_zh", ""),
                "deadline": uni.get("deadline", ""),
                "is_premium": uni.get("is_premium", False)
            }
            
            # 格式化截止日期
            if result["deadline"]:
                try:
                    if isinstance(result["deadline"], datetime):
                        result["deadline"] = result["deadline"].strftime("%Y-%m-%d")
                    else:
                        result["deadline"] = str(result["deadline"])
                except (ValueError, TypeError, AttributeError):
                    result["deadline"] = str(result["deadline"])
            
            results.append(result)
        
        return jsonify({
            "success": True,
            "universities": results,
            "total": len(results)
        })
        
    except Exception as e:
        logger.error(f"搜索大学时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"搜索失败: {str(e)}"
        }), 500


@chat_bp.route('/api/load-university', methods=['POST'])
@admin_required
def load_university():
    """加载大学文档"""
    try:
        data = request.get_json()
        if not data or not data.get('university_id'):
            return jsonify({
                "success": False,
                "error": "缺少university_id参数"
            }), 400
        
        university_id = data['university_id']
        
        # 获取大学文档
        doc_mgr = get_doc_manager()
        university_doc = doc_mgr.get_university_by_id(university_id)
        
        if not university_doc:
            return jsonify({
                "success": False,
                "error": "未找到指定的大学"
            }), 404
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 返回任务ID，客户端可以用来监听进度
        return jsonify({
            "success": True,
            "task_id": task_id,
            "university_name": university_doc.get("university_name", ""),
            "message": "开始加载大学文档"
        })
        
    except Exception as e:
        logger.error(f"加载大学文档时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"加载失败: {str(e)}"
        }), 500


@chat_bp.route('/api/load-progress/<task_id>')
@admin_required
def load_progress(task_id):
    """获取加载进度（SSE）"""
    # task_id参数暂未使用，预留用于实际任务跟踪
    def generate_progress():
        try:
            # 模拟进度更新
            yield f"data: {json.dumps({'progress': 0, 'message': '开始处理...', 'status': 'running'})}\n\n"
            time.sleep(0.5)
            
            # 这里应该根据实际的任务状态来更新进度
            # 现在简化为模拟进度
            for progress in [20, 40, 60, 80, 100]:
                if progress == 100:
                    message = "加载完成"
                    status = "completed"
                else:
                    message = f"处理中... {progress}%"
                    status = "running"
                
                yield f"data: {json.dumps({'progress': progress, 'message': message, 'status': status})}\n\n"
                time.sleep(0.5)
                
        except Exception as e:
            logger.error(f"进度更新时出错: {e}")
            yield f"data: {json.dumps({'progress': -1, 'message': f'错误: {str(e)}', 'status': 'error'})}\n\n"
    
    response = Response(
        stream_with_context(generate_progress()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
        }
    )
    
    return response


@chat_bp.route('/api/create-session', methods=['POST'])
@admin_required
@chat_api_protection(max_requests=10, time_window=60)
def create_session():
    """创建对话会话"""
    try:
        data = request.get_json()
        if not data or not data.get('university_id'):
            return jsonify({
                "success": False,
                "error": "缺少university_id参数"
            }), 400
        
        university_id = data['university_id']
        
        # 创建会话
        chat_mgr = get_chat_manager()
        session = chat_mgr.create_chat_session(university_id)
        
        if not session:
            return jsonify({
                "success": False,
                "error": "创建会话失败"
            }), 500
        
        # 生成CSRF令牌
        csrf_token = get_csrf_token_for_session(session.session_id)
        
        session_data = session.to_dict()
        session_data['csrf_token'] = csrf_token
        
        response = jsonify({
            "success": True,
            "session": session_data
        })
        
        # 添加安全头
        return add_security_headers(response)
        
    except Exception as e:
        logger.error(f"创建会话时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"创建会话失败: {str(e)}"
        }), 500


@chat_bp.route('/api/send-message', methods=['POST'])
@admin_required  
@chat_api_protection(max_requests=20, time_window=60)
def send_message():
    """发送消息"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "请求数据格式错误"
            }), 400
        
        session_id = data.get('session_id')
        message = data.get('message', '').strip()
        
        if not session_id:
            return jsonify({
                "success": False,
                "error": "缺少session_id参数"
            }), 400
        
        if not message:
            return jsonify({
                "success": False,
                "error": "消息内容不能为空"
            }), 400
        
        # 处理消息
        chat_mgr = get_chat_manager()
        result = chat_mgr.process_message(session_id, message)
        
        response = jsonify(result)
        return add_security_headers(response)
        
    except Exception as e:
        logger.error(f"发送消息时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"发送消息失败: {str(e)}",
            "error_code": "SEND_MESSAGE_ERROR"
        }), 500


@chat_bp.route('/api/session/<session_id>/history', methods=['GET'])
@admin_required
@chat_api_protection(max_requests=60, time_window=60)
def get_session_history(session_id):
    """获取会话历史"""
    try:
        chat_mgr = get_chat_manager()
        history = chat_mgr.get_session_history(session_id)
        
        if history is None:
            return jsonify({
                "success": False,
                "error": "会话不存在或已过期"
            }), 404
        
        response = jsonify({
            "success": True,
            "history": history
        })
        return add_security_headers(response)
        
    except Exception as e:
        logger.error(f"获取会话历史时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"获取历史失败: {str(e)}"
        }), 500


@chat_bp.route('/api/session/<session_id>/clear', methods=['POST'])
@admin_required
@chat_api_protection(max_requests=10, time_window=60)
def clear_session_history(session_id):
    """清空会话历史"""
    try:
        chat_mgr = get_chat_manager()
        success = chat_mgr.clear_session_history(session_id)
        
        if not success:
            return jsonify({
                "success": False,
                "error": "会话不存在或已过期"
            }), 404
        
        response = jsonify({
            "success": True,
            "message": "会话历史已清空"
        })
        return add_security_headers(response)
        
    except Exception as e:
        logger.error(f"清空会话历史时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"清空历史失败: {str(e)}"
        }), 500


@chat_bp.route('/api/session/<session_id>', methods=['DELETE'])
@admin_required
def delete_session(session_id):
    """删除会话"""
    try:
        chat_mgr = get_chat_manager()
        success = chat_mgr.cleanup_session(session_id)
        
        if not success:
            return jsonify({
                "success": False,
                "error": "会话不存在"
            }), 404
        
        return jsonify({
            "success": True,
            "message": "会话已删除"
        })
        
    except Exception as e:
        logger.error(f"删除会话时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"删除会话失败: {str(e)}"
        }), 500


@chat_bp.route('/api/sessions', methods=['GET'])
@admin_required
def get_active_sessions():
    """获取活跃会话列表"""
    try:
        chat_mgr = get_chat_manager()
        sessions = chat_mgr.get_active_sessions()
        
        return jsonify({
            "success": True,
            "sessions": sessions,
            "total": len(sessions)
        })
        
    except Exception as e:
        logger.error(f"获取会话列表时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"获取会话列表失败: {str(e)}"
        }), 500


@chat_bp.route('/api/stats', methods=['GET'])
@admin_required
def get_chat_stats():
    """获取聊天系统统计信息"""
    try:
        chat_mgr = get_chat_manager()
        stats = chat_mgr.get_stats()
        
        return jsonify({
            "success": True,
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"获取统计信息时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"获取统计信息失败: {str(e)}"
        }), 500


@chat_bp.route('/api/cleanup', methods=['POST'])
@admin_required
def cleanup_expired_sessions():
    """清理过期会话"""
    try:
        chat_mgr = get_chat_manager()
        cleaned_count = chat_mgr.cleanup_expired_sessions()
        
        return jsonify({
            "success": True,
            "cleaned_sessions": cleaned_count,
            "message": f"已清理 {cleaned_count} 个过期会话"
        })
        
    except Exception as e:
        logger.error(f"清理过期会话时出错: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"清理失败: {str(e)}"
        }), 500


# 错误处理
@chat_bp.errorhandler(404)
def not_found(error):
    # error参数在此处未使用，但需要保留以符合Flask错误处理器签名
    return jsonify({
        "success": False,
        "error": "API端点不存在",
        "error_code": "NOT_FOUND"
    }), 404


@chat_bp.errorhandler(500)
def internal_error(error):
    logger.error(f"内部服务器错误: {error}")
    return jsonify({
        "success": False,
        "error": "内部服务器错误",
        "error_code": "INTERNAL_ERROR"
    }), 500
