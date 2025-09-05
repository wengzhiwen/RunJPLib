"""
Blog Wiki处理器
自动识别blog内容中的学校名称并添加超链接
"""
import logging
import re
from typing import List, Set, Tuple
from urllib.parse import quote

from ..core.database import get_db

logger = logging.getLogger(__name__)


class BlogWikiProcessor:
    """Blog Wiki处理器，负责识别学校名称并生成超链接"""

    def __init__(self):
        self.university_names_cache = None
        self.university_names_zh_cache = None
        self._load_university_names()

    def _load_university_names(self):
        """从数据库加载所有大学名称到缓存"""
        try:
            db = get_db()
            if db is None:
                logger.error("无法连接到MongoDB，无法加载大学名称")
                # 初始化空缓存，避免后续检查出错
                self.university_names_cache = set()
                self.university_names_zh_cache = set()
                return

            # 获取所有大学名称
            universities = list(db.universities.find({}, {'university_name': 1, 'university_name_zh': 1}))

            # 构建缓存
            self.university_names_cache = set()
            self.university_names_zh_cache = set()

            for uni in universities:
                if uni.get('university_name'):
                    self.university_names_cache.add(uni['university_name'])
                if uni.get('university_name_zh'):
                    self.university_names_zh_cache.add(uni['university_name_zh'])

            logger.info(f"成功加载 {len(self.university_names_cache)} 个日文大学名称和 {len(self.university_names_zh_cache)} 个中文大学名称")

        except Exception as e:
            logger.error(f"加载大学名称时出错: {e}")
            # 初始化空缓存
            self.university_names_cache = set()
            self.university_names_zh_cache = set()

    def _find_existing_links(self, content: str) -> Set[str]:
        """查找内容中已存在的超链接，避免重复添加"""
        existing_links = set()

        # 匹配markdown超链接格式 [学校名称](链接)
        link_pattern = r'\[([^\]]+)\]\([^)]+\)'
        matches = re.findall(link_pattern, content)

        for match in matches:
            existing_links.add(match.strip())

        return existing_links

    def _find_university_matches(self, content: str) -> List[Tuple[str, str, int]]:
        """
        在blog内容中查找大学名称匹配
        
        返回:
            一个元组列表 (matched_text, university_name, start_pos)
        """
        if not self.university_names_cache or not self.university_names_zh_cache:
            logger.warning("大学名称缓存未加载，重新加载...")
            self._load_university_names()
            if not self.university_names_cache:
                return []

        matches = []

        # 查找日文大学名称
        for uni_name in self.university_names_cache:
            if uni_name in content:
                start_pos = content.find(uni_name)
                matches.append((uni_name, uni_name, start_pos))

        # 查找中文大学名称
        for uni_name_zh in self.university_names_zh_cache:
            if uni_name_zh in content:
                start_pos = content.find(uni_name_zh)
                matches.append((uni_name_zh, uni_name_zh, start_pos))

        # 按匹配文本长度降序排序，优先处理更长的匹配（更精确）
        matches.sort(key=lambda x: len(x[0]), reverse=True)

        return matches

    def _generate_markdown_link(self, university_name: str) -> str:
        """为大学名称生成markdown超链接"""
        # URL编码处理中文和日文字符
        encoded_name = quote(university_name)
        return f"[{university_name}](https://www.runjplib.com/university/{encoded_name})"

    def _replace_university_names(self, content: str, matches: List[Tuple[str, str, int]], existing_links: Set[str]) -> str:
        """
        替换大学名称为超链接
        
        参数:
            content: 原始blog内容
            matches: 大学名称匹配列表
            existing_links: 已存在的超链接集合
        
        返回:
            处理后的blog内容
        """
        # 从后往前替换，避免位置偏移问题
        matches.sort(key=lambda x: x[2], reverse=True)

        processed_content = content
        processed_positions = set()  # 记录已处理的位置，避免重复处理

        for matched_text, university_name, start_pos in matches:
            # 检查是否已经有超链接
            if matched_text in existing_links:
                logger.debug(f"跳过已有超链接的大学名称: {matched_text}")
                continue

            # 检查是否在已有超链接的范围内
            if self._is_in_existing_link(processed_content, start_pos):
                logger.debug(f"跳过已有超链接范围内的大学名称: {matched_text}")
                continue

            # 检查是否已经处理过这个位置
            if start_pos in processed_positions:
                logger.debug(f"跳过已处理位置的大学名称: {matched_text}")
                continue

            # 生成超链接
            markdown_link = self._generate_markdown_link(university_name)

            # 替换文本
            before = processed_content[:start_pos]
            after = processed_content[start_pos + len(matched_text):]
            processed_content = before + markdown_link + after

            # 记录已处理的位置
            processed_positions.add(start_pos)

            logger.info(f"为大学名称 '{matched_text}' 添加超链接")

        return processed_content

    def _is_in_existing_link(self, content: str, pos: int) -> bool:
        """检查指定位置是否在已有超链接的范围内"""
        # 向前查找最近的 '[' 和 ']'
        before_content = content[:pos]
        after_content = content[pos:]

        # 查找前面的 '[' 位置
        last_open_bracket = before_content.rfind('[')
        if last_open_bracket == -1:
            return False

        # 查找后面的 ']' 位置
        next_close_bracket = after_content.find(']')
        if next_close_bracket == -1:
            return False

        # 检查 '[' 和 ']' 之间是否有 '(' 和 ')'
        bracket_content = before_content[last_open_bracket:] + after_content[:next_close_bracket + 1]
        if '(' in bracket_content and ')' in bracket_content:
            return True

        return False

    def process_blog_content(self, content: str) -> str:
        """
        处理blog内容，自动添加大学名称超链接
        
        参数:
            content: 原始blog markdown内容
            
        返回:
            处理后的blog内容
        """
        try:
            logger.info("开始处理blog内容的wiki功能")

            # 查找已存在的超链接
            existing_links = self._find_existing_links(content)
            logger.info(f"发现 {len(existing_links)} 个已存在的超链接")

            # 查找大学名称匹配
            matches = self._find_university_matches(content)
            logger.info(f"发现 {len(matches)} 个大学名称匹配")

            if not matches:
                logger.info("未发现需要处理的大学名称")
                return content

            # 替换大学名称为超链接
            processed_content = self._replace_university_names(content, matches, existing_links)

            # 统计处理结果
            original_count = len(matches)
            processed_count = len([m for m in matches if m[0] not in existing_links])

            logger.info(f"Wiki处理完成: 原始匹配 {original_count} 个，实际处理 {processed_count} 个")

            return processed_content

        except Exception as e:
            logger.error(f"处理blog内容时出错: {e}")
            # 出错时返回原始内容，确保不影响正常保存
            return content

    def refresh_cache(self):
        """刷新大学名称缓存"""
        logger.info("刷新大学名称缓存")
        self._load_university_names()


# 全局实例
blog_wiki_processor = BlogWikiProcessor()
