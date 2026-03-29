"""
数据传输路由：发送端（推送到生产服务器）和接收端（接收来自处理服务器的数据）
"""
import json
import logging

from flask import jsonify
from flask import render_template
from flask import request

from routes.admin.auth import admin_required
from utils.core.database import get_db
from utils.transfer.receiver import get_pending_conflicts
from utils.transfer.receiver import receive_university
from utils.transfer.receiver import resolve_conflict
from utils.transfer.receiver import verify_token
from utils.transfer.sender import get_transfer_config
from utils.transfer.sender import send_batch

from ..blueprints import admin_bp

logger = logging.getLogger(__name__)

# ============================================================
# 页面路由
# ============================================================


@admin_bp.route("/transfer")
@admin_required
def transfer_page():
    """传输管理页面"""
    return render_template("transfer.html")


# ============================================================
# 发送端 API（Server B 使用，需要 admin 登录）
# ============================================================


@admin_bp.route("/api/transfer/config", methods=["GET"])
@admin_required
def transfer_config():
    """获取传输配置状态"""
    return jsonify(get_transfer_config())


@admin_bp.route("/api/transfer/send", methods=["POST"])
@admin_required
def transfer_send():
    """传输选中的大学到目标服务器"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空"}), 400

        university_ids = data.get("university_ids", [])
        if not university_ids:
            return jsonify({"error": "未选择任何大学"}), 400

        if len(university_ids) > 50:
            return jsonify({"error": "单次最多传输 50 个"}), 400

        results = send_batch(university_ids)
        success_count = sum(1 for r in results if r["success"])
        conflict_count = sum(1 for r in results if r.get("status") == "conflict")

        return jsonify({
            "message": f"传输完成: {success_count}/{len(results)} 成功" + (f", {conflict_count} 个冲突待处理" if conflict_count else ""),
            "results": results,
            "summary": {
                "total": len(results),
                "success": success_count,
                "conflict": conflict_count,
                "error": len(results) - success_count - conflict_count,
            },
        })

    except Exception as e:
        logger.error(f"[Transfer] 发送失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/transfer/sendable-tasks", methods=["GET"])
@admin_required
def transfer_sendable_tasks():
    """获取可传输的已完成任务列表"""
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        tasks = list(
            db.processing_tasks.find({
                "status": "completed",
                "task_type": {
                    "$in": ["PDF_PROCESSING", "OCR_IMPORT"]
                },
            }).sort("updated_at", -1).limit(100))

        result = []
        for task in tasks:
            params = task.get("params", {})
            university_name = params.get("university_name", "")

            # 查找对应的大学记录
            uni = db.universities.find_one({"university_name": university_name}, sort=[("_id", -1)])

            if uni:
                result.append({
                    "task_id": str(task["_id"]),
                    "task_type": task.get("task_type", "PDF_PROCESSING"),
                    "university_name": university_name,
                    "university_name_zh": uni.get("university_name_zh", ""),
                    "university_id": str(uni["_id"]),
                    "original_filename": params.get("original_filename", ""),
                    "completed_at": task.get("updated_at").isoformat() if task.get("updated_at") else "",
                })

        return jsonify(result)

    except Exception as e:
        logger.error(f"[Transfer] 获取可传输任务失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/transfer/sendable-universities", methods=["GET"])
@admin_required
def transfer_sendable_universities():
    """获取可传输的大学列表"""
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        # 去重聚合，每个 university_name 取最新的
        pipeline = [
            {
                "$sort": {
                    "_id": -1
                }
            },
            {
                "$group": {
                    "_id": "$university_name",
                    "doc": {
                        "$first": "$$ROOT"
                    }
                }
            },
            {
                "$replaceRoot": {
                    "newRoot": "$doc"
                }
            },
            {
                "$sort": {
                    "_id": -1
                }
            },
            {
                "$project": {
                    "content.original_md": 0,
                    "content.translated_md": 0,
                    "content.report_md": 0
                }
            },
        ]
        universities = list(db.universities.aggregate(pipeline))

        result = []
        for uni in universities:
            result.append({
                "university_id": str(uni["_id"]),
                "university_name": uni.get("university_name", ""),
                "university_name_zh": uni.get("university_name_zh", ""),
                "deadline": uni["deadline"].isoformat() if uni.get("deadline") else "",
                "created_at": uni["created_at"].isoformat() if uni.get("created_at") else "",
                "is_premium": uni.get("is_premium", False),
                "has_pdf": bool(uni.get("content", {}).get("pdf_file_id")),
            })

        return jsonify(result)

    except Exception as e:
        logger.error(f"[Transfer] 获取大学列表失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


# ============================================================
# 接收端 API（Server A 使用，token 验证，不需要 admin 登录）
# ============================================================


@admin_bp.route("/api/transfer/receive", methods=["POST"])
def transfer_receive():
    """接收来自处理服务器的大学数据"""
    # Token 验证
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "缺少 Authorization 头"}), 401

    token = auth_header[7:]
    if not verify_token(token):
        return jsonify({"error": "Token 验证失败"}), 403

    # 解析请求
    data_json = request.form.get("data")
    if not data_json:
        return jsonify({"error": "缺少 data 字段"}), 400

    pdf_file = request.files.get("pdf")
    if not pdf_file:
        return jsonify({"error": "缺少 PDF 文件"}), 400

    pdf_data = pdf_file.read()
    if not pdf_data:
        return jsonify({"error": "PDF 文件为空"}), 400

    original_filename = pdf_file.filename or "unknown.pdf"

    result = receive_university(data_json, pdf_data, original_filename)
    http_code = result.pop("http_code", 200)

    if result["success"]:
        return jsonify(result), http_code
    else:
        return jsonify({"error": result["message"], "status": result.get("status", "error")}), http_code


# ============================================================
# 冲突管理 API（Server A 使用，需要 admin 登录）
# ============================================================


@admin_bp.route("/api/transfer/conflicts", methods=["GET"])
@admin_required
def transfer_conflicts():
    """获取待处理冲突列表"""
    conflicts = get_pending_conflicts()
    return jsonify(conflicts)


@admin_bp.route("/api/transfer/conflicts/<conflict_id>/resolve", methods=["POST"])
@admin_required
def transfer_resolve_conflict(conflict_id):
    """处理冲突"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空"}), 400

        action = data.get("action", "")
        if action not in ("accept", "reject"):
            return jsonify({"error": "action 必须是 accept 或 reject"}), 400

        result = resolve_conflict(conflict_id, action)
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify({"error": result["message"]}), 400

    except Exception as e:
        logger.error(f"[Transfer] 处理冲突失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500
