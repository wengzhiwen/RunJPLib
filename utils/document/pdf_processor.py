"""
PDF处理器 - 大学招生信息处理器的核心类
基于Buffalo工作流程管理器来处理PDF文件
"""

from datetime import datetime
from datetime import time as datetime_time
from pathlib import Path
import json
import re
import shutil
import time
import uuid
from typing import Optional

from bson.objectid import ObjectId
from buffalo import Buffalo
from buffalo import Project
from buffalo import Work
from gridfs import GridFS
from pdf2image import convert_from_path

from ..ai.analysis_tool import DocumentAnalyzer
from ..ai.batch_ocr_tool import BatchOcrProcessor
from ..ai.ocr_tool import ImageOcrProcessor
from ..ai.translate_tool import DocumentTranslator
from ..core.config import Config
from ..core.database import get_db
from ..core.database import get_mongo_client
from ..core.logging import setup_task_logger
from ..core.proof import save_proof_bundle

task_logger = setup_task_logger("TaskManager")

_MARKDOWN_LINK_PATTERN = re.compile(r'(!?\[[^\]]*\]\()([^)]+)(\))')
_ASSET_IMAGE_PATTERN = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_ASSET_OCR_FALLBACK = "画像：正確に認識できなかった画像"


class PDFProcessor:
    """PDF处理器主类"""

    def __init__(
        self,
        task_id: str,
        university_name: str,
        pdf_file_path: str,
        original_md_path: str = None,
        reference_md_path: str = None,
        restart_from_step: str = None,
        processing_mode: str = "normal",
        task_manager_instance=None,
    ):
        """
        初始化PDF处理器

        参数:
            task_id: 任务ID
            university_name: 大学名称
            pdf_file_path: PDF文件路径
            restart_from_step: 从哪个步骤开始重启（可选）
            processing_mode: 处理模式 ("normal" | "batch")
            task_manager_instance: TaskManager的实例，用于回调
        """
        self.task_id = task_id
        self.university_name = university_name
        self.pdf_file_path = pdf_file_path
        self.original_md_path = original_md_path
        self.reference_md_path = reference_md_path
        self.restart_from_step = restart_from_step
        self.processing_mode = processing_mode
        self.config = Config()
        self.task_manager_instance = task_manager_instance

        # 创建任务专用的工作目录
        self.task_dir = self.config.temp_dir / f"task_{task_id}"
        self.task_dir.mkdir(exist_ok=True)

        # 初始化各种工具
        self.ocr_tool = None
        self.batch_ocr_tool = None
        self.translate_tool = None
        self.analysis_tool = None

        # 如果提供了外部OCR结果，预先加载到任务目录
        self._prepare_original_md()

    def _prepare_original_md(self):
        """如果提供外部OCR结果，将其写入任务目录"""
        if not self.original_md_path:
            return

        try:
            source_path = Path(self.original_md_path)
            if not source_path.exists():
                self._log_message(f"External OCR markdown not found: {source_path}", "ERROR")
                return

            target_path = self.task_dir / "original.md"
            content = source_path.read_text(encoding="utf-8")
            normalized_content = self._normalize_markdown_asset_links(content)
            target_path.write_text(normalized_content, encoding="utf-8")

            if not hasattr(self, "step_data"):
                self.step_data = {}
            self.step_data["original_md_path"] = str(target_path)
            self.step_data["original_md_content"] = normalized_content

            if normalized_content != content:
                self._log_message("Rewrote absolute asset links to relative paths in original.md.")

            self._log_message("Loaded external OCR markdown into task workspace.")
        except Exception as e:
            self._log_message(f"Failed to load external OCR markdown: {e}", "ERROR")

    @staticmethod
    def _normalize_markdown_asset_links(content: str) -> str:
        """将 markdown 中指向 assets 的绝对路径改为相对路径。"""

        def rewrite_target(target: str) -> str:
            lowered = target.lower()
            if lowered.startswith(("http://", "https://", "data:", "mailto:")):
                return target

            is_absolute = target.startswith("/") or re.match(r"^[a-zA-Z]:[\\/]", target)
            if not is_absolute:
                return target

            idx_forward = target.rfind("/assets/")
            idx_backward = target.rfind("\\assets\\")
            idx = max(idx_forward, idx_backward)
            if idx == -1:
                return target

            suffix = target[idx:]
            return suffix.replace("\\", "/")

        def normalize_target(target: str) -> str:
            stripped = target.strip()
            if stripped.startswith("<") and stripped.endswith(">"):
                inner = stripped[1:-1]
                rewritten = rewrite_target(inner)
                if rewritten == inner:
                    return target
                return f"<{rewritten}>"

            parts = stripped.split()
            if len(parts) == 1:
                dest = stripped
                tail = ""
            else:
                dest = parts[0]
                tail = stripped[len(parts[0]):]

            rewritten = rewrite_target(dest)
            if rewritten == dest:
                return target
            return rewritten + tail

        def replacer(match: re.Match[str]) -> str:
            prefix, target, suffix = match.groups()
            return f"{prefix}{normalize_target(target)}{suffix}"

        return _MARKDOWN_LINK_PATTERN.sub(replacer, content)

    def _update_task_status(
        self,
        status: str,
        current_step: str = "",
        progress: int = 0,
        error_message: str = "",
        logs: list = None,
    ):
        """更新任务状态到数据库"""
        try:
            client = get_mongo_client()
            if client is None:
                task_logger.error(f"[{self.task_id}] Cannot connect to DB to update status.")
                return

            db = client.RunJPLib
            update_data = {
                "status": status,
                "current_step": current_step,
                "progress": progress,
                "updated_at": datetime.utcnow(),
            }

            if error_message:
                update_data["error_message"] = error_message

            if logs:
                update_data["$push"] = {"logs": {"$each": logs}}

            db.processing_tasks.update_one(
                {"_id": ObjectId(self.task_id)},
                ({
                    "$set": update_data
                } if not logs else {
                    "$set": {
                        k: v
                        for k, v in update_data.items() if k != "$push"
                    },
                    **update_data,
                }),
            )
            task_logger.info(f"[{self.task_id}] Task status updated: {status}, step: {current_step}")
        except Exception as e:
            task_logger.error(f"[{self.task_id}] Failed to update task status: {e}")

    def _log_message(self, message: str, level: str = "INFO"):
        """记录日志消息"""
        timestamp = datetime.utcnow()
        log_entry = {"timestamp": timestamp, "level": level, "message": message}

        # 写入任务日志
        try:
            client = get_mongo_client()
            if client is not None:
                db = client.RunJPLib
                db.processing_tasks.update_one({"_id": ObjectId(self.task_id)}, {"$push": {"logs": log_entry}})
        except Exception as e:
            task_logger.error(f"[{self.task_id}] Failed to write log to DB: {e}")

        # 同时写入系统日志
        full_message = f"[{self.task_id}] {message}"
        if level == "ERROR":
            task_logger.error(full_message)
        elif level == "WARNING":
            task_logger.warning(full_message)
        else:
            task_logger.info(full_message)

    def _load_previous_results(self):
        """从之前的文件中加载处理结果（用于重启时的数据恢复）"""
        self.previous_results = {}

        if (self.task_dir / "original.md").exists():
            with open(self.task_dir / "original.md", "r", encoding="utf-8") as f:
                self.previous_results["original_md_content"] = f.read()

        if (self.task_dir / "translated.md").exists():
            with open(self.task_dir / "translated.md", "r", encoding="utf-8") as f:
                self.previous_results["translated_md_content"] = f.read()

        if (self.task_dir / "report.md").exists():
            with open(self.task_dir / "report.md", "r", encoding="utf-8") as f:
                self.previous_results["report_md_content"] = f.read()

        if self.previous_results:
            self._log_message(f"Loaded {len(self.previous_results)} previous results for restart.")

    def process_step_01_pdf2img(self, work: Work) -> bool:
        """步骤1: PDF转图片"""
        try:
            self._log_message("Starting PDF to image conversion...")
            self._update_task_status("processing", "01_pdf2img", 10)

            pdf_path = Path(self.pdf_file_path)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            # 创建图片输出目录
            images_dir = self.task_dir / "images"
            images_dir.mkdir(exist_ok=True)

            # 转换PDF为图片
            self._log_message(f"Converting PDF file: {pdf_path}")
            images = convert_from_path(str(pdf_path), dpi=self.config.ocr_dpi)

            image_paths = []
            for i, image in enumerate(images, 1):
                image_path = images_dir / f"page_{i:03d}.png"
                image.save(str(image_path), "PNG")
                image_paths.append(str(image_path))
                self._log_message(f"Saved page {i}: {image_path.name}")

            # 保存图片路径列表到实例数据
            if not hasattr(self, "step_data"):
                self.step_data = {}
            self.step_data["image_paths"] = image_paths
            self.step_data["total_pages"] = len(image_paths)

            self._log_message(f"PDF to image conversion complete. Total pages: {len(image_paths)}")
            return True

        except Exception as e:
            error_msg = f"PDF to image conversion failed: {str(e)}"
            self._log_message(error_msg, "ERROR")
            return False

    def process_step_02_ocr(self, work: Work) -> bool:
        """步骤2: OCR识别"""
        if self.original_md_path:
            return self._process_asset_ocr()

        if self.processing_mode == "batch":
            ocr_success = self._process_batch_ocr()
        else:
            ocr_success = self._process_normal_ocr()

        if not ocr_success:
            return False

        if self.reference_md_path:
            return self._refine_ocr_with_reference()

        return True

    def _process_normal_ocr(self) -> bool:
        """普通OCR处理模式"""
        try:
            self._log_message("Starting OCR (normal mode)...")
            self._update_task_status("processing", "02_ocr", 30)

            # 初始化OCR工具
            if not self.ocr_tool:
                self.ocr_tool = ImageOcrProcessor()

            # 获取图片路径
            image_paths = self._get_image_paths()
            if not image_paths:
                raise ValueError("No image files found for OCR")

            # 创建OCR输出目录
            ocr_dir = self.task_dir / "ocr"
            ocr_dir.mkdir(exist_ok=True)

            markdown_contents = []
            for i, image_path in enumerate(image_paths, 1):
                self._log_message(f"OCR processing page {i}/{len(image_paths)}...")

                try:
                    md_content = self.ocr_tool.img2md(image_path)
                    if md_content and md_content.strip() != "EMPTY_PAGE":
                        markdown_contents.append(md_content)

                        # 保存单页OCR结果
                        page_md_file = ocr_dir / f"page_{i:03d}.md"
                        with open(page_md_file, "w", encoding="utf-8") as f:
                            f.write(md_content)

                        self._log_message(f"Page {i} OCR completed.")
                    else:
                        self._log_message(f"Page {i} is blank, skipping.")

                except Exception as e:
                    self._log_message(f"Page {i} OCR failed: {str(e)}", "WARNING")
                    continue

            if not markdown_contents:
                raise ValueError("All pages failed OCR processing")

            # 合并所有OCR结果
            combined_markdown = "\n\n".join(markdown_contents)
            self._save_ocr_results(combined_markdown)

            self._log_message(f"OCR (normal mode) complete. Processed {len(markdown_contents)} non-blank pages.")
            return True

        except Exception as e:
            error_msg = f"OCR failed: {str(e)}"
            self._log_message(error_msg, "ERROR")
            return False

    def _process_batch_ocr(self) -> bool:
        """批量OCR处理模式"""
        try:
            self._log_message("Starting OCR (batch mode)...")
            self._update_task_status("processing", "02_ocr", 30)

            # 初始化批量OCR工具
            if not self.batch_ocr_tool:
                self.batch_ocr_tool = BatchOcrProcessor()
            if not self.ocr_tool:
                self.ocr_tool = ImageOcrProcessor()

            # 获取图片路径
            image_paths = self._get_image_paths()
            if not image_paths:
                raise ValueError("No image files found for batch OCR")

            # 保存图片路径列表到实例数据（确保数据一致性）
            if not hasattr(self, "step_data"):
                self.step_data = {}
            self.step_data["image_paths"] = image_paths
            self.step_data["total_pages"] = len(image_paths)

            # 检查是否已有批次在处理中
            batch_status = self.batch_ocr_tool.check_batch_status(self.task_id)

            if "error" not in batch_status and batch_status.get("total_batches", 0) > 0:
                # 已有批次，检查状态
                self._log_message(f"Found existing batch submission. Total batches: {batch_status['total_batches']}")
                if not batch_status.get("all_completed", False):
                    # 还没完成，继续等待
                    self._log_message("Batch not yet complete, entering wait loop...")
                    self._update_task_status("processing", "02_ocr_batch_waiting", 35)
                    return self._wait_for_batch_completion()
                else:
                    # 已完成，获取结果
                    self._log_message("Batch already complete, retrieving results...")
                    return self._retrieve_and_save_batch_results()
            else:
                # 没有批次，提交新的批次
                self._log_message(f"Submitting new batch OCR job for {len(image_paths)} pages.")
                try:
                    batch_ids = self.batch_ocr_tool.submit_batch_ocr(image_paths, self.task_id)
                    self._log_message(f"Submitted {len(batch_ids)} batches: {batch_ids}")
                    self._update_task_status("processing", "02_ocr_batch_submitted", 32)

                    # 开始等待完成
                    return self._wait_for_batch_completion()

                except Exception as e:
                    self._log_message(f"Batch OCR submission failed, falling back to normal mode: {e}", "WARNING")
                    return self._process_normal_ocr()

        except Exception as e:
            error_msg = f"Batch OCR processing failed: {str(e)}"
            self._log_message(error_msg, "ERROR")
            # 回退到普通模式
            self._log_message("Falling back to normal OCR mode.", "WARNING")
            return self._process_normal_ocr()

    def _wait_for_batch_completion(self) -> bool:
        """等待批次完成"""
        max_wait_time = 24 * 60 * 60  # 最大等待24小时
        check_interval = 5 * 60  # 每5分钟检查一次
        start_time = time.time()

        # 首次进入等待时，通知 TaskManager 可以启动下一个任务
        if self.task_manager_instance:
            self.task_manager_instance.notify_task_is_waiting(self.task_id)

        while time.time() - start_time < max_wait_time:
            batch_status = self.batch_ocr_tool.check_batch_status(self.task_id)

            if "error" in batch_status:
                self._log_message(f"Failed to check batch status: {batch_status['error']}", "ERROR")
                return False

            completed = batch_status.get("completed_batches", 0)
            total = batch_status.get("total_batches", 0)
            failed = batch_status.get("failed_batches", 0)
            processing = batch_status.get("processing_batches", 0)

            self._log_message(f"Batch status: {completed}/{total} complete, {failed} failed, {processing} in progress.")

            if batch_status.get("all_completed", False):
                self._log_message("All batches completed!")
                return self._retrieve_and_save_batch_results()

            # 更新进度
            if total > 0:
                progress = 30 + int((completed / total) * 10)  # 30-40%的进度
                self._update_task_status("processing", "02_ocr_batch_waiting", progress)

            # 等待下次检查
            self._log_message(f"Waiting for {check_interval//60} minutes before next check...")
            time.sleep(check_interval)

        # 超时
        self._log_message("Batch processing timed out, falling back to normal mode.", "WARNING")
        return self._process_normal_ocr()

    def _retrieve_and_save_batch_results(self) -> bool:
        """获取并保存批次结果"""
        try:
            self._log_message("Retrieving batch OCR results...")
            page_results = self.batch_ocr_tool.retrieve_batch_results(self.task_id, self.ocr_tool)

            if not page_results:
                raise ValueError("Batch processing returned no results")

            # 创建OCR输出目录
            ocr_dir = self.task_dir / "ocr"
            ocr_dir.mkdir(exist_ok=True)

            # 保存单页结果并收集有效内容
            markdown_contents = []
            for page_key in sorted(page_results.keys()):
                md_content = page_results[page_key]
                if md_content and md_content.strip() != "EMPTY_PAGE":
                    markdown_contents.append(md_content)

                    # 保存单页OCR结果
                    page_md_file = ocr_dir / f"page_{page_key}.md"
                    with open(page_md_file, "w", encoding="utf-8") as f:
                        f.write(md_content)

            if not markdown_contents:
                raise ValueError("All pages failed batch OCR processing")

            # 合并所有OCR结果
            combined_markdown = "\n\n".join(markdown_contents)
            self._save_ocr_results(combined_markdown)

            # 清理批次数据
            self.batch_ocr_tool.cleanup_batch_data(self.task_id)

            self._log_message(f"Batch OCR complete. Processed {len(markdown_contents)} non-blank pages.")
            return True

        except Exception as e:
            error_msg = f"Failed to retrieve batch results: {str(e)}"
            self._log_message(error_msg, "ERROR")
            return False

    def _get_image_paths(self) -> list:
        """获取图片路径列表"""
        if hasattr(self, "step_data") and "image_paths" in self.step_data:
            return self.step_data["image_paths"]
        elif (hasattr(self, "previous_results") and "image_paths" in self.previous_results):
            return self.previous_results["image_paths"]
        else:
            # 尝试从文件系统加载
            images_dir = self.task_dir / "images"
            if images_dir.exists():
                return sorted([str(p) for p in images_dir.glob("page_*.png")])
            else:
                return []

    def _save_ocr_results(self, combined_markdown: str):
        """保存OCR结果"""
        # 保存合并结果
        combined_md_file = self.task_dir / "original.md"
        with open(combined_md_file, "w", encoding="utf-8") as f:
            f.write(combined_markdown)

        # 保存OCR结果到实例数据
        if not hasattr(self, "step_data"):
            self.step_data = {}
        self.step_data["original_md_path"] = str(combined_md_file)
        self.step_data["original_md_content"] = combined_markdown

    def _get_original_md_content(self) -> str:
        if hasattr(self, "step_data") and "original_md_content" in self.step_data:
            return self.step_data["original_md_content"]
        if hasattr(self, "previous_results") and "original_md_content" in self.previous_results:
            return self.previous_results["original_md_content"]
        original_md_file = self.task_dir / "original.md"
        if original_md_file.exists():
            return original_md_file.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _extract_markdown_link_target(raw_target: str) -> str:
        target = raw_target.strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        if " " in target:
            target = target.split(" ", 1)[0]
        return target

    def _extract_asset_image_refs(self, content: str) -> list:
        matches = []
        for match in _ASSET_IMAGE_PATTERN.finditer(content):
            raw_target = match.group(1)
            target = self._extract_markdown_link_target(raw_target).replace("\\", "/")
            target_lower = target.lower()
            if target_lower.startswith(("http://", "https://", "data:", "mailto:")):
                continue
            if "/assets/" not in target_lower and not target_lower.startswith("assets/"):
                continue
            if Path(target_lower).suffix not in _ASSET_EXTENSIONS:
                continue
            matches.append({
                "start": match.start(),
                "end": match.end(),
                "target": target,
                "raw_target": raw_target,
            })
        return matches

    def _resolve_asset_path(self, base_dir: Path, target: str) -> Optional[Path]:
        normalized = target.replace("\\", "/")
        if normalized.startswith("/"):
            idx = normalized.lower().rfind("/assets/")
            if idx != -1:
                normalized = normalized[idx + 1:]
        rel = Path(normalized)
        candidate = (base_dir / rel).resolve()
        try:
            base_resolved = base_dir.resolve()
        except FileNotFoundError:
            base_resolved = base_dir
        if base_resolved not in candidate.parents and candidate != base_resolved:
            return None
        if "assets" not in [part.lower() for part in candidate.parts]:
            return None
        if not candidate.exists():
            return None
        if candidate.suffix.lower() not in _ASSET_EXTENSIONS:
            return None
        return candidate

    def _save_asset_manifest(self, manifest: list) -> None:
        manifest_path = self.task_dir / "asset_ocr_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _merge_asset_ocr_results(self, content: str, asset_entries: list, ocr_results: dict) -> str:
        replacements = []
        for entry in asset_entries:
            page_num = entry.get("page_num")
            text = None
            if page_num is not None:
                text = ocr_results.get(str(page_num).zfill(3))
                if text:
                    text = text.strip()
            if not text or text == "EMPTY_PAGE":
                text = _ASSET_OCR_FALLBACK
            replacements.append((entry["start"], entry["end"], text))

        updated = content
        for start, end, replacement in sorted(replacements, key=lambda item: item[0], reverse=True):
            updated = updated[:start] + replacement + updated[end:]
        return updated

    def _process_asset_ocr(self) -> bool:
        """针对assets图片进行批量OCR并合并回原文"""
        try:
            self._log_message("Starting OCR for asset images (batch mode)...")
            self._update_task_status("processing", "02_ocr", 30)

            if not self.batch_ocr_tool:
                self.batch_ocr_tool = BatchOcrProcessor()
            if not self.ocr_tool:
                self.ocr_tool = ImageOcrProcessor()

            content = self._get_original_md_content()
            if not content:
                self._log_message("No original markdown content found for asset OCR.", "WARNING")
                return True

            asset_entries = self._extract_asset_image_refs(content)
            if not asset_entries:
                self._log_message("No asset image references found in markdown. Skipping asset OCR.")
                return True

            base_dir = Path(self.original_md_path).parent if self.original_md_path else self.task_dir
            path_to_page = {}
            page_numbers = []
            image_paths = []
            next_page_num = 1

            for entry in asset_entries:
                asset_path = self._resolve_asset_path(base_dir, entry["target"])
                entry["asset_path"] = str(asset_path) if asset_path else None
                if not asset_path:
                    entry["page_num"] = None
                    continue
                key = str(asset_path)
                if key in path_to_page:
                    entry["page_num"] = path_to_page[key]
                    continue
                entry["page_num"] = next_page_num
                path_to_page[key] = next_page_num
                image_paths.append(str(asset_path))
                page_numbers.append(next_page_num)
                next_page_num += 1

            self._save_asset_manifest(asset_entries)

            if not image_paths:
                updated_content = self._merge_asset_ocr_results(content, asset_entries, {})
                self._save_ocr_results(updated_content)
                self._log_message("All asset images missing; replaced with fallback text.")
                return True

            batch_status = self.batch_ocr_tool.check_batch_status(self.task_id)
            if "error" not in batch_status and batch_status.get("total_batches", 0) > 0:
                self._log_message(f"Found existing asset OCR batches: {batch_status['total_batches']}")
                if not batch_status.get("all_completed", False):
                    return self._wait_for_asset_batch_completion(content, asset_entries)
                return self._retrieve_and_merge_asset_results(content, asset_entries)

            self._log_message(f"Submitting asset OCR batch for {len(image_paths)} images.")
            prompt = self.batch_ocr_tool._create_asset_prompt()
            self.batch_ocr_tool.submit_batch_ocr(image_paths, self.task_id, prompt=prompt, page_numbers=page_numbers)
            return self._wait_for_asset_batch_completion(content, asset_entries)

        except Exception as e:
            self._log_message(f"Asset OCR failed: {e}", "WARNING")
            content = self._get_original_md_content()
            if content:
                asset_entries = self._extract_asset_image_refs(content)
                if asset_entries:
                    updated_content = self._merge_asset_ocr_results(content, asset_entries, {})
                    self._save_ocr_results(updated_content)
            return True

    def _wait_for_asset_batch_completion(self, content: str, asset_entries: list) -> bool:
        max_wait_time = 24 * 60 * 60
        check_interval = 5 * 60
        start_time = time.time()

        if self.task_manager_instance:
            self.task_manager_instance.notify_task_is_waiting(self.task_id)

        while time.time() - start_time < max_wait_time:
            batch_status = self.batch_ocr_tool.check_batch_status(self.task_id)
            if "error" in batch_status:
                self._log_message(f"Failed to check asset OCR batch status: {batch_status['error']}", "WARNING")
                break

            completed = batch_status.get("completed_batches", 0)
            total = batch_status.get("total_batches", 0)
            failed = batch_status.get("failed_batches", 0)
            processing = batch_status.get("processing_batches", 0)

            self._log_message(f"Asset batch status: {completed}/{total} complete, {failed} failed, {processing} in progress.")

            if batch_status.get("all_completed", False):
                return self._retrieve_and_merge_asset_results(content, asset_entries)

            if total > 0:
                progress = 30 + int((completed / total) * 10)
                self._update_task_status("processing", "02_ocr_batch_waiting", progress)

            self._log_message(f"Waiting for {check_interval//60} minutes before next check...")
            time.sleep(check_interval)

        self._log_message("Asset OCR batch timed out. Replacing with fallback text.", "WARNING")
        updated_content = self._merge_asset_ocr_results(content, asset_entries, {})
        self._save_ocr_results(updated_content)
        return True

    def _retrieve_and_merge_asset_results(self, content: str, asset_entries: list) -> bool:
        try:
            self._log_message("Retrieving asset OCR batch results...")
            page_results = self.batch_ocr_tool.retrieve_batch_results(self.task_id, fallback_ocr_tool=None)
            updated_content = self._merge_asset_ocr_results(content, asset_entries, page_results)
            self._save_ocr_results(updated_content)
            self.batch_ocr_tool.cleanup_batch_data(self.task_id)
            self._log_message("Asset OCR merge complete.")
            return True
        except Exception as e:
            self._log_message(f"Failed to retrieve asset OCR results: {e}", "WARNING")
            updated_content = self._merge_asset_ocr_results(content, asset_entries, {})
            self._save_ocr_results(updated_content)
            return True

    def _refine_ocr_with_reference(self) -> bool:
        """使用外部Markdown对OCR结果进行校对补强。"""
        try:
            primary_md = self._get_original_md_content()
            if not primary_md:
                self._log_message("No OCR markdown found for refinement.", "WARNING")
                return True

            reference_path = Path(self.reference_md_path)
            if not reference_path.exists():
                self._log_message(f"Reference markdown not found: {reference_path}", "WARNING")
                return True

            reference_md = reference_path.read_text(encoding="utf-8")
            if not reference_md.strip():
                self._log_message("Reference markdown is empty. Skipping refinement.")
                return True

            if not self.analysis_tool:
                self.analysis_tool = DocumentAnalyzer(
                    self.config.analysis_questions,
                    self.config.translate_terms,
                )

            refine_start = time.time()
            self._log_message("Refine OCR markdown with reference started.")
            refined_md = self.analysis_tool.refine_markdown_with_reference(primary_md, reference_md)
            refine_cost = time.time() - refine_start
            self._log_message(f"Refine OCR markdown completed in {refine_cost:.2f}s.")
            if refined_md and refined_md.strip():
                try:
                    save_proof_bundle(self.university_name, primary_md, reference_md, refined_md)
                    self._log_message("Saved proof bundle for OCR refinement.")
                except Exception as save_error:
                    self._log_message(f"Failed to save proof bundle: {save_error}", "WARNING")

                combined_md_file = self.task_dir / "original.md"
                combined_md_file.write_text(refined_md, encoding="utf-8")
                if not hasattr(self, "step_data"):
                    self.step_data = {}
                self.step_data["original_md_path"] = str(combined_md_file)
                self.step_data["original_md_content"] = refined_md
                self._log_message("OCR markdown refined with reference markdown.")
            else:
                self._log_message("Refined markdown is empty, keeping original OCR result.", "WARNING")

            return True
        except Exception as e:
            self._log_message(f"Refine OCR with reference failed: {e}", "WARNING")
            return True

    def process_step_03_translate(self, work: Work) -> bool:
        """步骤3: 翻译"""
        try:
            self._log_message("Starting translation...")
            self._update_task_status("processing", "03_translate", 50)

            # 初始化翻译工具
            if not self.translate_tool:
                self.translate_tool = DocumentTranslator(self.config.translate_terms)

            # 获取OCR结果内容
            if hasattr(self, "step_data") and "original_md_content" in self.step_data:
                original_md_content = self.step_data["original_md_content"]
            elif (hasattr(self, "previous_results") and "original_md_content" in self.previous_results):
                original_md_content = self.previous_results["original_md_content"]
            else:
                # 尝试从文件加载
                original_md_file = self.task_dir / "original.md"
                if original_md_file.exists():
                    with open(original_md_file, "r", encoding="utf-8") as f:
                        original_md_content = f.read()
                else:
                    original_md_content = ""

            if not original_md_content:
                raise ValueError("No original markdown content found for translation")

            # 执行翻译
            self._log_message("Translating Japanese content to Chinese...")
            translated_content = self.translate_tool.md2zh(original_md_content)

            # 保存翻译结果
            translated_md_file = self.task_dir / "translated.md"
            with open(translated_md_file, "w", encoding="utf-8") as f:
                f.write(translated_content)

            # 保存翻译结果到实例数据
            if not hasattr(self, "step_data"):
                self.step_data = {}
            self.step_data["translated_md_path"] = str(translated_md_file)
            self.step_data["translated_md_content"] = translated_content

            self._log_message("Translation complete.")
            return True

        except Exception as e:
            error_msg = f"Translation failed: {str(e)}"
            self._log_message(error_msg, "ERROR")
            return False

    def process_step_04_analysis(self, work: Work) -> bool:
        """步骤4: 分析"""
        try:
            self._log_message("Starting analysis...")
            self._update_task_status("processing", "04_analysis", 70)

            # 初始化分析工具
            if not self.analysis_tool:
                self.analysis_tool = DocumentAnalyzer(
                    self.config.analysis_questions,
                    self.config.translate_terms,
                )

            # 获取翻译结果内容
            if hasattr(self, "step_data") and "translated_md_content" in self.step_data:
                translated_md_content = self.step_data["translated_md_content"]
            elif (hasattr(self, "previous_results") and "translated_md_content" in self.previous_results):
                translated_md_content = self.previous_results["translated_md_content"]
            else:
                # 尝试从文件加载
                translated_md_file = self.task_dir / "translated.md"
                if translated_md_file.exists():
                    with open(translated_md_file, "r", encoding="utf-8") as f:
                        translated_md_content = f.read()
                else:
                    translated_md_content = ""

            if not translated_md_content:
                raise ValueError("No translated markdown content found for analysis")

            # 执行分析
            self._log_message("Analyzing admission information...")
            analysis_report = self.analysis_tool.md2report(translated_md_content)

            # 保存分析报告
            report_md_file = self.task_dir / "report.md"
            with open(report_md_file, "w", encoding="utf-8") as f:
                f.write(analysis_report)

            self.step_data["report_md_path"] = str(report_md_file)
            self.step_data["report_md_content"] = analysis_report

            self._log_message("Analysis complete.")
            return True

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            self._log_message(error_msg, "ERROR")
            self.step_data["error"] = error_msg
            return False

    def _extract_university_name_zh(self, analysis_report: str) -> str:
        """从分析报告中提取大学的简体中文全称"""
        try:
            # 查找"大学中文名称："或"大学中文名称:"开头的行
            lines = analysis_report.split("\n")
            for line in lines:
                line_stripped = line.strip()
                # 支持中文冒号和英文冒号两种格式
                if line_stripped.startswith("大学中文名称：") or line_stripped.startswith("大学中文名称:"):
                    # 提取冒号后的内容（支持中文冒号和英文冒号）
                    if "：" in line_stripped:
                        university_name_zh = line_stripped.split("：", 1)[1].strip()
                    else:
                        university_name_zh = line_stripped.split(":", 1)[1].strip()

                    if university_name_zh:
                        self._log_message(f"Extracted Chinese university name from report: {university_name_zh}")
                        return university_name_zh

            self._log_message("Could not find Chinese university name in the report.", "WARNING")
            return None
        except Exception as e:
            self._log_message(f"Error extracting Chinese university name: {e}", "ERROR")
            return None

    def process_step_05_output(self, work: Work) -> bool:
        """步骤5: 输出到MongoDB"""
        try:
            self._log_message("Starting output to database...")
            self._update_task_status("processing", "05_output", 90)

            db = get_db()
            if db is None:
                raise ValueError("Cannot connect to the database")

            # 获取所有处理结果
            original_md = self.step_data.get("original_md_content", "")
            translated_md = self.step_data.get("translated_md_content", "")
            report_md = self.step_data.get("report_md_content", "")

            # 如果当前步骤数据中没有，尝试从之前的结果获取
            if hasattr(self, "previous_results"):
                if not original_md:
                    original_md = self.previous_results.get("original_md_content", "")
                if not translated_md:
                    translated_md = self.previous_results.get("translated_md_content", "")
                if not report_md:
                    report_md = self.previous_results.get("report_md_content", "")

            if not all([original_md, translated_md, report_md]):
                raise ValueError("Processing results are incomplete")

            # 从分析报告中提取大学中文全称
            university_name_zh = self._extract_university_name_zh(report_md)
            if not university_name_zh:
                # 如果没有提取到，使用原始大学名称作为备选
                university_name_zh = self.university_name
                self._log_message(f"Using original university name as Chinese name: {university_name_zh}")

            # 将PDF文件保存到GridFS
            fs = GridFS(db)
            with open(self.pdf_file_path, "rb") as pdf_file:
                pdf_file_id = fs.put(
                    pdf_file,
                    filename=str(uuid.uuid4()),
                    metadata={
                        "university_name": self.university_name,
                        "university_name_zh": university_name_zh,
                        "deadline": datetime.combine(datetime.now().date(), datetime_time.min),
                        "upload_time": datetime.utcnow(),
                        "original_filename": f"{self.university_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        "task_id": self.task_id,
                    },
                )

            # 创建大学信息文档
            university_doc = {
                "university_name": self.university_name,
                "university_name_zh": university_name_zh,
                "deadline": datetime.combine(datetime.now().date(), datetime_time.min),
                "created_at": datetime.utcnow(),
                "is_premium": False,
                "content": {
                    "original_md": original_md,
                    "translated_md": translated_md,
                    "report_md": report_md,
                    "pdf_file_id": pdf_file_id,
                },
            }

            # 插入到数据库
            result = db.universities.insert_one(university_doc)
            university_id = result.inserted_id

            self.step_data["university_id"] = str(university_id)
            self.step_data["pdf_file_id"] = str(pdf_file_id)

            self._log_message(f"Successfully saved to database. University ID: {university_id}")
            return True

        except Exception as e:
            error_msg = f"Output to database failed: {str(e)}"
            self._log_message(error_msg, "ERROR")
            self.step_data["error"] = error_msg
            return False

    def run_processing(self) -> bool:
        """运行完整的处理流程，使用Buffalo管理工作流程"""
        try:
            self._log_message("Starting PDF processing workflow...")
            self._update_task_status("processing", "initializing", 5)

            # 初始化Buffalo工作流程
            buffalo = Buffalo(
                base_dir=self.config.temp_dir,
                template_path=self.config.buffalo_template_file,
            )

            # 创建或加载项目
            project_name = f"pdf_processing_{self.task_id}"
            project = buffalo.create_project(project_name)

            if not project:
                raise ValueError("Failed to create Buffalo project")

            self._log_message(f"Buffalo project created: {project_name}")

            # 设置处理函数映射
            function_map = {
                "01_pdf2img": self.process_step_01_pdf2img,
                "02_ocr": self.process_step_02_ocr,
                "03_translate": self.process_step_03_translate,
                "04_analysis": self.process_step_04_analysis,
                "05_output": self.process_step_05_output,
            }

            # 如果指定了重启步骤，设置之前的步骤为已完成
            if self.restart_from_step:
                self._log_message(f"Restarting task from step: {self.restart_from_step}")
                self._load_previous_results()
                self._setup_restart_from_step(buffalo, project, self.restart_from_step)

            # 使用Buffalo的工作流程执行
            success = True
            while True:
                # 获取下一个待执行的任务
                work = project.get_next_not_started_work()

                if not work:
                    # 工作流程完成
                    self._log_message("All workflow steps completed.")
                    break

                step_name = work.name
                self._log_message(f"Buffalo: Starting work step: {step_name}")

                # 更新任务状态
                progress = self._get_progress_for_step(step_name)
                self._update_task_status("processing", step_name, progress)

                # 执行对应的处理函数
                if step_name in function_map:
                    try:
                        buffalo.update_work_status(project_name, work, "in_progress")
                        step_success = function_map[step_name](work)

                        if step_success:
                            buffalo.update_work_status(project_name, work, "done")
                            buffalo.save_project(project, project_name)
                            self._log_message(f"Step {step_name} executed successfully.")
                        else:
                            buffalo.update_work_status(project_name, work, "failed")
                            buffalo.save_project(project, project_name)
                            self._log_message(f"Step {step_name} failed.", "ERROR")
                            success = False
                            break

                    except Exception as e:
                        buffalo.update_work_status(project_name, work, "failed")
                        buffalo.save_project(project, project_name)
                        error_msg = f"Exception during step {step_name}: {str(e)}"
                        self._log_message(error_msg, "ERROR")
                        success = False
                        break
                else:
                    error_msg = f"Unknown step name: {step_name}"
                    self._log_message(error_msg, "ERROR")
                    buffalo.update_work_status(project_name, work, "failed")
                    buffalo.save_project(project, project_name)
                    success = False
                    break

            if success:
                self._log_message("PDF processing workflow completed successfully!")
                self._update_task_status("completed", "finished", 100)
                self._cleanup_temp_files()
                return True
            else:
                error_msg = "Workflow execution failed."
                self._log_message(error_msg, "ERROR")
                self._update_task_status("failed", "error", 0, error_msg)
                return False

        except Exception as e:
            error_msg = f"An unexpected error occurred during processing: {str(e)}"
            self._log_message(error_msg, "ERROR")
            self._update_task_status("failed", "error", 0, error_msg)
            return False

    def _setup_restart_from_step(self, buffalo: Buffalo, project: Project, restart_step: str):
        """设置从指定步骤重启，将之前的步骤标记为已完成"""
        project_name = project.folder_name

        for work in project.works:
            if work.name == restart_step:
                # 找到重启步骤，将之前的步骤标记为已完成
                for prev_work in project.works:
                    if prev_work.index < work.index:
                        buffalo.update_work_status(project_name, prev_work, "done")
                        self._log_message(f"Marking step {prev_work.name} as done for restart.")
                    elif prev_work.index >= work.index:
                        buffalo.update_work_status(project_name, prev_work, "not_started")
                        self._log_message(f"Resetting step {prev_work.name} to not_started for restart.")
                break

        # 保存项目状态
        buffalo.save_project(project, project_name)
        self._log_message("Restart setup complete.")

    def _get_progress_for_step(self, step_name: str) -> int:
        """根据步骤名称获取对应的进度百分比"""
        progress_map = {
            "01_pdf2img": 20,
            "02_ocr": 40,
            "03_translate": 60,
            "04_analysis": 80,
            "05_output": 100,
        }
        return progress_map.get(step_name, 0)

    def _cleanup_temp_files(self):
        """清理临时文件，增加安全校验"""
        try:
            # 安全校验：确保要删除的是当前任务的专属目录
            if self.task_dir.exists() and self.task_dir.name == f"task_{self.task_id}":
                shutil.rmtree(self.task_dir)
                self._log_message("Temporary files cleaned up successfully.")
            elif self.task_dir.exists():
                # 如果目录存在但名称与任务ID不匹配，记录严重错误并跳过删除
                error_msg = f"SAFETY HALT: Cleanup skipped. Directory name '{self.task_dir.name}' does not match task ID '{self.task_id}'."
                self._log_message(error_msg, "ERROR")
        except Exception as e:
            self._log_message(f"Failed to clean up temporary files: {str(e)}", "WARNING")


def run_pdf_processor(
    task_id: str,
    university_name: str,
    pdf_file_path: str,
    original_md_path: str = None,
    reference_md_path: str = None,
    restart_from_step: str = None,
    processing_mode: str = "normal",
    task_manager_instance=None,
) -> bool:
    """
    运行PDF处理器的入口函数

    参数:
        task_id: 任务ID
        university_name: 大学名称
        pdf_file_path: PDF文件路径
        original_md_path: 外部OCR结果Markdown路径（可选）
        reference_md_path: 参考Markdown路径（可选）
        restart_from_step: 从哪个步骤开始重启（可选）
        processing_mode: 处理模式 ("normal" | "batch")
        task_manager_instance: TaskManager的实例，用于回调

    返回:
        bool: 处理是否成功
    """
    processor = PDFProcessor(
        task_id,
        university_name,
        pdf_file_path,
        original_md_path,
        reference_md_path,
        restart_from_step,
        processing_mode,
        task_manager_instance,
    )
    return processor.run_processing()
