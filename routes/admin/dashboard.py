from datetime import datetime
from datetime import timedelta
import json
import logging
import time

from flask import jsonify
from flask import render_template
from flask import Response

from routes.admin.auth import admin_required
from utils.core.database import get_db
from utils.core.database import get_mongo_client
from utils.system.thread_pool import thread_pool_manager

from ..blueprints import admin_bp


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
