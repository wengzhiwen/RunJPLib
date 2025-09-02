"""
PDF处理器 - 大学招生信息处理器的核心类
基于Buffalo工作流程管理器来处理PDF文件
"""

from datetime import datetime
from datetime import time as datetime_time
import os
from pathlib import Path
import shutil
import time
import uuid

from bson.objectid import ObjectId
from buffalo import Buffalo
from buffalo import Project
from buffalo import Work
from gridfs import GridFS
from pdf2image import convert_from_path

from utils.analysis_tool import AnalysisTool
from utils.logging_config import setup_logger
from utils.mongo_client import get_db
from utils.mongo_client import get_mongo_client
from utils.ocr_tool import OCRTool
from utils.translate_tool import TranslateTool
from utils.batch_ocr_tool import BatchOCRTool

logger = setup_logger(logger_name="PDFProcessor", log_level="INFO")


class Config:
    """配置类，用于管理所有配置信息（单例模式）"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 加载环境变量配置
        from dotenv import load_dotenv

        load_dotenv()

        try:
            # 临时工作目录
            temp_dir_str = os.getenv("PDF_PROCESSOR_TEMP_DIR")
            if temp_dir_str is None:
                temp_dir_str = "temp/pdf_processing"
            self.temp_dir = Path(temp_dir_str)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ValueError(f"临时目录无法创建: {self.temp_dir}") from e

        try:
            # buffalo模板文件路径
            self.buffalo_template_file = Path(__file__).parent / "wf_template.yml"
            if not self.buffalo_template_file.exists():
                raise FileNotFoundError(f"Buffalo模板文件未找到: {self.buffalo_template_file}")
        except Exception as e:
            raise FileNotFoundError(f"Buffalo模板文件未找到: {self.buffalo_template_file}") from e

        # OCR配置
        try:
            self.ocr_dpi = int(os.getenv("OCR_DPI", 150))
        except Exception:
            self.ocr_dpi = 150

        # 优先从环境变量读取OCR模型名称
        self.ocr_model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-4o-mini")

        # 翻译配置
        try:
            translate_terms_file = os.getenv("TRANSLATE_TERMS_FILE", "")
            if translate_terms_file and Path(translate_terms_file).exists():
                with open(translate_terms_file, "r", encoding="utf-8") as f:
                    self.translate_terms = f.read()
            else:
                self.translate_terms = ""
        except Exception:
            self.translate_terms = ""

        # 优先从环境变量读取翻译模型名称
        self.translate_model_name = os.getenv("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini")

        # 优先从环境变量读取分析模型名称
        self.analysis_model_name = os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini")

        analysis_questions_file = os.getenv("ANALYSIS_QUESTIONS_FILE", "")
        if analysis_questions_file and Path(analysis_questions_file).exists():
            with open(analysis_questions_file, "r", encoding="utf-8") as f:
                self.analysis_questions = f.read()
        else:
            # 默认的分析问题
            self.analysis_questions = """
1. 该大学是否招收外国人留学生？
2. 招收外国人留学生的学部和专业有哪些？
3. 外国人留学生的报名条件是什么？
4. 需要提交的申请材料有哪些？
5. 入学考试的内容和形式是什么？
6. 报名和考试的时间安排如何？
7. 学费和其他费用是多少？
8. 是否有奖学金制度？
"""

        self._initialized = True


class PDFProcessor:
    """PDF处理器主类"""

    def __init__(
        self,
        task_id: str,
        university_name: str,
        pdf_file_path: str,
        restart_from_step: str = None,
        processing_mode: str = "normal",
    ):
        """
        初始化PDF处理器

        参数:
            task_id: 任务ID
            university_name: 大学名称
            pdf_file_path: PDF文件路径
            restart_from_step: 从哪个步骤开始重启（可选）
            processing_mode: 处理模式 ("normal" | "batch")
        """
        self.task_id = task_id
        self.university_name = university_name
        self.pdf_file_path = pdf_file_path
        self.restart_from_step = restart_from_step
        self.processing_mode = processing_mode
        self.config = Config()

        # 创建任务专用的工作目录
        self.task_dir = self.config.temp_dir / f"task_{task_id}"
        self.task_dir.mkdir(exist_ok=True)

        # 初始化各种工具
        self.ocr_tool = None
        self.batch_ocr_tool = None
        self.translate_tool = None
        self.analysis_tool = None

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
                logger.error("无法连接到数据库")
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
            logger.info(f"任务 {self.task_id} 状态已更新: {status}")
        except Exception as e:
            logger.error(f"更新任务状态失败: {e}")

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
            logger.error(f"写入任务日志失败: {e}")

        # 同时写入系统日志
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

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
            self._log_message(f"已加载 {len(self.previous_results)} 个之前的处理结果")

    def process_step_01_pdf2img(self, work: Work) -> bool:
        """步骤1: PDF转图片"""
        try:
            self._log_message("开始PDF转图片...")
            self._update_task_status("processing", "01_pdf2img", 10)

            pdf_path = Path(self.pdf_file_path)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

            # 创建图片输出目录
            images_dir = self.task_dir / "images"
            images_dir.mkdir(exist_ok=True)

            # 转换PDF为图片
            self._log_message(f"正在转换PDF文件: {pdf_path}")
            images = convert_from_path(str(pdf_path), dpi=self.config.ocr_dpi)

            image_paths = []
            for i, image in enumerate(images, 1):
                image_path = images_dir / f"page_{i:03d}.png"
                image.save(str(image_path), "PNG")
                image_paths.append(str(image_path))
                self._log_message(f"已保存页面 {i}: {image_path.name}")

            # 保存图片路径列表到实例数据
            if not hasattr(self, "step_data"):
                self.step_data = {}
            self.step_data["image_paths"] = image_paths
            self.step_data["total_pages"] = len(image_paths)

            self._log_message(f"PDF转图片完成，共 {len(image_paths)} 页")
            return True

        except Exception as e:
            error_msg = f"PDF转图片失败: {str(e)}"
            self._log_message(error_msg, "ERROR")
            return False

    def process_step_02_ocr(self, work: Work) -> bool:
        """步骤2: OCR识别"""
        if self.processing_mode == "batch":
            return self._process_batch_ocr()
        else:
            return self._process_normal_ocr()

    def _process_normal_ocr(self) -> bool:
        """普通OCR处理模式"""
        try:
            self._log_message("开始OCR识别（普通模式）...")
            self._update_task_status("processing", "02_ocr", 30)

            # 初始化OCR工具
            if not self.ocr_tool:
                self.ocr_tool = OCRTool()

            # 获取图片路径
            image_paths = self._get_image_paths()
            if not image_paths:
                raise ValueError("没有找到图片文件")

            # 创建OCR输出目录
            ocr_dir = self.task_dir / "ocr"
            ocr_dir.mkdir(exist_ok=True)

            markdown_contents = []
            for i, image_path in enumerate(image_paths, 1):
                self._log_message(f"正在OCR识别第 {i}/{len(image_paths)} 页...")

                try:
                    md_content = self.ocr_tool.img2md(image_path)
                    if md_content and md_content.strip() != "EMPTY_PAGE":
                        markdown_contents.append(md_content)

                        # 保存单页OCR结果
                        page_md_file = ocr_dir / f"page_{i:03d}.md"
                        with open(page_md_file, "w", encoding="utf-8") as f:
                            f.write(md_content)

                        self._log_message(f"第 {i} 页OCR完成")
                    else:
                        self._log_message(f"第 {i} 页为空白页，已跳过")

                except Exception as e:
                    self._log_message(f"第 {i} 页OCR失败: {str(e)}", "WARNING")
                    continue

            if not markdown_contents:
                raise ValueError("所有页面OCR都失败了")

            # 合并所有OCR结果
            combined_markdown = "\n\n".join(markdown_contents)
            self._save_ocr_results(combined_markdown)

            self._log_message(f"OCR识别完成，共处理 {len(markdown_contents)} 页有效内容")
            return True

        except Exception as e:
            error_msg = f"OCR识别失败: {str(e)}"
            self._log_message(error_msg, "ERROR")
            return False

    def _process_batch_ocr(self) -> bool:
        """批量OCR处理模式"""
        try:
            self._log_message("开始OCR识别（批量模式）...")
            self._update_task_status("processing", "02_ocr", 30)

            # 初始化批量OCR工具
            if not self.batch_ocr_tool:
                self.batch_ocr_tool = BatchOCRTool()
            if not self.ocr_tool:
                self.ocr_tool = OCRTool()

            # 获取图片路径
            image_paths = self._get_image_paths()
            if not image_paths:
                raise ValueError("没有找到图片文件")

            # 保存图片路径列表到实例数据（确保数据一致性）
            if not hasattr(self, "step_data"):
                self.step_data = {}
            self.step_data["image_paths"] = image_paths
            self.step_data["total_pages"] = len(image_paths)

            # 检查是否已有批次在处理中
            batch_status = self.batch_ocr_tool.check_batch_status(self.task_id)

            if "error" not in batch_status and batch_status.get("total_batches", 0) > 0:
                # 已有批次，检查状态
                self._log_message(f"发现已提交的批次，总数: {batch_status['total_batches']}")
                if not batch_status.get("all_completed", False):
                    # 还没完成，继续等待
                    self._log_message("批次尚未完成，继续等待...")
                    self._update_task_status("processing", "02_ocr_batch_waiting", 35)
                    return self._wait_for_batch_completion()
                else:
                    # 已完成，获取结果
                    self._log_message("批次已完成，获取结果...")
                    return self._retrieve_and_save_batch_results()
            else:
                # 没有批次，提交新的批次
                self._log_message(f"提交批量OCR处理，共 {len(image_paths)} 页")
                try:
                    batch_ids = self.batch_ocr_tool.submit_batch_ocr(image_paths, self.task_id)
                    self._log_message(f"已提交 {len(batch_ids)} 个批次: {batch_ids}")
                    self._update_task_status("processing", "02_ocr_batch_submitted", 32)

                    # 开始等待完成
                    return self._wait_for_batch_completion()

                except Exception as e:
                    self._log_message(f"提交批量OCR失败，回退到普通模式: {e}", "WARNING")
                    return self._process_normal_ocr()

        except Exception as e:
            error_msg = f"批量OCR处理失败: {str(e)}"
            self._log_message(error_msg, "ERROR")
            # 回退到普通模式
            self._log_message("回退到普通OCR模式", "WARNING")
            return self._process_normal_ocr()

    def _wait_for_batch_completion(self) -> bool:
        """等待批次完成"""
        max_wait_time = 24 * 60 * 60  # 最大等待24小时
        check_interval = 5 * 60  # 每5分钟检查一次
        start_time = time.time()

        while time.time() - start_time < max_wait_time:
            batch_status = self.batch_ocr_tool.check_batch_status(self.task_id)

            if "error" in batch_status:
                self._log_message(f"检查批次状态失败: {batch_status['error']}", "ERROR")
                return False

            completed = batch_status.get("completed_batches", 0)
            total = batch_status.get("total_batches", 0)
            failed = batch_status.get("failed_batches", 0)
            processing = batch_status.get("processing_batches", 0)

            self._log_message(f"批次状态: {completed}/{total} 完成, {failed} 失败, {processing} 处理中")

            if batch_status.get("all_completed", False):
                self._log_message("所有批次已完成！")
                return self._retrieve_and_save_batch_results()

            # 更新进度
            if total > 0:
                progress = 30 + int((completed / total) * 10)  # 30-40%的进度
                self._update_task_status("processing", "02_ocr_batch_waiting", progress)

            # 等待下次检查
            self._log_message(f"等待 {check_interval//60} 分钟后再次检查...")
            time.sleep(check_interval)

        # 超时
        self._log_message("批次处理超时，回退到普通模式", "WARNING")
        return self._process_normal_ocr()

    def _retrieve_and_save_batch_results(self) -> bool:
        """获取并保存批次结果"""
        try:
            self._log_message("获取批次处理结果...")
            page_results = self.batch_ocr_tool.retrieve_batch_results(self.task_id, self.ocr_tool)

            if not page_results:
                raise ValueError("批次处理未返回任何结果")

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
                raise ValueError("所有页面批次处理都失败了")

            # 合并所有OCR结果
            combined_markdown = "\n\n".join(markdown_contents)
            self._save_ocr_results(combined_markdown)

            # 清理批次数据
            self.batch_ocr_tool.cleanup_batch_data(self.task_id)

            self._log_message(f"批量OCR识别完成，共处理 {len(markdown_contents)} 页有效内容")
            return True

        except Exception as e:
            error_msg = f"获取批次结果失败: {str(e)}"
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

    def process_step_03_translate(self, work: Work) -> bool:
        """步骤3: 翻译"""
        try:
            self._log_message("开始翻译...")
            self._update_task_status("processing", "03_translate", 50)

            # 初始化翻译工具
            if not self.translate_tool:
                self.translate_tool = TranslateTool(self.config.translate_terms)

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
                raise ValueError("没有找到原始MD内容")

            # 执行翻译
            self._log_message("正在翻译日语内容为中文...")
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

            self._log_message("翻译完成")
            return True

        except Exception as e:
            error_msg = f"翻译失败: {str(e)}"
            self._log_message(error_msg, "ERROR")
            return False

    def process_step_04_analysis(self, work: Work) -> bool:
        """步骤4: 分析"""
        try:
            self._log_message("开始分析...")
            self._update_task_status("processing", "04_analysis", 70)

            # 初始化分析工具
            if not self.analysis_tool:
                self.analysis_tool = AnalysisTool(
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
                raise ValueError("没有找到翻译后的MD内容")

            # 执行分析
            self._log_message("正在分析招生信息...")
            analysis_report = self.analysis_tool.md2report(translated_md_content)

            # 保存分析报告
            report_md_file = self.task_dir / "report.md"
            with open(report_md_file, "w", encoding="utf-8") as f:
                f.write(analysis_report)

            self.step_data["report_md_path"] = str(report_md_file)
            self.step_data["report_md_content"] = analysis_report

            self._log_message("分析完成")
            return True

        except Exception as e:
            error_msg = f"分析失败: {str(e)}"
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
                        self._log_message(f"从分析报告中提取到大学中文名称: {university_name_zh}")
                        return university_name_zh

            self._log_message("未在分析报告中找到大学中文名称", "WARNING")
            return None
        except Exception as e:
            self._log_message(f"提取大学中文名称时出错: {e}", "ERROR")
            return None

    def process_step_05_output(self, work: Work) -> bool:
        """步骤5: 输出到MongoDB"""
        try:
            self._log_message("开始输出到数据库...")
            self._update_task_status("processing", "05_output", 90)

            db = get_db()
            if db is None:
                raise ValueError("无法连接到数据库")

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
                raise ValueError("处理结果不完整")

            # 从分析报告中提取大学中文全称
            university_name_zh = self._extract_university_name_zh(report_md)
            if not university_name_zh:
                # 如果没有提取到，使用原始大学名称作为备选
                university_name_zh = self.university_name
                self._log_message(f"使用原始大学名称作为中文名称: {university_name_zh}")

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

            self._log_message(f"成功保存到数据库，大学ID: {university_id}")
            return True

        except Exception as e:
            error_msg = f"输出到数据库失败: {str(e)}"
            self._log_message(error_msg, "ERROR")
            self.step_data["error"] = error_msg
            return False

    def run_processing(self) -> bool:
        """运行完整的处理流程，使用Buffalo管理工作流程"""
        try:
            self._log_message("开始处理PDF文件...")
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
                raise ValueError("无法创建Buffalo项目")

            self._log_message(f"Buffalo项目已创建: {project_name}")

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
                self._log_message(f"从步骤 {self.restart_from_step} 开始重启任务")
                self._load_previous_results()
                self._setup_restart_from_step(buffalo, project, self.restart_from_step)

            # 使用Buffalo的工作流程执行
            success = True
            while True:
                # 获取下一个待执行的任务
                work = project.get_next_not_started_work()

                if not work:
                    # 工作流程完成
                    self._log_message("所有步骤执行完成")
                    break

                step_name = work.name
                self._log_message(f"Buffalo获取到任务: {step_name}")

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
                            self._log_message(f"步骤 {step_name} 执行成功")
                        else:
                            buffalo.update_work_status(project_name, work, "failed")
                            buffalo.save_project(project, project_name)
                            self._log_message(f"步骤 {step_name} 执行失败", "ERROR")
                            success = False
                            break

                    except Exception as e:
                        buffalo.update_work_status(project_name, work, "failed")
                        buffalo.save_project(project, project_name)
                        error_msg = f"步骤 {step_name} 执行异常: {str(e)}"
                        self._log_message(error_msg, "ERROR")
                        success = False
                        break
                else:
                    error_msg = f"未知的步骤: {step_name}"
                    self._log_message(error_msg, "ERROR")
                    buffalo.update_work_status(project_name, work, "failed")
                    buffalo.save_project(project, project_name)
                    success = False
                    break

            if success:
                self._log_message("PDF处理完成！")
                self._update_task_status("completed", "finished", 100)
                self._cleanup_temp_files()
                return True
            else:
                error_msg = "工作流程执行失败"
                self._log_message(error_msg, "ERROR")
                self._update_task_status("failed", "error", 0, error_msg)
                return False

        except Exception as e:
            error_msg = f"处理过程中发生错误: {str(e)}"
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
                        self._log_message(f"步骤 {prev_work.name} 标记为已完成")
                    elif prev_work.index >= work.index:
                        buffalo.update_work_status(project_name, prev_work, "not_started")
                        self._log_message(f"步骤 {prev_work.name} 重置为未开始")
                break

        # 保存项目状态
        buffalo.save_project(project, project_name)
        self._log_message("重启设置已保存")

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
        """清理临时文件"""
        try:
            if self.task_dir.exists():
                shutil.rmtree(self.task_dir)
                self._log_message("临时文件已清理")
        except Exception as e:
            self._log_message(f"清理临时文件失败: {str(e)}", "WARNING")


def run_pdf_processor(
    task_id: str,
    university_name: str,
    pdf_file_path: str,
    restart_from_step: str = None,
    processing_mode: str = "normal",
) -> bool:
    """
    运行PDF处理器的入口函数

    参数:
        task_id: 任务ID
        university_name: 大学名称
        pdf_file_path: PDF文件路径
        restart_from_step: 从哪个步骤开始重启（可选）
        processing_mode: 处理模式 ("normal" | "batch")

    返回:
        bool: 处理是否成功
    """
    processor = PDFProcessor(task_id, university_name, pdf_file_path, restart_from_step, processing_mode)
    return processor.run_processing()
