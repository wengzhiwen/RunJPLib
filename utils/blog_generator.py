"""
使用AI生成博客文章的工具。
该模块改编自参考脚本 `blog_writer.py` 的逻辑，
支持多种生成模式和内容格式化。
"""
from datetime import datetime
import json
import os
from typing import Dict, List, Optional

from agents import Agent
from agents import Runner
from agents import trace
from bson.objectid import ObjectId
from dotenv import load_dotenv
import nest_asyncio

from utils.logging_config import setup_logger
from utils.mongo_client import get_mongo_client

# 应用补丁以允许嵌套的asyncio事件循环
nest_asyncio.apply()

# 设置独立的日志记录器
logger = setup_logger(logger_name="BlogGenerator", log_level="INFO")

# --- 系统提示词 ---

PROMPT_EXPAND = f"""
你是一位专业的日本留学相关的文章的简体中文BLOG写作专家。

你的工作是：
1、根据用户提供的基础材料（markdown文件内容，一般是大学的留学生招生简章）和扩展写作方向
2、在保持原材料核心信息准确性的基础上，按照指定的写作方向进行BLOG的书写
3、你要写作的BLOG文章是根据扩展写作方向的要求来撰写的，并不是以对基础材料的归纳和总结为主，具体原始材料需要引用到什么程度，请根据扩展写作方向来决定
4、确保文章内容轻松易读，适合SEO优化
5、如果你有互联网搜索能力，请使用互联网搜索能力来获取更多信息，但请确保只搜索日文的信息，不要搜索中文的信息
6、记录下在你输出中提到的大学中文名称（全名）列表（大学中文全名、大学日文全名）
7、表格是很好的信息组织方式，如果需要，可以使用markdown的语法来表示表格
8、为防止简单盗取，文章中应以“润日图书馆”、“本馆”等相关名称自称

请以JSON格式返回结果，格式如下：
{{
    "title": "文章标题",
    "content": "文章内容",
    "universities": [
        {{
            "chinese_name": "大学中文名",
            "japanese_name": "大学日文名(日文全名，不是英文名)"
        }}
    ]
}}

注意：
 - 标题要体现扩展的写作方向，并带上今年的年份：{datetime.now().year + 1}，以提升SEO的水准
 - 请严格基于提供的基础材料进行扩展，如果要添加补充的信息，请务必使用互联网上的权威日语信息（千万不要参考中文的信息）
 - 你撰写的文章中必须使用大学完整的中文名称
 - 不要添加任何主观臆断，不要推测基础材料中没有的信息
 - 对于重要的数据，请保持原样，不要进行任何修改
 - 文章内容要正面积极
 - 不要在返回中带有```json 或是 ``` 这样的定界符
 - 请使用简体中文输出
"""

PROMPT_COMPARE = f"""
你是一位专业的日本留学相关的文章的写作专家。
除非输出内容中明确要求使用日语的部分，其他部分一律使用中文输出。

你的工作是：
1、根据用户输入的多个大学的参考内容，分析这些大学的共同点和特色
2、撰写一篇综合性的文章，重点突出这些大学的共同特点和各自的特色对大学进行推荐
3、不要机械的去写共同特点是xxx，共同特色是xxx，共同特色更多的体现在标题和开头即可，内容还是以各个大学分别的介绍为主
4、对于可以渡日前申请、只需要进行线上面试等入学方式比较便捷的大学进行特别说明，但篇幅不要多
5、文章内容要轻松易读，适合SEO优化
6、表格是很好的信息组织方式，如果需要，可以使用markdown的语法来表示表格
7、为防止简单盗取，文章中应以“润日图书馆”、“本馆”等相关名称自称

请以JSON格式返回结果，格式如下：
{{
    "title": "文章标题",
    "content": "文章内容",
    "universities": [
        {{
            "chinese_name": "大学中文名",
            "japanese_name": "大学日文名(日文全名，不是英文名)"
        }}
    ]
}}

注意：
 - 标题不要太长，但要带上今年的年份：{datetime.now().year}，以提升SEO的水准
 - 请不要对日本留学相关的内容进行任何推测，不要添加任何主观臆断
 - 你撰写的文章中必须使用大学完整的中文名称
 - 不要添加任何主观臆断，不要添加任何原文中不存在的信息（哪怕是一些常识性的信息），不要推测 不要推测 不要推测！
 - 对于重要的数据，请保持原样，不要进行任何修改
 - 文章内容要正面积极
 - 不要在返回中带有```json 或是 ``` 这样的定界符
"""

PROMPT_USER_ONLY = """
你是一位专业的日本留学相关的文章的写作优化专家。
你的工作是：
1、根据用户输入的参考内容，重新进行组织和优化，使得文章内容更加轻松、易读
2、必要时根据你所掌握的日本留学相关的准确知识进行适当的补充
3、你所写的内容主要会被应用于留学相关网站的SEO，请务必确保文章内容对SEO友好
4、只有用户输入的参考内容中提到的大学，你才可以在输出中提及
5、记录下在你输出中提到的大学中文名称（全名）列表（大学中文全名、大学日文全名）
6、在文章的末尾添加一个"相关大学"的标题，列出上表中的中文全名
7、表格是很好的信息组织方式，如果需要，可以使用markdown的语法来表示表格
8、为防止简单盗取，文章中应以“润日图书馆”、“本馆”等相关名称自称

请以JSON格式返回结果，格式如下：
{{
    "title": "文章标题",
    "content": "文章内容",
    "universities": [
        {{
            "chinese_name": "大学中文名",
            "japanese_name": "大学日文名(日文全名，不是英文名)"
        }}
    ]
}}

注意：
 - 请不要对日本留学相关的内容进行任何推测，不要添加任何主观臆断
 - 输入的原文中可能存在一些留学咨询机构的广告（比如请咨询XXX，或是XXX位你提供服务），请不要在你输出的内容中保留任何的广告内容，特别是联系方式
 - 你撰写的文章中必须使用大学完整的中文名称
 - 不要在返回中带有```json 或是 ``` 这样的定界符
"""

PROMPT_REDUCER = """
你是一位专业的日本大学招生简章的缩减专家。
如果输入的内容原文是日语，那你的输出也必须是日语，否则请输出中文。

你的工作是：
1. 仔细阅读文章全文，对文章中提到的信息完全把握的前提下进行后续步骤
2. 对文章内容按以下要求进行处理：
 - 保留：大学的全名、基本信息，概况介绍；如果特别长进行适当缩减
 - 保留：大学或学部的特色说明，但删除与外国人留学生招募不相关的学部；如果特别长进行适当缩减
 - 删除：学校创始人 校长 教学理念等相关的介绍，但如果有和这个学校相关的名人的介绍可以进行适当缩减
 - 简化：各个学部的招生要求中，只保留与外国人留学生有关的学部（本科）的招生信息，并进行简化，将要求类似的学部进行合并
 - 保留：如果有提到和大学排名相关的信息，请保留
 - 保留：在几月进行出愿（报名）、考试、合格发表、入学等关键时间点，精确到月份，不需要保留年份和具体日期
3. 输出结果第一行为大学的日文全名

注意事项：
1. 请确保提取的信息准确、客观，不要添加任何主观臆断
2. 所有提取的信息请控制在5000字以内
3. 不需要保留原文的格式（比如Markdown），特别是繁复的表格只需要准确提取表格所表达的信息的概要内容即可
4. 不要添加任何主观臆断，不要添加任何原文中不存在的信息（哪怕是一些常识性的信息），不要推测 不要推测 不要推测！
5. 对于重要的数据，请保持原样，不要进行任何修改
6. 不需要保留任何和年份有关的信息
"""

PROMPT_FORMATTER = """
你是一位专业的日本留学相关的文章的格式化专家。
你的工作是将输入的文章内容进行markdown格式化：
1、将文章内容进行markdown格式化，注意正确的使用H1～H4的标题以及加粗等markdown语法
2、表格的排版要特别注意，保证表格的完整性


请以JSON格式返回结果，格式如下：
{{
    "formatted_content": "格式化后的文章内容"
}}

注意：
- 你的工作只是进行格式化，除非有明显的中文语法错误，不要对文章内容进行任何的修改
- 返回的formatted_content不应该带有任何 ```json 或是 ``` 或是 ```markdown 这样的标记

关于Markdown的语法格式，特别注意以下要求：
1. 表格前后的空行要保留
2. 列表前后的空行要保留
3. 标题前后的空行要保留
4. 表格的排版（特别是合并单元格）要与原文（图片）完全一致
5. 根据Markdown的语法，需要添加空格的地方，请务必添加空格；但不要在表格的单元格内填充大量的空格，需要的话填充一个空格即可
6. 文章开始的summary部分（若有）可以使用块引用的语法来突出表示
总之，要严格的践行Markdown的语法要求，不要只是看上去像，其实有不少语法错误
"""


class BlogGenerator:

    def __init__(self):
        load_dotenv()
        self.model = os.getenv("OPENAI_BLOG_WRITER_MODEL", "gpt-4o")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set.")
            raise ValueError("OpenAI API key not set.")

        # 设置环境变量禁用重试，避免429错误时的自动重试
        os.environ["OPENAI_MAX_RETRIES"] = "0"

        logger.info(f'BlogGenerator setup with model: {self.model}')

    def _create_agent(self, name: str, system_prompt: str) -> Agent:
        return Agent(name=name, model=self.model, instructions=system_prompt)

    def _run_agent_and_parse_json(self, agent: Agent, task_prompt: str) -> Dict:
        logger.info(f"Running agent: {agent.name}...")
        logger.info(f"Task prompt length: {len(task_prompt)} characters")

        with trace(f"Agent-{agent.name}"):
            input_items = [{"role": "user", "content": task_prompt}]
            try:
                result = Runner.run_sync(agent, input_items)
                if not result or not result.final_output:
                    raise Exception(f"Agent {agent.name} failed to generate content.")
            except Exception as e:
                logger.error(f"Agent {agent.name} execution failed: {e}", exc_info=True)
                # 检查是否是429错误
                if "429" in str(e):
                    logger.warning(f"Detected 429 error in agent {agent.name}, this should not retry automatically")
                raise e

        logger.info(f"Agent {agent.name} finished generation.")
        logger.info(f"Agent {agent.name} output length: {len(result.final_output)} characters")
        logger.debug(f"Agent {agent.name} raw output: {result.final_output[:500]}...")

        try:
            parsed_result = json.loads(result.final_output)
            logger.info(f"Successfully parsed JSON from agent {agent.name}")
            logger.debug(f"Parsed result keys: {list(parsed_result.keys())}")
            return parsed_result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from agent {agent.name}. Error: {e}")
            logger.error(f"Raw output (first 1000 chars): {result.final_output[:1000]}")
            return {"title": "生成结果（JSON格式错误）", "content": result.final_output, "universities": []}

    def _get_university_materials(self, university_ids: List[str]) -> List[Dict]:
        client = get_mongo_client()
        if not client:
            raise ConnectionError("Could not connect to MongoDB.")
        db = client.RunJPLib

        materials = []
        for uid_str in university_ids:
            try:
                obj_id = ObjectId(uid_str)
                university = db.universities.find_one({"_id": obj_id})
                if university and "content" in university:
                    # 获取原始markdown和基础分析报告
                    original_md = university["content"].get("original_md", "")
                    report_md = university["content"].get("report_md", "")

                    if original_md or report_md:
                        materials.append({"name": university["university_name"], "original_md": original_md, "report_md": report_md})
            except Exception:
                logger.warning(f"Invalid ObjectId string or DB error for: {uid_str}")
        return materials

    def _format_content(self, content_to_format: str) -> str:
        if not content_to_format or not content_to_format.strip():
            return content_to_format

        logger.info("Formatting blog content with Markdown...")
        formatter_agent = self._create_agent("blog_formatter", PROMPT_FORMATTER)
        task_prompt = f"请格式化以下文章：\n\n{content_to_format}"

        try:
            formatted_data = self._run_agent_and_parse_json(formatter_agent, task_prompt)
            return formatted_data.get("formatted_content", content_to_format)
        except Exception as e:
            logger.error(f"An error occurred during content formatting: {e}", exc_info=True)
            return content_to_format  # 失败时返回原始内容

    def generate_blog_content(self, mode: str, university_ids: List[str], user_prompt: str, system_prompt: str) -> Optional[Dict]:
        try:
            initial_result = None
            if mode == 'expand':
                initial_result = self._generate_expand_mode(university_ids, user_prompt, system_prompt)
            elif mode == 'compare':
                initial_result = self._generate_compare_mode(university_ids, user_prompt, system_prompt)
            elif mode == 'user_prompt_only':
                initial_result = self._generate_user_prompt_mode(user_prompt, system_prompt)
            else:
                raise ValueError(f"Unknown generation mode: {mode}")

            if initial_result and initial_result.get("content"):
                logger.info(f"Formatting content, original length: {len(initial_result['content'])} characters")
                formatted_content = self._format_content(initial_result["content"])
                initial_result["content"] = formatted_content
                logger.info(f"Content formatted, new length: {len(formatted_content)} characters")

            logger.info(f"Blog generation completed successfully, returning result with keys: {list(initial_result.keys()) if initial_result else 'None'}")
            return initial_result

        except Exception as e:
            logger.error(f"An error occurred during blog generation (mode: {mode}): {e}", exc_info=True)
            return None

    def _generate_expand_mode(self, university_ids: List[str], user_prompt: str, system_prompt: str) -> Dict:
        materials_data = self._get_university_materials(university_ids)
        if not materials_data:
            raise ValueError("Expand mode requires at least one university to be selected.")

        # 首先尝试使用原始内容
        materials_text = "\n\n---\n\n".join([f"大学名称: {u['name']}\n\n{u['original_md']}" for u in materials_data])
        task_prompt = f"""
请根据以下基础材料和扩展写作方向，撰写一篇扩展性的日本留学BLOG文章。
基础材料：
{materials_text}
扩展写作方向：
{user_prompt}
"""
        agent = self._create_agent("expand_writer", system_prompt)

        try:
            return self._run_agent_and_parse_json(agent, task_prompt)
        except Exception as e:
            # 检查是否是OpenAI API速率限制错误
            if "429" in str(e) and "tokens per min" in str(e):
                logger.warning(f"OpenAI API速率限制错误，尝试使用基础分析报告替代长文本内容: {e}")

                # 使用基础分析报告替代原始内容
                materials_text_report = "\n\n---\n\n".join([f"大学名称: {u['name']}\n\n{u['report_md']}" for u in materials_data if u.get('report_md')])
                if not materials_text_report:
                    logger.error("没有可用的基础分析报告，无法继续处理")
                    raise e

                task_prompt_report = f"""
请根据以下基础材料和扩展写作方向，撰写一篇扩展性的日本留学BLOG文章。
基础材料（基于分析报告）：
{materials_text_report}
扩展写作方向：
{user_prompt}
"""

                try:
                    return self._run_agent_and_parse_json(agent, task_prompt_report)
                except Exception as e2:
                    logger.error(f"使用基础分析报告后仍然失败: {e2}", exc_info=True)
                    raise e2
            else:
                # 其他类型的错误，直接抛出
                raise e

    def _generate_compare_mode(self, university_ids: List[str], user_prompt: str, system_prompt: str) -> Dict:
        materials_data = self._get_university_materials(university_ids)
        if len(materials_data) < 2:
            raise ValueError("Compare mode requires at least two universities.")

        reducer_agent = self._create_agent("article_reducer", PROMPT_REDUCER)
        summaries = []

        try:
            # 首先尝试使用原始内容
            for material in materials_data:
                logger.info(f"Reducing content for {material['name']}...")
                task_prompt = f"请缩减以下文章内容：\n\n{material['original_md']}"
                input_items = [{"role": "user", "content": task_prompt}]
                result = Runner.run_sync(reducer_agent, input_items)
                if result and result.final_output:
                    summaries.append(result.final_output)

            combined_summaries = "\n\n---\n\n".join(summaries)
            task_prompt = f"""
请根据以下多所大学的信息，撰写一篇综合性的日本留学的BLOG。
{combined_summaries}

另外，请参考用户的以下要求来组织文章：
{user_prompt}
"""
            compare_agent = self._create_agent("comparative_writer", system_prompt)
            return self._run_agent_and_parse_json(compare_agent, task_prompt)

        except Exception as e:
            # 检查是否是OpenAI API速率限制错误
            if "429" in str(e) and "tokens per min" in str(e):
                logger.warning(f"OpenAI API速率限制错误，尝试使用基础分析报告替代长文本内容: {e}")

                # 使用基础分析报告替代原始内容
                summaries_report = []
                for material in materials_data:
                    if material.get('report_md'):
                        logger.info(f"Using analysis report for {material['name']}...")
                        summaries_report.append(material['report_md'])
                    else:
                        # 如果没有分析报告，使用原始内容的截断版本
                        logger.info(f"No analysis report for {material['name']}, using truncated original content")
                        summaries_report.append(material['original_md'][:2000] + "..." if len(material['original_md']) > 2000 else material['original_md'])

                combined_summaries_report = "\n\n---\n\n".join(summaries_report)
                task_prompt_report = f"""
请根据以下多所大学的信息，撰写一篇综合性的日本留学的BLOG。
{combined_summaries_report}

另外，请参考用户的以下要求来组织文章：
{user_prompt}
"""

                try:
                    compare_agent = self._create_agent("comparative_writer", system_prompt)
                    return self._run_agent_and_parse_json(compare_agent, task_prompt_report)
                except Exception as e2:
                    logger.error(f"使用基础分析报告后仍然失败: {e2}", exc_info=True)
                    raise e2
            else:
                # 其他类型的错误，直接抛出
                raise e

    def _generate_user_prompt_mode(self, user_prompt: str, system_prompt: str) -> Dict:
        if not user_prompt:
            raise ValueError("User prompt cannot be empty for this mode.")

        task_prompt = f"""
请根据以下参考内容，撰写一篇专业的日本留学咨询文章。
参考内容：
{user_prompt}
"""
        agent = self._create_agent("article_writer", system_prompt)
        return self._run_agent_and_parse_json(agent, task_prompt)
