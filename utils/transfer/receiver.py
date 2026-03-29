"""
传输接收端：验证请求、检测冲突、存储数据到 MongoDB + GridFS。
"""
from datetime import datetime
import hashlib
import json
import logging
import os
import uuid

from bson.objectid import ObjectId
from gridfs import GridFS

from utils.core.database import get_db

logger = logging.getLogger(__name__)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _compute_existing_checksum(db, pdf_file_id) -> str:
    """计算已有大学的 PDF checksum"""
    fs = GridFS(db)
    try:
        grid_out = fs.get(pdf_file_id)
        pdf_data = grid_out.read()
        return _sha256_bytes(pdf_data)
    except Exception as e:
        logger.warning(f"读取已有 PDF 计算 checksum 失败: {e}")
        return ""


def verify_token(request_token: str) -> bool:
    """验证传输 token"""
    expected = os.getenv("TRANSFER_SECRET_TOKEN", "").strip()
    if not expected:
        return False
    return request_token == expected


def receive_university(data_json: str, pdf_data: bytes, original_filename: str) -> dict:
    """
    接收并处理一个大学的传输数据。

    Returns:
        dict with keys: success (bool), message (str), status (str), http_code (int)
        status: "created" | "updated" | "conflict"
    """
    db = get_db()
    if db is None:
        return {"success": False, "message": "数据库连接失败", "status": "error", "http_code": 500}

    # 解析数据
    try:
        data = json.loads(data_json)
    except (json.JSONDecodeError, TypeError) as e:
        return {"success": False, "message": f"JSON 解析失败: {e}", "status": "error", "http_code": 400}

    university_name = data.get("university_name", "").strip()
    if not university_name:
        return {"success": False, "message": "缺少 university_name", "status": "error", "http_code": 400}

    incoming_checksum = data.get("pdf_checksum", "")
    if not incoming_checksum:
        # 自行计算
        incoming_checksum = _sha256_bytes(pdf_data)

    # 验证 PDF checksum
    actual_checksum = _sha256_bytes(pdf_data)
    if incoming_checksum != actual_checksum:
        return {"success": False, "message": "PDF checksum 校验失败，数据可能在传输中损坏", "status": "error", "http_code": 400}

    # 查找是否已存在同名大学（取最新的）
    existing = db.universities.find_one({"university_name": university_name}, sort=[("_id", -1)])

    if existing:
        existing_pdf_file_id = existing.get("content", {}).get("pdf_file_id")
        existing_checksum = ""
        if existing_pdf_file_id:
            existing_checksum = _compute_existing_checksum(db, existing_pdf_file_id)

        if existing_checksum == incoming_checksum:
            # PDF 相同，自动覆盖文本内容
            return _update_existing(db, existing, data, pdf_data, original_filename, incoming_checksum)
        else:
            # PDF 不同，创建冲突记录
            return _create_conflict(db, existing, data, pdf_data, original_filename, incoming_checksum, existing_checksum)
    else:
        # 新大学，直接插入
        return _insert_new(db, data, pdf_data, original_filename, incoming_checksum)


def _parse_datetime(value):
    """解析 ISO 格式日期字符串"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _insert_new(db, data: dict, pdf_data: bytes, original_filename: str, checksum: str) -> dict:
    """插入新大学"""
    fs = GridFS(db)
    pdf_file_id = fs.put(
        pdf_data,
        filename=str(uuid.uuid4()),
        metadata={
            "university_name": data.get("university_name", ""),
            "university_name_zh": data.get("university_name_zh", ""),
            "deadline": _parse_datetime(data.get("deadline")),
            "upload_time": datetime.utcnow(),
            "original_filename": original_filename,
            "source": "transfer",
            "checksum": checksum,
        },
    )

    content = data.get("content", {})
    university_doc = {
        "university_name": data.get("university_name", ""),
        "university_name_zh": data.get("university_name_zh", ""),
        "deadline": _parse_datetime(data.get("deadline")) or datetime.utcnow(),
        "created_at": _parse_datetime(data.get("created_at")) or datetime.utcnow(),
        "is_premium": data.get("is_premium", False),
        "tags": data.get("tags", []),
        "content": {
            "original_md": content.get("original_md", ""),
            "translated_md": content.get("translated_md", ""),
            "report_md": content.get("report_md", ""),
            "pdf_file_id": pdf_file_id,
        },
    }

    result = db.universities.insert_one(university_doc)
    logger.info(f"传输接收：新插入大学 {data.get('university_name')} (ID: {result.inserted_id})")

    return {
        "success": True,
        "message": f"新增大学: {data.get('university_name')}",
        "status": "created",
        "http_code": 201,
    }


def _update_existing(db, existing: dict, data: dict, pdf_data: bytes, original_filename: str, checksum: str) -> dict:
    """PDF checksum 相同时覆盖更新"""
    content = data.get("content", {})
    update_fields = {
        "university_name_zh": data.get("university_name_zh", existing.get("university_name_zh", "")),
        "deadline": _parse_datetime(data.get("deadline")) or existing.get("deadline"),
        "is_premium": data.get("is_premium", existing.get("is_premium", False)),
        "tags": data.get("tags", existing.get("tags", [])),
        "content.original_md": content.get("original_md", ""),
        "content.translated_md": content.get("translated_md", ""),
        "content.report_md": content.get("report_md", ""),
        "last_modified": datetime.utcnow(),
    }

    db.universities.update_one({"_id": existing["_id"]}, {"$set": update_fields})
    logger.info(f"传输接收：覆盖更新大学 {data.get('university_name')} (ID: {existing['_id']})")

    return {
        "success": True,
        "message": f"已覆盖更新: {data.get('university_name')}（PDF 相同）",
        "status": "updated",
        "http_code": 200,
    }


def _create_conflict(db, existing: dict, data: dict, pdf_data: bytes, original_filename: str, incoming_checksum: str, existing_checksum: str) -> dict:
    """PDF 不同时创建冲突记录"""
    # 将传入的 PDF 临时存入 GridFS
    fs = GridFS(db)
    temp_pdf_id = fs.put(
        pdf_data,
        filename=str(uuid.uuid4()),
        metadata={
            "university_name": data.get("university_name", ""),
            "purpose": "transfer_conflict",
            "original_filename": original_filename,
            "checksum": incoming_checksum,
        },
    )

    conflict_doc = {
        "university_name": data.get("university_name", ""),
        "incoming_data": data,
        "incoming_pdf_id": temp_pdf_id,
        "incoming_checksum": incoming_checksum,
        "existing_university_id": existing["_id"],
        "existing_checksum": existing_checksum,
        "status": "pending",
        "received_at": datetime.utcnow(),
        "resolved_at": None,
        "resolution": None,
    }

    result = db.transfer_conflicts.insert_one(conflict_doc)
    logger.info(f"传输接收：冲突 {data.get('university_name')} (conflict ID: {result.inserted_id})")

    return {
        "success": True,
        "message": f"冲突待处理: {data.get('university_name')}（PDF 不同）",
        "status": "conflict",
        "http_code": 200,
    }


def resolve_conflict(conflict_id: str, action: str) -> dict:
    """
    处理冲突：接受或拒绝。

    Args:
        conflict_id: 冲突记录 ID
        action: "accept" 或 "reject"

    Returns:
        dict with keys: success (bool), message (str)
    """
    if action not in ("accept", "reject"):
        return {"success": False, "message": "无效操作，必须是 accept 或 reject"}

    db = get_db()
    if db is None:
        return {"success": False, "message": "数据库连接失败"}

    try:
        conflict = db.transfer_conflicts.find_one({"_id": ObjectId(conflict_id)})
    except Exception:
        return {"success": False, "message": f"无效的冲突 ID: {conflict_id}"}

    if not conflict:
        return {"success": False, "message": "冲突记录不存在"}

    if conflict.get("status") != "pending":
        return {"success": False, "message": f"冲突已处理: {conflict.get('resolution')}"}

    fs = GridFS(db)

    if action == "accept":
        # 用传入数据覆盖现有数据
        data = conflict.get("incoming_data", {})
        incoming_pdf_id = conflict.get("incoming_pdf_id")
        existing_id = conflict.get("existing_university_id")

        existing = db.universities.find_one({"_id": existing_id})
        if not existing:
            return {"success": False, "message": "原有大学记录已不存在"}

        # 删除旧 PDF
        old_pdf_id = existing.get("content", {}).get("pdf_file_id")
        if old_pdf_id:
            try:
                fs.delete(old_pdf_id)
            except Exception as e:
                logger.warning(f"删除旧 PDF 失败: {e}")

        # 读取冲突中临时存储的 PDF 并重新保存（更新 metadata）
        try:
            grid_out = fs.get(incoming_pdf_id)
            pdf_data = grid_out.read()
            old_metadata = grid_out.metadata or {}
        except Exception as e:
            return {"success": False, "message": f"读取传入 PDF 失败: {e}"}

        new_pdf_id = fs.put(
            pdf_data,
            filename=str(uuid.uuid4()),
            metadata={
                "university_name": data.get("university_name", ""),
                "university_name_zh": data.get("university_name_zh", ""),
                "deadline": _parse_datetime(data.get("deadline")),
                "upload_time": datetime.utcnow(),
                "original_filename": old_metadata.get("original_filename", "unknown.pdf"),
                "source": "transfer",
                "checksum": conflict.get("incoming_checksum", ""),
            },
        )

        # 更新大学文档
        content = data.get("content", {})
        update_fields = {
            "university_name_zh": data.get("university_name_zh", ""),
            "deadline": _parse_datetime(data.get("deadline")) or existing.get("deadline"),
            "is_premium": data.get("is_premium", False),
            "tags": data.get("tags", []),
            "content.original_md": content.get("original_md", ""),
            "content.translated_md": content.get("translated_md", ""),
            "content.report_md": content.get("report_md", ""),
            "content.pdf_file_id": new_pdf_id,
            "last_modified": datetime.utcnow(),
        }
        db.universities.update_one({"_id": existing_id}, {"$set": update_fields})

        # 删除临时 PDF
        try:
            fs.delete(incoming_pdf_id)
        except Exception:
            pass

        # 更新冲突状态
        db.transfer_conflicts.update_one({"_id": conflict["_id"]}, {"$set": {"status": "resolved", "resolution": "accepted", "resolved_at": datetime.utcnow()}})

        logger.info(f"冲突已接受: {data.get('university_name')}")
        return {"success": True, "message": f"已接受: {data.get('university_name')}"}

    else:  # reject
        # 删除临时 PDF
        incoming_pdf_id = conflict.get("incoming_pdf_id")
        if incoming_pdf_id:
            try:
                fs.delete(incoming_pdf_id)
            except Exception as e:
                logger.warning(f"删除临时 PDF 失败: {e}")

        # 更新冲突状态
        db.transfer_conflicts.update_one({"_id": conflict["_id"]}, {"$set": {"status": "resolved", "resolution": "rejected", "resolved_at": datetime.utcnow()}})

        logger.info(f"冲突已拒绝: {conflict.get('university_name')}")
        return {"success": True, "message": f"已拒绝: {conflict.get('university_name')}"}


def get_pending_conflicts() -> list:
    """获取所有待处理的冲突"""
    db = get_db()
    if db is None:
        return []

    conflicts = list(db.transfer_conflicts.find({"status": "pending"}).sort("received_at", -1))
    result = []
    for c in conflicts:
        result.append({
            "_id": str(c["_id"]),
            "university_name": c.get("university_name", ""),
            "incoming_checksum": c.get("incoming_checksum", "")[:12] + "...",
            "existing_checksum": c.get("existing_checksum", "")[:12] + "...",
            "received_at": c.get("received_at").isoformat() if c.get("received_at") else "",
            "incoming_university_name_zh": c.get("incoming_data", {}).get("university_name_zh", ""),
            "incoming_deadline": c.get("incoming_data", {}).get("deadline", ""),
        })
    return result
