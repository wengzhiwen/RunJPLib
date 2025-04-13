"""
博客路由模块
"""
import glob
import os
import re
from datetime import datetime
import random
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import time
import logging

import markdown
from flask import render_template

# 缓存更新间隔（秒）
CACHE_UPDATE_INTERVAL = 60


class BlogCache:
    """博客缓存管理类"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.last_check_time = 0
            self.files_hash = None
            self.blogs_list = None
            self.content_cache = {}
            self.initialized = True

    @classmethod
    def get_instance(cls):
        """获取BlogCache单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def should_update(self) -> bool:
        """检查是否需要更新缓存"""
        current_time = time.time()
        if current_time - self.last_check_time > CACHE_UPDATE_INTERVAL:
            new_hash = self._calculate_files_hash()
            if new_hash != self.files_hash:
                logging.info("博客缓存需要更新：文件哈希值已改变 (old: %s, new: %s)", self.files_hash, new_hash)
                self.files_hash = new_hash
                return True
            logging.info("博客缓存检查完成：文件未发生变化")
        return False

    def _calculate_files_hash(self) -> str:
        """计算所有博客文件的哈希值"""
        hash_str = ""
        try:
            # 首先将目录中所有文件名加入哈希计算
            all_files = sorted(glob.glob('blogs/*.md'))
            logging.info("正在计算博客文件哈希值，共发现 %d 个文件", len(all_files))
            hash_str += ";".join(all_files) + ";"

            # 然后加入每个文件的修改时间
            for file in all_files:
                hash_str += f"{file}:{os.path.getmtime(file)};"
        except OSError as e:
            logging.error("计算博客文件哈希值时发生错误: %s", str(e))
        return hashlib.md5(hash_str.encode()).hexdigest()

    def get_content(self, blog_id: str) -> dict:
        """获取博客内容，优先从缓存获取"""
        if blog_id in self.content_cache:
            logging.info("从缓存获取博客内容: %s", blog_id)
            return self.content_cache[blog_id]

        logging.info("缓存未命中，从文件加载博客内容: %s", blog_id)
        content = self._load_content(blog_id)
        if content:
            self.content_cache[blog_id] = content
        return content

    def _load_content(self, blog_id: str) -> dict:
        """从文件加载博客内容"""
        file_path = f'blogs/{blog_id}.md'
        if not os.path.exists(file_path) or not os.path.getsize(file_path):
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                md_content = f.read()

            md = markdown.Markdown(
                extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'],
                output_format="html5",
            )
            html_content = md.convert(md_content)

            return {'content': html_content, 'text_content': re.sub(r'<[^>]+>', '', html_content)}
        except Exception:
            return None

    def clear(self):
        """清除所有缓存"""
        logging.info("清除所有博客缓存")
        self.blogs_list = None
        self.content_cache.clear()
        self.last_check_time = 0


def get_title_similarity(title1, title2):
    """计算两个标题的相似度"""
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio()


def get_all_blogs():
    """获取所有博客列表"""
    cache = BlogCache.get_instance()

    # 检查是否需要更新缓存
    if cache.blogs_list is None or cache.should_update():
        blogs = []
        blog_files = glob.glob('blogs/*.md')

        for file in blog_files:
            filename = os.path.basename(file)
            if not os.path.getsize(file):
                continue

            match = re.match(r'(.+)_(\d{14})\.md$', filename)
            if not match:
                continue

            title = match.group(1)
            date_str = match.group(2)
            date = datetime.strptime(date_str, '%Y%m%d%H%M%S')

            blogs.append({
                'id': filename[:-3],
                'title': title,
                'url_title': title.replace(' ', '-').lower(),
                'date': date.strftime('%Y-%m-%d'),
                'datetime': date,
                'md_path': file
            })

        # 按日期降序排序
        blogs = sorted(blogs, key=lambda x: x['datetime'], reverse=True)

        # 对于相同标题的文章，只保留最新的一篇
        unique_blogs = {}
        for blog in blogs:
            if blog['title'] not in unique_blogs:
                unique_blogs[blog['title']] = blog

        cache.blogs_list = list(unique_blogs.values())
        cache.last_check_time = time.time()

    return cache.blogs_list


def get_blog_by_id(blog_id):
    """获取特定博客内容"""
    file_path = f'blogs/{blog_id}.md'
    if not os.path.exists(file_path) or not os.path.getsize(file_path):
        return None

    match = re.match(r'(.+)_(\d{14})$', blog_id)
    if not match:
        return None

    title = match.group(1)
    date_str = match.group(2)
    date = datetime.strptime(date_str, '%Y%m%d%H%M%S')

    # 从缓存获取内容
    content_data = BlogCache.get_instance().get_content(blog_id)
    if not content_data:
        return None

    return {'id': blog_id, 'title': title, 'url_title': title.replace(' ', '-').lower(), 'date': date.strftime('%Y-%m-%d'), 'content': content_data['content']}


@lru_cache(maxsize=20, typed=False)
def find_blog_by_title(url_title):
    """根据URL友好的标题查找博客"""
    # 强制重新检查文件系统状态
    BlogCache.get_instance().should_update()

    all_blogs = get_all_blogs()

    # 首先尝试精确匹配
    for blog in all_blogs:
        if blog['url_title'] == url_title:
            return get_blog_by_id(blog['id'])

    # 如果没有精确匹配，尝试模糊匹配
    best_match = None
    highest_similarity = 0.7  # 设置相似度阈值

    for blog in all_blogs:
        similarity = get_title_similarity(url_title.replace('-', ' '), blog['title'])
        if similarity > highest_similarity:
            highest_similarity = similarity
            best_match = blog

    if best_match:
        return get_blog_by_id(best_match['id'])

    return None


def get_random_blogs(n=10):
    """获取n篇随机博客"""
    all_blogs = get_all_blogs()
    return random.sample(all_blogs, min(n, len(all_blogs)))


def get_random_blogs_with_summary(count=3):
    """获取指定数量的随机博客，并生成摘要"""
    all_blogs = get_all_blogs()
    if not all_blogs:
        return []

    selected_blogs = random.sample(all_blogs, min(count, len(all_blogs)))

    result = []
    for blog in selected_blogs:
        # 从缓存获取内容
        content_data = BlogCache.get_instance().get_content(blog['id'])
        if not content_data:
            continue

        # 生成摘要
        summary = content_data['text_content'][:100].strip() + '...' if len(content_data['text_content']) > 100 else content_data['text_content']

        result.append({'id': blog['id'], 'title': blog['title'], 'url_title': blog['url_title'], 'summary': summary})

    return result


def blog_list_route():
    """博客列表路由处理函数"""
    blogs = get_all_blogs()

    # 如果有博客文章，随机选择一篇作为默认显示
    if blogs:
        random_blog = random.choice(blogs)
        return blog_detail_route(random_blog['url_title'])

    # 如果没有博客文章，显示404页面并推荐其他博客
    recommended_blogs = get_random_blogs(10)
    return render_template('404.html', mode='blog', blogs=blogs, recommended_blogs=recommended_blogs), 404


def blog_detail_route(url_title):
    """博客详情路由处理函数"""
    blog = find_blog_by_title(url_title)
    if blog is None:
        # 获取10篇随机推荐的博客
        recommended_blogs = get_random_blogs(10)
        return render_template('404.html', mode='blog', blogs=get_all_blogs(), recommended_blogs=recommended_blogs), 404

    return render_template(
        'content.html',
        mode='blog',
        blogs=get_all_blogs(),
        blog=blog,
        content=blog['content']
    )
