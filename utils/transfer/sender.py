"""
传输发送端：从本地 MongoDB 打包大学数据 + PDF，POST 到目标服务器。
"""
import hashlib
import logging
import os

from bson.objectid import ObjectId
from gridfs import GridFS
import requests

from utils.core.database import get_db

logger = logging.getLogger(__name__)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_transfer_config():
    """获取传输配置状态"""
    target_url = os.getenv("TRANSFER_TARGET_URL", "").strip().rstrip("/")
    token = os.getenv("TRANSFER_SECRET_TOKEN", "").strip()
    return {
        "target_url": target_url,
        "has_target_url": bool(target_url),
        "has_token": bool(token),
        "ready": bool(target_url and token),
    }


def send_university(university_id: str) -> dict:
    """
    将指定大学的数据传输到目标服务器。

    Returns:
        dict with keys: success (bool), message (str), status (str)
        status: "created" | "updated" | "conflict" | "error"
    """
    config = get_transfer_config()
    if not config["ready"]:
        return {"success": False, "message": "传输未配置：缺少 TRANSFER_TARGET_URL 或 TRANSFER_SECRET_TOKEN", "status": "error"}

    db = get_db()
    if db is None:
        return {"success": False, "message": "数据库连接失败", "status": "error"}

    # 查找大学文档
    try:
        uni_doc = db.universities.find_one({"_id": ObjectId(university_id)})
    except Exception:
        return {"success": False, "message": f"无效的大学 ID: {university_id}", "status": "error"}

    if not uni_doc:
        return {"success": False, "message": f"未找到大学: {university_id}", "status": "error"}

    # 从 GridFS 读取 PDF
    content = uni_doc.get("content", {})
    pdf_file_id = content.get("pdf_file_id")
    if not pdf_file_id:
        return {"success": False, "message": f"大学 {uni_doc.get('university_name')} 没有关联的 PDF 文件", "status": "error"}

    fs = GridFS(db)
    try:
        grid_out = fs.get(pdf_file_id)
        pdf_data = grid_out.read()
        original_filename = grid_out.metadata.get("original_filename", "unknown.pdf") if grid_out.metadata else "unknown.pdf"
    except Exception as e:
        return {"success": False, "message": f"读取 PDF 失败: {e}", "status": "error"}

    pdf_checksum = _sha256_bytes(pdf_data)

    # 构造传输数据（排除 _id 和 pdf_file_id）
    transfer_data = {
        "university_name": uni_doc.get("university_name", ""),
        "university_name_zh": uni_doc.get("university_name_zh", ""),
        "deadline": uni_doc["deadline"].isoformat() if uni_doc.get("deadline") else None,
        "created_at": uni_doc["created_at"].isoformat() if uni_doc.get("created_at") else None,
        "is_premium": uni_doc.get("is_premium", False),
        "tags": uni_doc.get("tags", []),
        "content": {
            "original_md": content.get("original_md", ""),
            "translated_md": content.get("translated_md", ""),
            "report_md": content.get("report_md", ""),
        },
        "pdf_checksum": pdf_checksum,
        "original_filename": original_filename,
    }

    # POST 到目标服务器
    target_url = os.getenv("TRANSFER_TARGET_URL", "").strip().rstrip("/")
    token = os.getenv("TRANSFER_SECRET_TOKEN", "").strip()
    url = f"{target_url}/api/transfer/receive"

    try:
        import json
        resp = requests.post(
            url,
            files={"pdf": (original_filename, pdf_data, "application/pdf")},
            data={"data": json.dumps(transfer_data, ensure_ascii=False)},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        )
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": f"无法连接目标服务器: {target_url}", "status": "error"}
    except requests.exceptions.Timeout:
        return {"success": False, "message": "请求超时（120秒）", "status": "error"}
    except Exception as e:
        return {"success": False, "message": f"请求失败: {e}", "status": "error"}

    try:
        result = resp.json()
    except Exception:
        return {"success": False, "message": f"目标服务器返回非 JSON 响应 (HTTP {resp.status_code})", "status": "error"}

    if resp.status_code == 200 or resp.status_code == 201:
        return {"success": True, "message": result.get("message", "传输成功"), "status": result.get("status", "created")}
    else:
        return {"success": False, "message": result.get("error", f"HTTP {resp.status_code}"), "status": "error"}


def send_batch(university_ids: list) -> list:
    """
    批量传输多个大学。

    Returns:
        list of dicts, each with: university_id, university_name, success, message, status
    """
    db = get_db()
    results = []
    for uid in university_ids:
        # 获取大学名称用于结果展示
        name = uid
        if db:
            try:
                doc = db.universities.find_one({"_id": ObjectId(uid)}, {"university_name": 1})
                if doc:
                    name = doc.get("university_name", uid)
            except Exception:
                pass

        result = send_university(uid)
        result["university_id"] = uid
        result["university_name"] = name
        results.append(result)
        logger.info(f"传输 {name}: {result['status']} - {result['message']}")

    return results
