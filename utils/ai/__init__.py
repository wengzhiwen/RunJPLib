"""
AI相关工具模块
包含文档分析、内容生成、OCR、翻译等AI功能
"""

from .analysis_tool import DocumentAnalyzer
from .batch_ocr_tool import BatchOcrProcessor
from .blog_generator import ContentGenerator
from .ocr_tool import ImageOcrProcessor
from .translate_tool import DocumentTranslator

# 向后兼容的别名
AnalysisTool = DocumentAnalyzer
BlogGenerator = ContentGenerator
OCRTool = ImageOcrProcessor
BatchOCRTool = BatchOcrProcessor
TranslateTool = DocumentTranslator

__all__ = [
    'DocumentAnalyzer', 'AnalysisTool', 'ContentGenerator', 'BlogGenerator', 'ImageOcrProcessor', 'OCRTool', 'BatchOcrProcessor', 'BatchOCRTool',
    'DocumentTranslator', 'TranslateTool'
]
