"""
批量OCR工具类 - 使用OpenAI Batch API进行成本优化的OCR处理
"""

import base64
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Dict, List, Optional, Tuple

from utils.logging_config import setup_logger
from utils.mongo_client import get_db

logger = setup_logger(logger_name="BatchOCRTool", log_level="INFO")

try:
    from openai import OpenAI
except ImportError:
    logger.error("需要安装 openai 包：pip install openai>=1.54.0")
    raise


class BatchOCRTool:
    """批量OCR工具类，使用OpenAI Batch API处理图像OCR识别"""

    def __init__(self):
        """
        初始化批量OCR工具类
        """
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY 环境变量未设置")

        # 从环境变量读取模型名称
        self.model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-4o-mini")
        self.client = OpenAI()

        # 批处理配置
        self.max_pages_per_batch = 40  # 每批最大页数
        self.max_file_size_mb = 150  # 最大文件大小MB

    def _calculate_optimal_batches(self, total_pages: int) -> List[Tuple[int, int]]:
        """
        计算最优的批次分配
        
        参数:
            total_pages: 总页数
            
        返回:
            List[Tuple[int, int]]: 每批的(起始页, 结束页)列表
        """
        if total_pages <= self.max_pages_per_batch:
            return [(1, total_pages)]

        # 计算批次数
        num_batches = math.ceil(total_pages / self.max_pages_per_batch)
        pages_per_batch = total_pages // num_batches
        remaining_pages = total_pages % num_batches

        batches = []
        start_page = 1

        for i in range(num_batches):
            # 前面的批次多分配一页（如果有余数）
            batch_size = pages_per_batch + (1 if i < remaining_pages else 0)
            end_page = start_page + batch_size - 1
            batches.append((start_page, end_page))
            start_page = end_page + 1

        logger.info(f"总页数 {total_pages}，分配为 {num_batches} 批：{batches}")
        return batches

    def _create_combined_prompt(self) -> str:
        """创建合并的OCR+格式化提示词"""
        return """你是一个专业的OCR文本识别与Markdown格式化专家。
请仔细观察图像中的文本内容，尽可能准确地提取所有文本和表格，并直接输出为标准Markdown格式。

OCR识别要求：
1. 仅提取图像中的实际文本，不要添加任何解释或说明
2. 保持原始日语文本，不要翻译
3. 尽可能保持原始格式结构，特别是表格，要准确的提取表格中的所有文字
4. 忽略所有的纯图形内容（比如：logo，地图等，包括页面上的水印）
5. 忽略所有的页眉和页脚，但保留原文中每页的页码（如果原文中有），严格按照原文中标注的页码来提取（不论原文是否有错）
6. 如果遇到空白页或整页都是没有意义的内容，请返回：EMPTY_PAGE

Markdown格式化要求：
1. 表格前后的空行要保留
2. 列表前后的空行要保留  
3. 标题前后的空行要保留
4. 表格的排版（特别是合并单元格）要与原文（图片）完全一致
5. 根据Markdown的语法，需要添加空格的地方，请务必添加空格；但不要在表格的单元格内填充大量的空格，需要的话填充一个空格即可
6. 如有原文有页码的话，按原文保留
7. 对于像目录这样的内容，可能会包含大量的「..........」或「-------------」这样的符号，如果只是为了表达页码的话请将其长度限制在6个点也就是「......」
8. 如果有URL信息，请保持完整的URL信息，但不要用Markdown的链接格式来处理URL，保留纯文本状态即可
9. 不要添加任何```markdown```之类的定界符

总之，要严格践行Markdown的语法要求，直接输出可用的Markdown文本。"""

    def _create_batch_jsonl(self, image_paths: List[str], batch_id: int) -> str:
        """
        创建批处理JSONL文件
        
        参数:
            image_paths: 图片路径列表
            batch_id: 批次ID
            
        返回:
            JSONL文件路径
        """
        fd, jsonl_path = tempfile.mkstemp(suffix=f"_batch_{batch_id}.jsonl")
        os.close(fd)

        combined_prompt = self._create_combined_prompt()

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for idx, image_path in enumerate(image_paths, 1):
                try:
                    with open(image_path, "rb") as img_f:
                        image_data = img_f.read()
                    base64_image = base64.b64encode(image_data).decode("utf-8")

                    # 检查单个图片大小（避免过大）
                    if len(base64_image) > 20 * 1024 * 1024:  # 20MB限制
                        logger.warning(f"图片 {image_path} 过大 ({len(base64_image)/1024/1024:.1f}MB)，可能导致API失败")

                    page_num = os.path.basename(image_path).replace("page_", "").replace(".png", "")

                    request_body = {
                        "model":
                        self.model_name,
                        "messages": [{
                            "role":
                            "user",
                            "content": [{
                                "type": "text",
                                "text": combined_prompt
                            }, {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }]
                        }],
                        "max_tokens":
                        4000
                    }

                    line = {"custom_id": f"batch_{batch_id}_page_{page_num}", "method": "POST", "url": "/v1/chat/completions", "body": request_body}

                    f.write(json.dumps(line, ensure_ascii=False) + "\n")

                except Exception as e:
                    logger.error(f"处理图片 {image_path} 失败: {e}")
                    continue

        # 检查文件大小
        file_size_mb = os.path.getsize(jsonl_path) / (1024 * 1024)
        logger.info(f"批次 {batch_id} JSONL文件大小: {file_size_mb:.1f}MB")

        if file_size_mb > self.max_file_size_mb:
            logger.warning(f"批次 {batch_id} 文件大小超限 ({file_size_mb:.1f}MB > {self.max_file_size_mb}MB)")

        return jsonl_path

    def submit_batch_ocr(self, image_paths: List[str], task_id: str) -> List[str]:
        """
        提交批量OCR处理
        
        参数:
            image_paths: 图片路径列表
            task_id: 任务ID
            
        返回:
            批次ID列表
        """
        try:
            # 计算最优批次分配
            total_pages = len(image_paths)
            batch_ranges = self._calculate_optimal_batches(total_pages)
            batch_ids = []

            for batch_idx, (start_page, end_page) in enumerate(batch_ranges, 1):
                # 获取当前批次的图片路径
                batch_image_paths = image_paths[start_page - 1:end_page]

                logger.info(f"准备批次 {batch_idx}: 第 {start_page}-{end_page} 页 ({len(batch_image_paths)} 张图片)")

                # 创建JSONL文件
                jsonl_path = self._create_batch_jsonl(batch_image_paths, batch_idx)

                try:
                    # 上传文件
                    with open(jsonl_path, "rb") as f:
                        input_file = self.client.files.create(purpose="batch", file=f)

                    # 创建批处理作业
                    batch = self.client.batches.create(input_file_id=input_file.id,
                                                       endpoint="/v1/chat/completions",
                                                       completion_window="24h",
                                                       metadata={
                                                           "task_id": task_id,
                                                           "batch_index": str(batch_idx),
                                                           "start_page": str(start_page),
                                                           "end_page": str(end_page)
                                                       })

                    batch_ids.append(batch.id)
                    logger.info(f"批次 {batch_idx} 已提交: {batch.id} (页面 {start_page}-{end_page})")

                    # 保存批次信息到数据库
                    self._save_batch_info(task_id, batch.id, batch_idx, start_page, end_page, input_file.id)

                finally:
                    # 清理临时文件
                    try:
                        os.unlink(jsonl_path)
                    except OSError:
                        pass

            logger.info(f"任务 {task_id} 所有批次已提交完成，共 {len(batch_ids)} 个批次")
            return batch_ids

        except Exception as e:
            logger.error(f"提交批量OCR失败: {e}")
            raise

    def _save_batch_info(self, task_id: str, batch_id: str, batch_index: int, start_page: int, end_page: int, input_file_id: str):
        """保存批次信息到数据库"""
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
                "status": "submitted",
                "created_at": time.time(),
                "updated_at": time.time()
            }

            db.ocr_batches.insert_one(batch_info)
            logger.info(f"批次信息已保存: {batch_id}")

        except Exception as e:
            logger.error(f"保存批次信息失败: {e}")

    def check_batch_status(self, task_id: str) -> Dict[str, any]:
        """
        检查任务的所有批次状态
        
        参数:
            task_id: 任务ID
            
        返回:
            状态信息字典
        """
        try:
            db = get_db()
            if db is None:
                return {"error": "无法连接到数据库"}

            # 获取任务的所有批次
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
                    # 查询OpenAI API获取最新状态
                    batch = self.client.batches.retrieve(batch_id)
                    status = batch.status

                    # 更新数据库中的状态
                    db.ocr_batches.update_one({"batch_id": batch_id}, {"$set": {"status": status, "updated_at": time.time()}})

                    batch_status = {
                        "batch_id": batch_id,
                        "batch_index": batch_info["batch_index"],
                        "start_page": batch_info["start_page"],
                        "end_page": batch_info["end_page"],
                        "status": status
                    }

                    if status == "completed":
                        completed_batches += 1
                        # 如果有输出文件，记录文件ID
                        if hasattr(batch, 'output_file_id') and batch.output_file_id:
                            batch_status["output_file_id"] = batch.output_file_id
                    elif status in ["failed", "cancelled", "expired"]:
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
                        "error": str(e)
                    })
                    failed_batches += 1

            return {
                "total_batches": total_batches,
                "completed_batches": completed_batches,
                "failed_batches": failed_batches,
                "processing_batches": processing_batches,
                "all_completed": completed_batches == total_batches,
                "batch_statuses": batch_statuses
            }

        except Exception as e:
            logger.error(f"检查批次状态失败: {e}")
            return {"error": str(e)}

    def retrieve_batch_results(self, task_id: str, fallback_ocr_tool=None) -> Dict[str, str]:
        """
        获取所有批次的结果并合并
        
        参数:
            task_id: 任务ID
            fallback_ocr_tool: 失败时的备用OCR工具
            
        返回:
            页面结果字典 {页码: markdown内容}
        """
        try:
            db = get_db()
            if db is None:
                raise ValueError("无法连接到数据库")

            # 获取任务的所有已完成批次
            completed_batches = list(db.ocr_batches.find({"task_id": task_id, "status": "completed"}).sort("batch_index", 1))

            page_results = {}
            failed_pages = []

            for batch_info in completed_batches:
                batch_id = batch_info["batch_id"]
                start_page = batch_info["start_page"]
                end_page = batch_info["end_page"]

                logger.info(f"处理批次 {batch_info['batch_index']} 结果: {batch_id} (页面 {start_page}-{end_page})")

                try:
                    # 获取批次详情
                    batch = self.client.batches.retrieve(batch_id)

                    if not hasattr(batch, 'output_file_id') or not batch.output_file_id:
                        logger.error(f"批次 {batch_id} 没有输出文件")
                        failed_pages.extend(range(start_page, end_page + 1))
                        continue

                    # 下载结果文件
                    content = self.client.files.content(batch.output_file_id).text

                    # 解析结果
                    for line in content.strip().split('\n'):
                        if not line.strip():
                            continue

                        try:
                            result_obj = json.loads(line)
                            custom_id = result_obj.get("custom_id", "")

                            # 解析页码
                            if not custom_id.startswith(f"batch_{batch_info['batch_index']}_page_"):
                                continue

                            page_num_str = custom_id.replace(f"batch_{batch_info['batch_index']}_page_", "")

                            try:
                                page_num = int(page_num_str)
                            except ValueError:
                                # 处理可能的格式如 "001"
                                page_num = int(page_num_str.lstrip('0') or '0')

                            # 检查是否有错误
                            if "error" in result_obj and result_obj["error"]:
                                logger.error(f"页面 {page_num} 处理失败: {result_obj['error']}")
                                failed_pages.append(page_num)
                                continue

                            # 提取文本内容
                            response = result_obj.get("response", {})

                            if "choices" in response and response["choices"]:
                                content = response["choices"][0].get("message", {}).get("content", "")
                            else:
                                logger.error(f"页面 {page_num} 响应格式异常")
                                failed_pages.append(page_num)
                                continue

                            if content.strip():
                                # 清理可能的markdown定界符
                                content = content.replace("```markdown", "").replace("```", "")
                                page_results[str(page_num).zfill(3)] = content.strip()
                                logger.info(f"页面 {page_num} 处理成功")
                            else:
                                logger.warning(f"页面 {page_num} 内容为空")
                                failed_pages.append(page_num)

                        except json.JSONDecodeError as e:
                            logger.error(f"解析结果行失败: {e}")
                            continue
                        except Exception as e:
                            logger.error(f"处理结果行失败: {e}")
                            continue

                except Exception as e:
                    logger.error(f"处理批次 {batch_id} 结果失败: {e}")
                    failed_pages.extend(range(start_page, end_page + 1))

            # 处理失败页面
            if failed_pages and fallback_ocr_tool:
                logger.info(f"使用普通模式处理 {len(failed_pages)} 个失败页面")
                self._process_failed_pages(failed_pages, page_results, task_id, fallback_ocr_tool)

            return page_results

        except Exception as e:
            logger.error(f"获取批次结果失败: {e}")
            raise

    def _process_failed_pages(self, failed_pages: List[int], page_results: Dict[str, str], task_id: str, fallback_ocr_tool):
        """使用普通OCR工具处理失败的页面"""
        try:
            # 需要从fallback_ocr_tool获取task_dir路径
            # 这里假设fallback_ocr_tool有config属性
            if hasattr(fallback_ocr_tool, 'config'):
                task_dir = Path(fallback_ocr_tool.config.temp_dir) / f"task_{task_id}" / "images"
            else:
                # 如果没有config，尝试从环境变量获取
                temp_dir = os.getenv("PDF_PROCESSOR_TEMP_DIR", "temp/pdf_processing")
                task_dir = Path(temp_dir) / f"task_{task_id}" / "images"

            for page_num in failed_pages:
                image_path = task_dir / f"page_{page_num:03d}.png"

                if not image_path.exists():
                    logger.error(f"页面 {page_num} 图片文件不存在: {image_path}")
                    continue

                try:
                    logger.info(f"使用普通模式处理失败页面 {page_num}")
                    md_content = fallback_ocr_tool.img2md(str(image_path))

                    if md_content and md_content.strip() != "EMPTY_PAGE":
                        page_results[str(page_num).zfill(3)] = md_content
                        logger.info(f"失败页面 {page_num} 补救成功")
                    else:
                        logger.warning(f"失败页面 {page_num} 补救后仍为空")

                except Exception as e:
                    logger.error(f"处理失败页面 {page_num} 时出错: {e}")
                    continue

        except Exception as e:
            logger.error(f"处理失败页面时出错: {e}")

    def cleanup_batch_data(self, task_id: str):
        """清理批次相关数据"""
        try:
            db = get_db()
            if db is None:
                return

            # 删除批次记录
            result = db.ocr_batches.delete_many({"task_id": task_id})
            logger.info(f"已清理任务 {task_id} 的 {result.deleted_count} 条批次记录")

        except Exception as e:
            logger.error(f"清理批次数据失败: {e}")
