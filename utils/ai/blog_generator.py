"""
使用AI生成博客文章的工具。
该模块改编自参考脚本 `blog_writer.py` 的逻辑，
支持多种生成模式和内容格式化。
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import nest_asyncio
from agents import Agent, Runner, trace
from bson.objectid import ObjectId
from dotenv import load_dotenv

from ..core.database import get_mongo_client
from ..core.logging import setup_logger

# 应用补丁以允许嵌套的asyncio事件循环
nest_asyncio.apply()

# 设置独立的日志记录器
logger = setup_logger(logger_name="ContentGenerator", log_level="INFO")

# --- 系统提示词 ---

PROMPT_EXPAND = f"""
你是一位专业的日本留学相关的文章的简体中文BLOG写作专家。

你的工作是：
1、根据用户提供的基础材料（markdown文件内容，一般是大学的留学生招生简章）和扩展写作方向
2、在保持原材料核心信息准确性的基础上，按照指定的写作方向进行BLOG的书写
3、你要写作的BLOG文章是根据扩展写作方向的要求来撰写的，并不是以对基础材料的归纳和总结为主，具体原始材料需要引用到什么程度，请根据扩展写作方向来决定
4、确保文章内容轻松易读，适合SEO优化
5、记录下在你输出中提到的大学中文名称（全名）列表（大学中文全名、大学日文全名）
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
 - 标题要体现扩展的写作方向，并带上今年的年份：{datetime.now().year + 1}，以提升SEO的水准
 - 请严格基于提供的基础材料进行扩展，不要添加任何主观臆断，不要添加任何原文中不存在的信息
 - 你撰写的文章中必须使用大学完整的中文名称
 - 对于重要的数据（计划录取数、学费等），请保持原样，不要进行任何修改
 - 对于重要的信息（电话号码、地址等），请保持原样，不要进行任何修改
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
 - 请不要对日本留学相关的内容进行任何推测，不要添加任何主观臆断，不要添加任何原文中不存在的信息
 - 你撰写的文章中必须使用大学完整的中文名称
 - 对于重要的数据（计划录取数、学费等），请保持原样，不要进行任何修改
 - 对于重要的信息（电话号码、地址等），请保持原样，不要进行任何修改
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
 - 请不要对日本留学相关的内容进行任何推测，不要添加任何主观臆断
 - 输入的原文中可能存在一些留学咨询机构的广告（比如请咨询XXX，或是XXX位你提供服务），请不要在你输出的内容中保留任何的广告内容，特别是联系方式
 - 你撰写的文章中必须使用大学完整的中文名称
 - 不要在返回中带有```json 或是 ``` 这样的定界符
"""

PROMPT_REDUCER = """
你是一位专业的日本大学招生简章的缩减专家。
如果输入的内容原文是日语，那你的输出也必须是日语，否则请输出中文。
如果输入的内容本来就不长（不超过10000字），请直接输出原文。

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
2. 所有提取的信息请控制在10000字以内
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

PROMPT_WEB_SEARCH = """
你是一个专业的信息检索助手。

你的职责：
为文章撰写Agent提供补充材料；
补充的方向是为了让撰写出来的文章更加丰富，具有更大的吸引力和更强的SEO，而不是为了补充具体的招生信息；
根据用户的原始需求，从权威的日语站点（Wikipedia、大学官网等）中检索与用户的原始需求有关联的内容。

请直接以无格式的文本，按照相关度输出搜索结果（只要文本内容，不需要URL）。

注意：
- 不需要检索任何具体大学的招生政策，这些信息用户已经完全掌握
- 仅使用日语的权威来源，输出结果也为日语，你不需要处理翻译的工作
- 不要使用任何中文来源，也不要使用任何自媒体（如Twitter、Facebook等）的内容
- 不要编造，不要主观臆断
- 不要过长，控制在5000字以内
"""


class ContentGenerator:
    """内容生成器类，使用AI生成博客文章"""

    def __init__(self):
        load_dotenv()
        self.model = os.getenv("OPENAI_BLOG_WRITER_MODEL", "gpt-4o")
        self.web_search_enabled = os.getenv("OPENAI_WEB_SEARCH_ENABLED", "true").lower() == "true"
        self.web_search_model = os.getenv("OPENAI_WEB_SEARCH_MODEL", "gpt-4o-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set.")
            raise ValueError("OpenAI API key not set.")

        # 设置环境变量禁用重试，避免429错误时的自动重试
        os.environ["OPENAI_MAX_RETRIES"] = "0"

        logger.info(f"完成BlogGenerator的初始化，模型: {self.model}，网络搜索: {self.web_search_enabled}")
        if self.web_search_enabled:
            logger.info(f"网络搜索启用，模型: {self.web_search_model}")

    def _create_agent(self, name: str, system_prompt: str) -> Agent:
        return Agent(name=name, model=self.model, instructions=system_prompt)

    def _run_agent_and_parse_json(self, agent: Agent, task_prompt: str) -> Dict:
        logger.info(f"执行Agent: {agent.name}...")
        logger.info(f"任务提示词长度: {len(task_prompt)} 字符")

        with trace(f"Agent-{agent.name}"):
            input_items = [{"role": "user", "content": task_prompt}]
            try:
                result = Runner.run_sync(agent, input_items)
                if not result or not result.final_output:
                    raise Exception(f"Agent {agent.name} 生成内容失败。")
            except Exception as e:
                logger.error(f"Agent {agent.name} 执行失败: {e}", exc_info=True)
                # 检查是否是429错误
                if "429" in str(e):
                    logger.warning(f"检测到Agent {agent.name} 的429错误，不应自动重试")
                raise e

        logger.info(f"Agent {agent.name} 完成生成。")
        logger.info(f"Agent {agent.name} 输出长度: {len(result.final_output)} 字符")
        logger.debug(f"Agent {agent.name} 原始输出: {result.final_output[:500]}...")

        try:
            parsed_result = json.loads(result.final_output)
            logger.info(f"成功解析Agent {agent.name} 的JSON输出")
            logger.debug(f"Parsed result keys: {list(parsed_result.keys())}")
            return parsed_result
        except json.JSONDecodeError as e:
            logger.error(f"解析JSON from agent {agent.name}失败. Error: {e}")
            logger.error(f"Raw output (first 1000 chars): {result.final_output[:1000]}")
            return {"title": "生成结果（JSON格式错误）", "content": result.final_output, "universities": []}

    def _web_search_supplement(self, user_prompt: str, materials_data: List[Dict]) -> str:
        """使用OpenAI Responses API的web_search工具基于用户输入与大学名称做一次检索，
        返回简要中文要点以及URL列表，作为补充材料。

        返回：格式化好的补充文本，失败时返回空字符串。
        """
        if not self.web_search_enabled:
            return ""

        try:
            # 组合查询：用户要求 + 大学中文/日文名，强调仅检索日文权威来源
            university_names = []
            for u in materials_data:
                name = u.get("name")
                if name:
                    university_names.append(name)
            universities_text = "、".join(university_names) if university_names else ""
            logger.debug(f"WEB Search - 相关大学: {universities_text}")

            query_instruction = "请仅使用日语权威来源进行网络检索，补充与原材料相关的信息（比如大学的历史、特色、优势、名人、知名日剧等）。"

            input_text = (f"用户需求：{user_prompt}\n"
                          f"相关大学：{universities_text}\n"
                          f"检索要求：{query_instruction}")

            logger.debug(f"WEB Search - 输入文本: {input_text}")

            search_agent = Agent(name="web_search_agent", model=self.web_search_model, instructions=PROMPT_WEB_SEARCH)
            input_items = [{"role": "user", "content": [{"type": "input_text", "text": input_text}]}]
            result = Runner.run_sync(search_agent, input_items)
            text_output = (result.final_output or "").strip()

            if not text_output:
                return ""

            # 控制补充长度，避免过长
            if len(text_output) > 10000:
                text_output = text_output[:10000] + "..."

            supplement = ("网络检索补充材料（优先以大学官方信息为准）：\n\n"
                          f"{text_output.strip()}\n")
            return supplement
        except Exception as e:
            logger.warning(f"Web search supplement failed: {e}")
            return ""

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

        # 先执行一次web search补充材料
        web_search_text = self._web_search_supplement(user_prompt=user_prompt, materials_data=materials_data)

        reducer_agent = self._create_agent("article_reducer", PROMPT_REDUCER)
        summaries = []

        for material in materials_data:
            if len(material['original_md']) > 10000:
                logger.info(f"Reducing content for {material['name']}...")
                task_prompt = f"请缩减以下文章内容：\n\n{material['original_md']}"
                input_items = [{"role": "user", "content": task_prompt}]
                try:
                    result = Runner.run_sync(reducer_agent, input_items)
                    if result and result.final_output:
                        summaries.append(result.final_output)
                except Exception as e:
                    logger.error(f"Reducing content for {material['name']} failed: {e}", exc_info=True)
                    # 如果缩减失败，则使用原始内容的截断版本
                    summaries.append(material['original_md'][:10000] + "...")
            else:
                summaries.append(material['original_md'])

            # 添加基础分析报告
            summaries.append(material['report_md'])

        # 合并所有内容
        materials_text_report = "\n\n---\n\n".join(summaries)

        task_prompt = f"""
请根据以下基础材料、网络检索补充材料和扩展写作方向，撰写一篇扩展性的日本留学BLOG文章。
用户指定的写作方向：
{user_prompt}

可信的基础材料：
{materials_text_report}

通过网络检索补充的材料（以下为日语，但不影响你输出中文）：
{web_search_text}
"""
        logger.debug(f"Blog写作（扩展模式）完整提示词: {task_prompt}")
        if len(task_prompt) > 200000:
            logger.warning(f"Blog写作（扩展模式）完整提示词长度达到：{len(task_prompt)}，超过200000字符，将会实施截断")
            task_prompt = task_prompt[:200000] + "..."

        agent = self._create_agent("expand_writer", system_prompt)

        try:
            return self._run_agent_and_parse_json(agent, task_prompt)
        except Exception as e:
            logger.error(f"Blog写作（扩展模式）失败: {e}", exc_info=True)
            raise e

    def _generate_compare_mode(self, university_ids: List[str], user_prompt: str, system_prompt: str) -> Dict:
        materials_data = self._get_university_materials(university_ids)
        if len(materials_data) < 2:
            raise ValueError("Compare mode requires at least two universities.")

        reducer_agent = self._create_agent("article_reducer", PROMPT_REDUCER)
        summaries = []

        # 对每所大学先缩减 original_md，然后并入其 report_md 作为对比材料的一部分
        for material in materials_data:
            logger.info(f"Reducing content for {material['name']}...")
            task_prompt = f"请缩减以下文章内容：\n\n{material['original_md']}"
            input_items = [{"role": "user", "content": task_prompt}]
            result = Runner.run_sync(reducer_agent, input_items)
            if result and result.final_output:
                summaries.append(result.final_output)

            # 无论是否存在，都追加 report_md（可能为空字符串）
            summaries.append(material.get('report_md', ''))

        combined_summaries = "\n\n---\n\n".join(summaries)
        task_prompt = f"""
请根据以下多所大学的信息，撰写一篇综合性的日本留学的BLOG。
用户的写作要求如下：
{user_prompt}

以下是多所大学的基础材料：
{combined_summaries}
"""
        compare_agent = self._create_agent("comparative_writer", system_prompt)

        try:
            return self._run_agent_and_parse_json(compare_agent, task_prompt)
        except Exception as e:
            logger.error(f"Blog写作（对比模式）失败: {e}", exc_info=True)
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
