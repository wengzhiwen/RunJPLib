"""
批量OCR工具类 - 使用 OpenAI Batch API（Responses API 格式）进行成本优化的 OCR 处理

提供两种批处理模式：
  - PDF 模式（submit_batch_ocr_pdf）：将整份 PDF 作为一个请求，使用 input_file 格式
  - 图像模式（submit_batch_ocr_images）：将图像列表逐一打包，用于 asset 图片识别
"""

import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Dict, List, Optional, Tuple

from ..core.database import get_db
from ..core.logging import setup_logger

logger = setup_logger(logger_name="BatchOcrProcessor", log_level="INFO")

try:
    from openai import OpenAI
except ImportError:
    logger.error("需要安装 openai 包：pip install openai>=1.54.0")
    raise

_BATCH_ENDPOINT = "/v1/responses"

_OCR_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "full_markdown": {
            "type": "string",
            "description": "完整的文档Markdown内容。若文档无有效内容，返回字符串 EMPTY_PAGE。",
        },
        "document_type": {
            "type": "string",
            "description": "文档类型，如「募集要项」「出願要件」「大学案内」等。",
        },
    },
    "required": ["full_markdown", "document_type"],
    "additionalProperties": False,
}

_PDF_OCR_PROMPT = """你是一个专业的OCR文本识别与Markdown格式化专家。
请对上传的PDF文档进行整体识别和提取，直接输出结构化结果。

识别要求：
1. 提取文档中所有文本内容，包括正文、标题、表格
2. 保持原始日语文本，不要翻译
3. 忽略所有纯图形内容（logo、地图、水印等）
4. 忽略页眉和页脚，但保留原文中标注的页码
5. 针对表格，使用Markdown表格语法精确提取，严格保证列数（包括空单元格首行也要算作一列）

Markdown格式化要求：
1. 输出标准Markdown，表格/列表/标题前后保留空行
2. 目录中的点状导引（..........）最多使用6个点（......）
3. URL保持纯文本形式，不使用Markdown链接格式
4. 不要添加任何```markdown```之类的定界符
5. 若整份文档无有效内容，full_markdown字段返回字符串 EMPTY_PAGE

请将完整的文档Markdown写入full_markdown字段，将文档类型写入document_type字段。"""


class BatchOcrProcessor:
    """批量OCR处理器，使用 OpenAI Batch API（Responses API 格式）处理 OCR 识别。"""

    def __init__(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY 环境变量未设置")
        self.model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-5.4-mini")
        self.client = OpenAI()
        self.max_images_per_batch = 40
        self.max_file_size_mb = 150

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def submit_batch_ocr_pdf(self, pdf_path: str, task_id: str) -> List[str]:
        """
        将整份 PDF 作为一个 Batch 请求提交，使用 Responses API + Structured Outputs。

        参数:
            pdf_path: PDF 文件路径
            task_id: 任务 ID

        返回:
            batch_id 列表（PDF 模式只有一个 batch）
        """
        pdf_file = None
        jsonl_path = None
        try:
            # 1. 上传 PDF 文件（purpose="user_data"，供 Responses API 使用）
            logger.info(f"上传 PDF 至 Files API: {pdf_path}")
            with open(pdf_path, "rb") as f:
                pdf_file = self.client.files.create(file=f, purpose="user_data")
            logger.info(f"PDF 已上传，file_id: {pdf_file.id}")

            # 2. 创建包含单个请求的 JSONL
            jsonl_path = self._create_pdf_batch_jsonl(pdf_file.id, task_id)

            # 3. 上传 JSONL 并提交 Batch 作业
            with open(jsonl_path, "rb") as f:
                input_file = self.client.files.create(purpose="batch", file=f)

            batch = self.client.batches.create(
                input_file_id=input_file.id,
                endpoint=_BATCH_ENDPOINT,
                completion_window="24h",
                metadata={
                    "task_id": task_id,
                    "batch_index": "1",
                    "mode": "pdf",
                },
            )

            self._save_batch_info(
                task_id=task_id,
                batch_id=batch.id,
                batch_index=1,
                start_page=1,
                end_page=1,
                input_file_id=input_file.id,
                pdf_file_id=pdf_file.id,
                result_format="json_schema",
            )

            logger.info(f"PDF Batch 已提交: {batch.id}，任务: {task_id}")
            return [batch.id]

        except Exception as e:
            # 提交失败时清理已上传的 PDF 文件
            if pdf_file:
                try:
                    self.client.files.delete(pdf_file.id)
                except Exception:
                    pass
            logger.error(f"提交 PDF Batch OCR 失败: {e}")
            raise

        finally:
            if jsonl_path:
                try:
                    os.unlink(jsonl_path)
                except OSError:
                    pass

    def submit_batch_ocr_images(
        self,
        image_paths: List[str],
        task_id: str,
        prompt: Optional[str] = None,
        page_numbers: Optional[List[int]] = None,
    ) -> List[str]:
        """
        将图像列表以 Batch 方式提交（用于 asset 图片识别）。

        参数:
            image_paths: 图像路径列表
            task_id: 任务 ID
            prompt: 自定义提示词（不传则使用默认）
            page_numbers: 与 image_paths 对应的页码列表（不传则按顺序编号）

        返回:
            batch_id 列表
        """
        if not image_paths:
            return []

        if prompt is None:
            prompt = self._create_asset_prompt()
        if page_numbers is None:
            page_numbers = list(range(1, len(image_paths) + 1))

        total_images = len(image_paths)
        batch_ranges = self._calculate_optimal_batches(total_images)
        batch_ids = []

        try:
            for batch_idx, (start_idx, end_idx) in enumerate(batch_ranges, 1):
                batch_image_paths = image_paths[start_idx - 1:end_idx]
                batch_page_numbers = page_numbers[start_idx - 1:end_idx]

                logger.info(f"准备图像批次 {batch_idx}: {len(batch_image_paths)} 张图像")

                jsonl_path = self._create_image_batch_jsonl(
                    batch_image_paths,
                    batch_page_numbers,
                    batch_idx,
                    prompt,
                )
                try:
                    with open(jsonl_path, "rb") as f:
                        input_file = self.client.files.create(purpose="batch", file=f)

                    batch = self.client.batches.create(
                        input_file_id=input_file.id,
                        endpoint=_BATCH_ENDPOINT,
                        completion_window="24h",
                        metadata={
                            "task_id": task_id,
                            "batch_index": str(batch_idx),
                            "mode": "image",
                        },
                    )

                    batch_ids.append(batch.id)
                    self._save_batch_info(
                        task_id=task_id,
                        batch_id=batch.id,
                        batch_index=batch_idx,
                        start_page=batch_page_numbers[0],
                        end_page=batch_page_numbers[-1],
                        input_file_id=input_file.id,
                        result_format="text",
                    )
                    logger.info(f"图像批次 {batch_idx} 已提交: {batch.id}")

                finally:
                    try:
                        os.unlink(jsonl_path)
                    except OSError:
                        pass

            logger.info(f"任务 {task_id} 所有图像批次已提交，共 {len(batch_ids)} 个")
            return batch_ids

        except Exception as e:
            logger.error(f"提交图像 Batch OCR 失败: {e}")
            raise

    def check_batch_status(self, task_id: str) -> Dict:
        """检查任务的所有批次状态。"""
        try:
            db = get_db()
            if db is None:
                return {"error": "无法连接到数据库"}

            batches = list(db.ocr_batches.find({"task_id": task_id}).sort("batch_index", 1))
            if not batches:
                return {"error": "未找到批次信息"}

            total_batches = len(batches)
            completed_batches = 0
            failed_batches = 0
            processing_batches = 0
            batch_statuses = []

            for batch_info in batches:
                batch_id = batch_info["batch_id"]
                try:
                    batch = self.client.batches.retrieve(batch_id)
                    status = batch.status
                    db.ocr_batches.update_one({"batch_id": batch_id}, {"$set": {"status": status, "updated_at": time.time()}})

                    batch_status = {
                        "batch_id": batch_id,
                        "batch_index": batch_info["batch_index"],
                        "start_page": batch_info["start_page"],
                        "end_page": batch_info["end_page"],
                        "status": status,
                    }
                    if status == "completed":
                        completed_batches += 1
                        if hasattr(batch, "output_file_id") and batch.output_file_id:
                            batch_status["output_file_id"] = batch.output_file_id
                    elif status in ("failed", "cancelled", "expired"):
                        failed_batches += 1
                    else:
                        processing_batches += 1

                    batch_statuses.append(batch_status)

                except Exception as e:
                    logger.error(f"检查批次 {batch_id} 状态失败: {e}")
                    batch_statuses.append({
                        "batch_id": batch_id,
                        "batch_index": batch_info["batch_index"],
                        "start_page": batch_info["start_page"],
                        "end_page": batch_info["end_page"],
                        "status": "error",
                        "error": str(e),
                    })
                    failed_batches += 1

            return {
                "total_batches": total_batches,
                "completed_batches": completed_batches,
                "failed_batches": failed_batches,
                "processing_batches": processing_batches,
                "all_completed": completed_batches == total_batches,
                "batch_statuses": batch_statuses,
            }

        except Exception as e:
            logger.error(f"检查批次状态失败: {e}")
            return {"error": str(e)}

    def retrieve_batch_results(self, task_id: str) -> Dict[str, str]:
        """
        获取所有批次的结果并合并。

        返回:
            页面结果字典 {页码字符串（3位补零）: markdown内容}
            PDF 模式只有一个键 "001"，包含完整文档 markdown。
        """
        try:
            db = get_db()
            if db is None:
                raise ValueError("无法连接到数据库")

            completed_batches = list(db.ocr_batches.find({"task_id": task_id, "status": "completed"}).sort("batch_index", 1))

            page_results = {}

            for batch_info in completed_batches:
                batch_id = batch_info["batch_id"]
                result_format = batch_info.get("result_format", "text")

                logger.info(f"处理批次 {batch_info['batch_index']} 结果: {batch_id} (格式: {result_format})")

                try:
                    batch = self.client.batches.retrieve(batch_id)
                    if not getattr(batch, "output_file_id", None):
                        logger.error(f"批次 {batch_id} 没有输出文件")
                        continue

                    content = self.client.files.content(batch.output_file_id).text

                    for line in content.strip().split("\n"):
                        if not line.strip():
                            continue
                        try:
                            result_obj = json.loads(line)
                        except json.JSONDecodeError as e:
                            logger.error(f"解析结果行失败: {e}")
                            continue

                        custom_id = result_obj.get("custom_id", "")
                        page_key = self._extract_page_key(custom_id, batch_info["batch_index"])
                        if page_key is None:
                            continue

                        if result_obj.get("error"):
                            logger.error(f"批次请求 {custom_id} 出错: {result_obj['error']}")
                            continue

                        # Responses API 输出格式
                        response = result_obj.get("response", {})
                        body = response.get("body", {})
                        output_text = self._extract_output_text(body)

                        if not output_text:
                            logger.warning(f"批次请求 {custom_id} 内容为空")
                            continue

                        if result_format == "json_schema":
                            try:
                                parsed = json.loads(output_text)
                                md = parsed.get("full_markdown", "")
                            except (json.JSONDecodeError, AttributeError):
                                md = output_text
                        else:
                            md = output_text

                        # 清理定界符
                        for marker in ("```markdown", "```Markdown", "```"):
                            md = md.replace(marker, "")
                        md = md.strip()

                        if md:
                            page_results[page_key] = md
                            logger.info(f"批次请求 {custom_id} 处理成功")

                except Exception as e:
                    logger.error(f"处理批次 {batch_id} 结果失败: {e}")

            return page_results

        except Exception as e:
            logger.error(f"获取批次结果失败: {e}")
            raise

    def cleanup_batch_data(self, task_id: str):
        """清理批次相关数据（包括已上传的 PDF 文件）。"""
        try:
            db = get_db()
            if db is None:
                return

            batches = list(db.ocr_batches.find({"task_id": task_id}))
            for batch_info in batches:
                pdf_file_id = batch_info.get("pdf_file_id")
                if pdf_file_id:
                    try:
                        self.client.files.delete(pdf_file_id)
                        logger.info(f"已删除 PDF 文件: {pdf_file_id}")
                    except Exception as e:
                        logger.warning(f"删除 PDF 文件失败 {pdf_file_id}: {e}")

            result = db.ocr_batches.delete_many({"task_id": task_id})
            logger.info(f"已清理任务 {task_id} 的 {result.deleted_count} 条批次记录")

        except Exception as e:
            logger.error(f"清理批次数据失败: {e}")

    def _create_asset_prompt(self) -> str:
        """返回用于 asset 图片识别的提示词。"""
        return """你是一个专业的OCR文本识别与Markdown格式化专家。
请仔细识别图像中的所有文本内容，直接输出为标准Markdown格式。

要求：
1. 仅提取图像中的实际文本，不要添加任何解释或说明
2. 保持原始日语文本，不要翻译
3. 表格使用Markdown表格语法精确提取，注意列数（包括空单元格）
4. 忽略纯图形内容（logo、地图、水印等）
5. 忽略页眉页脚，但保留原文中标注的页码
6. 如果图像没有有效文字内容，返回：EMPTY_PAGE
7. 不要添加任何```markdown```之类的定界符，直接输出Markdown文本"""

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _calculate_optimal_batches(self, total_images: int) -> List[Tuple[int, int]]:
        """计算最优批次分配，返回 (start_idx, end_idx) 列表（1-based）。"""
        if total_images <= self.max_images_per_batch:
            return [(1, total_images)]

        num_batches = math.ceil(total_images / self.max_images_per_batch)
        base_size = total_images // num_batches
        remainder = total_images % num_batches

        batches = []
        start = 1
        for i in range(num_batches):
            size = base_size + (1 if i < remainder else 0)
            batches.append((start, start + size - 1))
            start += size

        logger.info(f"总图像数 {total_images}，分配为 {num_batches} 批：{batches}")
        return batches

    def _create_pdf_batch_jsonl(self, pdf_file_id: str, task_id: str) -> str:
        """创建 PDF 模式的 Batch JSONL 文件（单个请求）。"""
        fd, jsonl_path = tempfile.mkstemp(suffix=f"_pdf_batch_{task_id}.jsonl")
        os.close(fd)

        request_body = {
            "model": self.model_name,
            "input": [{
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_id": pdf_file_id,
                    },
                    {
                        "type": "input_text",
                        "text": _PDF_OCR_PROMPT,
                    },
                ],
            }],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "ocr_result",
                    "schema": _OCR_JSON_SCHEMA,
                    "strict": True,
                }
            },
        }

        line = {
            "custom_id": f"task_{task_id}_page_001",
            "method": "POST",
            "url": _BATCH_ENDPOINT,
            "body": request_body,
        }

        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

        return jsonl_path

    def _create_image_batch_jsonl(
        self,
        image_paths: List[str],
        page_numbers: List[int],
        batch_id: int,
        prompt: str,
    ) -> str:
        """创建图像模式的 Batch JSONL 文件。"""
        import base64
        fd, jsonl_path = tempfile.mkstemp(suffix=f"_img_batch_{batch_id}.jsonl")
        os.close(fd)

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for image_path, page_num in zip(image_paths, page_numbers):
                try:
                    with open(image_path, "rb") as img_f:
                        image_data = base64.b64encode(img_f.read()).decode("utf-8")

                    if len(image_data) > 20 * 1024 * 1024:
                        logger.warning(f"图像 {image_path} 过大 ({len(image_data)/1024/1024:.1f}MB)，可能导致 API 失败")

                    request_body = {
                        "model":
                        self.model_name,
                        "input": [{
                            "role":
                            "user",
                            "content": [
                                {
                                    "type": "input_image",
                                    "detail": "high",
                                    "image_url": f"data:image/png;base64,{image_data}",
                                },
                                {
                                    "type": "input_text",
                                    "text": prompt,
                                },
                            ],
                        }],
                    }

                    page_key = f"{page_num:03d}"
                    line = {
                        "custom_id": f"batch_{batch_id}_page_{page_key}",
                        "method": "POST",
                        "url": _BATCH_ENDPOINT,
                        "body": request_body,
                    }
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")

                except Exception as e:
                    logger.error(f"处理图像 {image_path} 失败: {e}")
                    continue

        file_size_mb = os.path.getsize(jsonl_path) / (1024 * 1024)
        logger.info(f"批次 {batch_id} JSONL 文件大小: {file_size_mb:.1f}MB")
        if file_size_mb > self.max_file_size_mb:
            logger.warning(f"批次 {batch_id} 文件大小超限 ({file_size_mb:.1f}MB > {self.max_file_size_mb}MB)")

        return jsonl_path

    def _save_batch_info(
        self,
        task_id: str,
        batch_id: str,
        batch_index: int,
        start_page: int,
        end_page: int,
        input_file_id: str,
        pdf_file_id: Optional[str] = None,
        result_format: str = "text",
    ):
        """保存批次信息到数据库。"""
        try:
            db = get_db()
            if db is None:
                logger.error("无法连接到数据库")
                return

            batch_info = {
                "task_id": task_id,
                "batch_id": batch_id,
                "batch_index": batch_index,
                "start_page": start_page,
                "end_page": end_page,
                "input_file_id": input_file_id,
                "result_format": result_format,
                "status": "submitted",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            if pdf_file_id:
                batch_info["pdf_file_id"] = pdf_file_id

            db.ocr_batches.insert_one(batch_info)
            logger.info(f"批次信息已保存: {batch_id}")

        except Exception as e:
            logger.error(f"保存批次信息失败: {e}")

    @staticmethod
    def _extract_output_text(body: dict) -> str:
        """从 Responses API batch 输出的 body 中提取文本内容。"""
        # 优先使用 output_text 字段（Responses API 的聚合属性）
        output_text = body.get("output_text")
        if output_text:
            return output_text

        # 备选：从 output 数组中提取
        for output_item in body.get("output", []):
            if output_item.get("type") == "message":
                for content in output_item.get("content", []):
                    if content.get("type") == "output_text":
                        text = content.get("text", "")
                        if text:
                            return text
        return ""

    @staticmethod
    def _extract_page_key(custom_id: str, batch_index: int) -> Optional[str]:
        """从 custom_id 提取页码键（3位补零字符串）。"""
        # PDF 模式：task_{task_id}_page_001
        if "_page_" in custom_id:
            parts = custom_id.rsplit("_page_", 1)
            if len(parts) == 2:
                page_part = parts[1]
                try:
                    return f"{int(page_part):03d}"
                except ValueError:
                    return None
        return None
