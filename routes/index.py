"""
处理首页和大学相关路由的模块。
"""
import os
import csv
import re
import logging
from collections import defaultdict
from functools import lru_cache
import hashlib
import time

import markdown
from flask import render_template, make_response, send_file, abort
from utils.mongo_client import get_mongo_client

from .blog import get_all_blogs, get_random_blogs_with_summary

# 缓存更新间隔（秒）
CACHE_UPDATE_INTERVAL = 60


class University:
    # pylint: disable=too-few-public-methods
    """大学信息类"""

    def __init__(self, name, deadline, zh_md_path, md_path, report_md_path, pdf_path):
        self.name = name
        self.deadline = deadline
        self.zh_md_path = zh_md_path
        self.md_path = md_path
        self.report_md_path = report_md_path
        self.url = f"/university/{name}"  # 添加url属性
        self.pdf_path = pdf_path


class UniversityCache:
    """大学信息缓存管理类"""

    def __init__(self):
        self.last_check_time = 0
        self.files_hash = None
        self._universities = None
        self._sorted_universities = None
        self._latest_by_name = {}

    def should_update(self) -> bool:
        """检查是否需要更新缓存"""
        current_time = time.time()
        if current_time - self.last_check_time > CACHE_UPDATE_INTERVAL:
            new_hash = self._calculate_files_hash()
            if new_hash != self.files_hash:
                logging.info("大学信息缓存需要更新：文件哈希值已改变 (old: %s, new: %s)", self.files_hash, new_hash)
                self.files_hash = new_hash
                return True
            logging.info("大学信息缓存检查完成：文件未发生变化")
        return False

    def _calculate_files_hash(self) -> str:
        """计算所有大学文件的哈希值"""
        hash_str = ""
        base_dir = os.getenv("CONTENT_BASE_DIR", ".")
        pdf_dirs = [d for d in os.listdir(base_dir) if d.startswith("pdf_with_md")]

        logging.info("正在计算大学文件哈希值，发现 %d 个pdf_with_md目录", len(pdf_dirs))
        # 首先将所有pdf_with_md目录名加入哈希计算
        hash_str += ";".join(sorted(pdf_dirs)) + ";"

        for pdf_dir in pdf_dirs:
            try:
                for root, dirs, files in os.walk(pdf_dir):
                    # 将目录结构信息加入哈希计算
                    hash_str += f"dir:{root}:{','.join(sorted(dirs))};"
                    md_files = [f for f in sorted(files) if f.endswith('.md')]
                    logging.debug("在目录 %s 中发现 %d 个markdown文件", root, len(md_files))
                    for file in md_files:
                        full_path = os.path.join(root, file)
                        hash_str += f"file:{full_path}:{os.path.getmtime(full_path)};"
            except OSError as e:
                logging.error("计算大学文件哈希值时发生错误 (目录: %s): %s", pdf_dir, str(e))
                continue
        return hashlib.md5(hash_str.encode()).hexdigest()

    def get_all_universities(self) -> list[University]:
        """获取所有大学信息"""
        if self._universities is None or self.should_update():
            logging.info("重新加载所有大学信息")
            self._universities = self._load_universities()
            self._sorted_universities = None  # 清除排序缓存
            self._latest_by_name.clear()  # 清除最新信息缓存
            self.last_check_time = time.time()
        return self._universities

    def get_sorted_universities(self) -> list[University]:
        """获取排序后的大学列表"""
        if self._sorted_universities is None:
            logging.info("重新生成排序后的大学列表")
            universities = self.get_all_universities()
            # 获取优质大学列表
            best_universities = set()
            base_dir = os.getenv("CONTENT_BASE_DIR", ".")
            pdf_dirs = [d for d in os.listdir(base_dir) if d.startswith("pdf_with_md")]

            for pdf_dir in pdf_dirs:
                best_list_path = os.path.join(pdf_dir, "best_list.csv")
                if os.path.exists(best_list_path):
                    with open(best_list_path, "r", encoding="utf-8") as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if row:
                                best_universities.add(row[0])

            # 排序函数
            def get_sort_key(univ: University):
                is_best = 1 if univ.name in best_universities else 0
                return (is_best, univ.deadline)

            self._sorted_universities = sorted(universities, key=get_sort_key, reverse=True)

        return self._sorted_universities

    def get_latest_by_name(self, name: str) -> University | None:
        """获取指定大学最新的信息"""
        if name not in self._latest_by_name:
            universities = self.get_all_universities()
            matching = [u for u in universities if u.name == name]
            if matching:
                self._latest_by_name[name] = max(matching, key=lambda x: x.deadline)
                logging.debug("找到大学 %s 的最新信息，截止日期为 %s", name, self._latest_by_name[name].deadline)
            else:
                logging.debug("未找到大学 %s 的信息", name)
                self._latest_by_name[name] = None
        return self._latest_by_name[name]

    def _load_universities(self) -> list[University]:
        """从文件系统加载大学信息"""
        universities = []
        base_dir = os.getenv("CONTENT_BASE_DIR", ".")
        pdf_dirs = [d for d in os.listdir(base_dir) if d.startswith("pdf_with_md")]

        for pdf_dir in pdf_dirs:
            sub_dirs = [d for d in os.listdir(pdf_dir) if os.path.isdir(os.path.join(pdf_dir, d))]
            for sub_dir in sub_dirs:
                sub_dir_name = sub_dir.split("_")
                if len(sub_dir_name) < 2:
                    logging.info("忽略子文件夹: %s 。文件夹名不含有\"_\"", sub_dir)
                    continue

                university_name = sub_dir_name[0]
                deadline = sub_dir_name[1]

                if len(deadline) == 8 and deadline.isdigit():
                    deadline = f"{deadline[:4]}-{deadline[4:6]}-{deadline[6:]}"
                elif len(deadline) == 10:
                    deadline = deadline.replace("/", "-")
                    if not re.match(r"\d{4}-\d{2}-\d{2}", deadline):
                        logging.info("忽略子文件夹: %s。无法解析的报名截止日", sub_dir)
                        continue
                else:
                    logging.info("忽略子文件夹: %s。无法解析的报名截止日", sub_dir)
                    continue

                # 检查必要文件
                required_files = [f"{sub_dir}.md", f"{sub_dir}_report.md", f"{sub_dir}_中文.md"]
                if not all(os.path.exists(os.path.join(pdf_dir, sub_dir, f)) for f in required_files):
                    logging.info("忽略子文件夹: %s。缺少必要文件", sub_dir)
                    continue

                # 检查是否存在一个pdf文件，如果有多个取第一个
                pdf_files = [f for f in os.listdir(os.path.join(pdf_dir, sub_dir)) if f.endswith('.pdf')]
                if len(pdf_files) == 0:
                    logging.info("忽略子文件夹: %s。没有pdf文件", sub_dir)
                    continue
                else:
                    pdf_file = pdf_files[0]

                is_updated = False
                # 确认在universitis中是否有重名的大学
                for university in universities:
                    if university.name == university_name:
                        # 比较deadline，如果当前的deadline更新，则更新university
                        logging.debug("比较大学 %s 的deadline，旧的deadline为 %s，新的deadline为 %s", university.name, university.deadline, deadline)
                        if university.deadline < deadline:
                            logging.debug("更新大学 %s 的deadline为 %s", university.name, deadline)
                            university.deadline = deadline
                            university.zh_md_path = os.path.join(pdf_dir, sub_dir, f"{sub_dir}_中文.md")
                            university.md_path = os.path.join(pdf_dir, sub_dir, f"{sub_dir}.md")
                            university.report_md_path = os.path.join(pdf_dir, sub_dir, f"{sub_dir}_report.md")
                            university.pdf_path = os.path.join(pdf_dir, sub_dir, pdf_file)
                            is_updated = True
                            break

                if is_updated:
                    logging.debug("大学 %s 已存在，更新deadline为 %s", university_name, deadline)
                    continue

                universities.append(
                    University(
                        name=university_name,
                        deadline=deadline,
                        zh_md_path=os.path.join(pdf_dir, sub_dir, f"{sub_dir}_中文.md"),
                        md_path=os.path.join(pdf_dir, sub_dir, f"{sub_dir}.md"),
                        report_md_path=os.path.join(pdf_dir, sub_dir, f"{sub_dir}_report.md"),
                        pdf_path=os.path.join(pdf_dir, sub_dir, pdf_file),
                    ))

        return universities

    def clear(self):
        """清除所有缓存"""
        logging.info("清除所有大学信息缓存")
        self._universities = None
        self._sorted_universities = None
        self._latest_by_name.clear()
        self.last_check_time = 0
        self.files_hash = None


# 创建全局缓存实例
_university_cache = UniversityCache()


def get_all_universities() -> list[University]:
    """获取所有大学列表"""
    return _university_cache.get_all_universities()


def get_sorted_universities() -> list[University]:
    """获取排序后的大学列表"""
    return _university_cache.get_sorted_universities()


def get_latest_university_by_name(name: str) -> University | None:
    """获取指定大学最新的信息"""
    return _university_cache.get_latest_by_name(name)


@lru_cache(maxsize=1, typed=False)
def load_categories() -> defaultdict:
    """
    加载大学分类信息，并根据实际文件存在情况标记链接状态
    
    :return: 包含分类信息的defaultdict
    """
    logging.debug("####load_categories####")
    categories = defaultdict(list)

    try:
        with open('data/university_categories.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 检查必要字段是否存在且不为空
                required_fields = ['category', 'name', 'ja_name', 'short_name']
                if not all(row.get(field) for field in required_fields):
                    missing_fields = [field for field in required_fields if not row.get(field)]
                    logging.warning("CSV行缺少必要字段: %s", missing_fields)
                    continue

                # 使用 get_latest_university_by_name 检查
                file_exists = get_latest_university_by_name(row['ja_name']) is not None

                categories[row['category']].append({
                    'name': row['name'],
                    'ja_name': row['ja_name'],
                    'short_name': row['short_name'],
                    'url': "/university/" + row['ja_name'],
                    'file_exists': file_exists
                })
    except FileNotFoundError as e:
        logging.error("找不到大学分类数据文件: %s", e)
    except PermissionError as e:
        logging.error("没有权限访问大学分类数据文件: %s", e)
    except UnicodeDecodeError as e:
        logging.error("大学分类数据文件编码错误: %s", e)
    except csv.Error as e:
        logging.error("大学分类数据CSV格式错误: %s", e)
    except IOError as e:
        logging.error("读取大学分类数据时发生IO错误: %s", e)
    return categories


def index_route():
    """首页路由"""
    universities = get_sorted_universities()
    categories = load_categories()
    recommended_blogs = get_random_blogs_with_summary(3)
    return render_template("index.html", universities=universities, categories=categories, recommended_blogs=recommended_blogs, mode='index')


def get_university_by_name_and_deadline(name, deadline=None) -> University | None:
    """
    根据大学名称和报名截止日期获取信息

    :param name: 大学名称
    :param deadline: 报名截止日期（YYYY-MM-DD / YYYYMMDD / YYYY/MM/DD）
    :return: 大学信息
    """
    # 如果没有提供deadline，返回最新的大学信息
    if deadline is None:
        return get_latest_university_by_name(name)

    # 对报名截止日期进行格式化
    # 如果报名截止日是一串8位数字，则认为它是YYYYMMDD格式，需要转换为YYYY/MM/DD格式
    if len(deadline) == 8 and deadline.isdigit():
        deadline = f"{deadline[:4]}-{deadline[4:6]}-{deadline[6:]}"
    # 如果报名截止日是YYYY/MM/DD格式或YYYY-MM-DD格式，为了保证显示效果，需要统一为YYYY-MM-DD格式
    elif len(deadline) == 10:
        deadline = deadline.replace("/", "-")
        # 检查格式是否正确
        if not re.match(r"\d{4}-\d{2}-\d{2}", deadline):
            logging.info("无法解析的报名截止日：%s", deadline)
            return None
    else:
        logging.info("无法解析的报名截止日：%s", deadline)
        return None

    # 获取所有大学的信息
    universities = get_all_universities()

    # 根据大学名称和报名截止日期获取信息
    for university in universities:
        if university.name == name and university.deadline == deadline:
            return university

    return None


def get_university_from_mongo(name, deadline=None):
    """
    Gets university details from MongoDB.
    If deadline is provided, it finds the exact match.
    If not, it finds the latest one for the given university name.
    """
    client = get_mongo_client()
    if not client:
        return None
    db = client.RunJPLib

    query = {"university_name": name}
    if deadline:
        # Deadline can be YYYY-MM-DD or YYYYMMDD, mongo stores YYYYMMDD
        query["deadline"] = deadline.replace('-', '').replace('/', '')

    # Find one and sort by deadline descending to get the latest if no deadline is specified
    doc = db.universities.find_one(query, sort=[("deadline", -1)])
    return doc


def university_route(name, deadline=None, content="REPORT"):
    """大学详情页路由处理函数"""
    debug_file_path = None
    # Try fetching from MongoDB first
    university_doc = get_university_from_mongo(name, deadline)

    # I noticed a bug in my previous implementation. The content keys were wrong.
    # Correct keys are: original_md, translated_md, report_md
    if university_doc:
        # We have data from Mongo, use it
        try:
            md = markdown.Markdown(
                extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'],
                output_format="html5",
            )

            current_deadline_formatted = f"{university_doc['deadline'][:4]}-{university_doc['deadline'][4:6]}-{university_doc['deadline'][6:]}"

            if content == "REPORT":
                html_content = md.convert(university_doc['content'].get('report_md', ''))
                template = "content_report.html"
                return render_template(template,
                                       universities=get_sorted_universities(),
                                       content=html_content,
                                       current_university=university_doc['university_name'],
                                       current_deadline=current_deadline_formatted,
                                       debug_file_path=None)  # Explicitly None for Mongo data

            elif content == "ORIGINAL":
                html_content = md.convert(university_doc['content'].get('original_md', ''))
                chinese_html_content = md.convert(university_doc['content'].get('translated_md', ''))
                pdf_url = f"/pdf/resource/{str(university_doc['_id'])}"
                template = "content_original.html"
                return render_template(template,
                                       universities=get_sorted_universities(),
                                       content=html_content,
                                       chinese_content=chinese_html_content,
                                       pdf_url=pdf_url,
                                       current_university=university_doc['university_name'],
                                       current_deadline=current_deadline_formatted,
                                       debug_file_path=None)

            else:  # content == "ZH"
                html_content = md.convert(university_doc['content'].get('translated_md', ''))
                template = "content.html"
                return render_template(template,
                                       universities=get_sorted_universities(),
                                       content=html_content,
                                       current_university=university_doc['university_name'],
                                       current_deadline=current_deadline_formatted,
                                       debug_file_path=None)

        except Exception as e:
            logging.error(f"处理来自 MongoDB 的大学数据时出错: {e}")
            return render_template("404.html", universities=get_sorted_universities()), 500

    # Fallback to the old file-based method if not found in Mongo
    logging.warning(f"在 MongoDB 中未找到大学 '{name}' (截止日期: '{deadline}'), 回退到文件系统。")
    university = get_university_by_name_and_deadline(name, deadline)
    if not university:
        return render_template("404.html", universities=get_sorted_universities()), 404

    try:
        md = markdown.Markdown(
            extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'],
            output_format="html5",
        )

        if content == "REPORT":
            if os.getenv('LOG_LEVEL') == 'DEBUG':
                debug_file_path = university.report_md_path
            with open(university.report_md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            html_content = md.convert(md_content)
            template = "content_report.html"
            return render_template(template,
                                   universities=get_sorted_universities(),
                                   content=html_content,
                                   current_university=university.name,
                                   current_deadline=university.deadline,
                                   debug_file_path=debug_file_path)

        elif content == "ORIGINAL":
            if os.getenv('LOG_LEVEL') == 'DEBUG':
                debug_file_path = university.md_path
            with open(university.md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            html_content = md.convert(md_content)

            with open(university.zh_md_path, 'r', encoding='utf-8') as f:
                zh_md_content = f.read()
            chinese_html_content = md.convert(zh_md_content)

            pdf_url = f"/pdf/{university.name}/{university.deadline}"
            template = "content_original.html"
            return render_template(template,
                                   universities=get_sorted_universities(),
                                   content=html_content,
                                   chinese_content=chinese_html_content,
                                   pdf_url=pdf_url,
                                   current_university=university.name,
                                   current_deadline=university.deadline,
                                   debug_file_path=debug_file_path)

        else:  # content == "ZH"
            if os.getenv('LOG_LEVEL') == 'DEBUG':
                debug_file_path = university.zh_md_path
            with open(university.zh_md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            html_content = md.convert(md_content)
            template = "content.html"
            return render_template(template,
                                   universities=get_sorted_universities(),
                                   content=html_content,
                                   current_university=university.name,
                                   current_deadline=university.deadline,
                                   debug_file_path=debug_file_path)

    except FileNotFoundError:
        return render_template("404.html", universities=get_sorted_universities()), 404


def serve_pdf(name, deadline):
    """提供PDF文件服务"""
    university = get_university_by_name_and_deadline(name, deadline)
    if not university or not university.pdf_path:
        abort(404)

    if not os.path.exists(university.pdf_path):
        abort(404)

    # 使用安全的文件名，避免中文字符编码问题
    safe_filename = f"university_{name}_{deadline}.pdf"
    
    return send_file(
        university.pdf_path, 
        as_attachment=False, 
        mimetype='application/pdf',
        download_name=safe_filename
    )


def sitemap_route():
    """sitemap路由处理函数"""
    base_url = os.getenv('BASE_URL', 'https://www.runjplib.com')
    response = make_response(render_template('sitemap.xml', base_url=base_url, blogs=get_all_blogs(), universities=get_all_universities()))
    response.headers["Content-Type"] = "application/xml"
    return response
