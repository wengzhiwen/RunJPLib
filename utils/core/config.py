"""
配置管理模块
包含系统配置信息的管理
"""

import os
from pathlib import Path


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
            self.buffalo_template_file = Path(__file__).parent.parent / "templates" / "workflow_template.yml"
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
