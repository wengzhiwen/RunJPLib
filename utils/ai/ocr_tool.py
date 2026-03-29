"""
OCR处理器 - 基于 Responses API 的文档识别工具

PdfOcrProcessor: 将 PDF 直接发送给模型，进行文档级识别（主流程）
ImageOcrProcessor: 将图像发送给模型，用于 asset 图片识别（辅助流程）
"""
import base64
import json
import os
import time

from openai import OpenAI

from ..core.logging import setup_logger

logger = setup_logger(logger_name="OcrProcessor", log_level="INFO")

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

_IMAGE_OCR_PROMPT = """你是一个专业的OCR文本识别与Markdown格式化专家。
请仔细识别图像中的所有文本内容，直接输出为标准Markdown格式。

要求：
1. 仅提取图像中的实际文本，不要添加任何解释或说明
2. 保持原始日语文本，不要翻译
3. 表格使用Markdown表格语法精确提取，注意列数（包括空单元格）
4. 忽略纯图形内容（logo、地图、水印等）
5. 忽略页眉页脚，但保留原文中标注的页码
6. 如果图像没有有效文字内容，返回：EMPTY_PAGE
7. 不要添加任何```markdown```之类的定界符，直接输出Markdown文本"""


class PdfOcrProcessor:
    """
    PDF直接输入OCR处理器。

    将 PDF 文件上传至 Files API，通过 Responses API 直接发送给模型进行文档级识别，
    使用 Structured Outputs 返回结构化 JSON，提取 full_markdown 字段作为结果。
    """

    def __init__(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY 环境变量未设置")
        self.model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-5.4-mini")
        self.client = OpenAI()

    def pdf2md(self, pdf_path: str) -> str:
        """
        将 PDF 直接发送给模型进行文档级 OCR 识别，返回 Markdown 字符串。

        参数:
            pdf_path: PDF 文件路径

        返回:
            str: 识别后的 Markdown 文本；空文档返回空字符串
        """
        start_time = time.time()
        uploaded_file = None

        try:
            logger.info(f"上传 PDF 至 Files API: {pdf_path}")
            with open(pdf_path, "rb") as f:
                uploaded_file = self.client.files.create(file=f, purpose="user_data")
            logger.info(f"PDF 已上传，file_id: {uploaded_file.id}")

            response = self.client.responses.create(
                model=self.model_name,
                input=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "file_id": uploaded_file.id,
                        },
                        {
                            "type": "input_text",
                            "text": _PDF_OCR_PROMPT,
                        },
                    ],
                }],
                text={"format": {
                    "type": "json_schema",
                    "name": "ocr_result",
                    "schema": _OCR_JSON_SCHEMA,
                    "strict": True,
                }},
            )

            result = json.loads(response.output_text)
            full_markdown = result.get("full_markdown", "")
            document_type = result.get("document_type", "")

            elapsed = time.time() - start_time
            logger.info(f"PDF OCR 完成，文档类型: {document_type}，耗时: {elapsed:.2f}秒")

            if full_markdown.strip() == "EMPTY_PAGE":
                return ""
            return full_markdown

        except Exception as e:
            logger.error(f"PDF OCR 失败: {e}")
            raise

        finally:
            if uploaded_file:
                try:
                    self.client.files.delete(uploaded_file.id)
                    logger.info(f"已删除临时文件: {uploaded_file.id}")
                except Exception:
                    pass


class ImageOcrProcessor:
    """
    图像 OCR 处理器（用于 asset 图片识别）。

    将图像通过 Responses API 发送给模型，单次调用完成 OCR + Markdown 格式化。
    """

    def __init__(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY 环境变量未设置")
        self.model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-5.4-mini")
        self.client = OpenAI()

    def img2md(self, image_path: str) -> str:
        """
        将图像识别为 Markdown 文本。

        参数:
            image_path: 图像文件路径

        返回:
            str: 识别后的 Markdown 文本
        """
        start_time = time.time()
        logger.info(f"对图像进行 OCR 识别: {image_path}")

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        response = self.client.responses.create(
            model=self.model_name,
            input=[{
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
                        "text": _IMAGE_OCR_PROMPT,
                    },
                ],
            }],
        )

        result = response.output_text.strip()
        # 清理可能残留的 markdown 定界符
        for marker in ("```markdown", "```Markdown", "```"):
            result = result.replace(marker, "")
        result = result.strip()

        elapsed = time.time() - start_time
        logger.info(f"图像 OCR 完成，耗时: {elapsed:.2f}秒")
        return result
