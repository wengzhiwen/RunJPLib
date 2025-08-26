"""
处理首页和大学相关路由的模块 (纯MongoDB版本)
"""
from collections import defaultdict
import csv
from functools import lru_cache
import logging
import os
import re

from cachetools import cached
from flask import abort
from flask import make_response
from flask import render_template
import markdown

from utils.analytics import log_access
from utils.cache import TTLCache
from utils.mongo_client import get_mongo_client

from .blog import get_all_blogs as get_all_blogs_for_sitemap
from .blog import get_random_blogs_with_summary

# --- 缓存定义 ---
university_list_cache = TTLCache(maxsize=1, ttl=600)
categories_cache = TTLCache(maxsize=1, ttl=3600)

# --- 数据获取函数 (MongoDB) ---


@cached(university_list_cache)
def get_sorted_universities_for_index():
    """
    从MongoDB获取所有大学的列表，为首页和侧边栏展示。
    按 is_premium 和 deadline 降序排序。
    !!! 警告: 此查询的性能高度依赖于数据库索引。 !!!
    """
    logging.info("缓存未命中或过期，正在从MongoDB加载完整的大学列表...")
    client = get_mongo_client()
    if not client:
        return []
    db = client.RunJPLib

    try:
        # --- 关键修复点：移除 .limit(100) ---
        cursor = db.universities.find({}, {"university_name": 1, "deadline": 1, "is_premium": 1, "_id": 0}).sort([("is_premium", -1), ("deadline", -1)])

        universities = []
        for uni in cursor:
            # 增加健壮性检查，跳过没有名称的脏数据
            uni_name = uni.get('university_name')
            if not uni_name:
                continue

            universities.append({'name': uni_name, 'deadline': uni.get('deadline'), 'url': f"/university/{uni_name}"})

        logging.info(f"成功为首页加载了 {len(universities)} 所大学。")
        return universities
    except Exception as e:
        logging.error(f"为首页加载大学列表时出错: {e}", exc_info=True)
        return []


@cached(categories_cache)
def load_categories():
    """
    加载大学分类信息。
    """
    logging.info("缓存未命中或过期，正在从CSV加载分类信息...")
    categories = defaultdict(list)
    try:
        # 为了性能，不再每次都去数据库检查文件是否存在
        with open('data/university_categories.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                required_fields = ['category', 'name', 'ja_name', 'short_name']
                if not all(row.get(field) for field in required_fields):
                    continue

                categories[row['category']].append({
                    'name': row['name'],
                    'ja_name': row['ja_name'],
                    'short_name': row['short_name'],
                    'url': "/university/" + row['ja_name'],
                    'file_exists': True
                })
        return categories
    except Exception as e:
        logging.error(f"加载分类信息时出错: {e}", exc_info=True)
        return defaultdict(list)


def get_university_details(name, deadline=None):
    """
    从MongoDB获取大学的详细信息。
    """
    logging.info(f"从MongoDB获取大学详情: name='{name}', deadline='{deadline}'")
    client = get_mongo_client()
    if not client:
        return None
    db = client.RunJPLib

    query = {"university_name": name}
    if deadline:
        formatted_deadline = deadline.replace('-', '').replace('/', '')
        if len(formatted_deadline) == 8 and formatted_deadline.isdigit():
            query["deadline"] = formatted_deadline
        else:
            return None

    sort_order = [("deadline", -1)] if not deadline else None

    try:
        doc = db.universities.find_one(query, sort=sort_order)
        if doc:
            logging.info(f"成功找到大学: {doc['university_name']} ({doc['deadline']})")
        else:
            logging.warning(f"在MongoDB中未找到大学: {query}")
        return doc
    except Exception as e:
        logging.error(f"查询大学详情时出错: {e}", exc_info=True)
        return None


# --- 路由处理函数 ---


def index_route():
    """首页路由"""
    universities = get_sorted_universities_for_index()
    categories = load_categories()
    recommended_blogs = get_random_blogs_with_summary(3)
    return render_template("index.html", universities=universities, categories=categories, recommended_blogs=recommended_blogs, mode='index')


def university_route(name, deadline=None, content="REPORT"):
    """大学详情页路由处理函数 (纯MongoDB)"""
    log_access('university')
    university_doc = get_university_details(name, deadline)

    if not university_doc:
        abort(404)

    try:
        md = markdown.Markdown(
            extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'],
            output_format="html5",
        )

        raw_deadline = university_doc.get('deadline', '')
        current_deadline_formatted = f"{raw_deadline[:4]}-{raw_deadline[4:6]}-{raw_deadline[6:]}" if len(raw_deadline) == 8 else raw_deadline

        universities_for_sidebar = get_sorted_universities_for_index()

        template_vars = {
            "universities": universities_for_sidebar,
            "current_university": university_doc['university_name'],
            "current_deadline": current_deadline_formatted,
        }

        content_data = university_doc.get('content', {})
        if content == "REPORT":
            html_content = md.convert(content_data.get('report_md', ''))
            template_vars["content"] = html_content
            return render_template("content_report.html", **template_vars)

        elif content == "ORIGINAL":
            html_content = md.convert(content_data.get('original_md', ''))
            chinese_html_content = md.convert(content_data.get('translated_md', ''))
            pdf_url = f"/pdf/resource/{str(university_doc['_id'])}"
            template_vars.update({"content": html_content, "chinese_content": chinese_html_content, "pdf_url": pdf_url})
            return render_template("content_original.html", **template_vars)

        else:  # content == "ZH"
            html_content = md.convert(content_data.get('translated_md', ''))
            template_vars["content"] = html_content
            return render_template("content.html", **template_vars)

    except Exception as e:
        logging.error(f"渲染大学页面时出错: {e}", exc_info=True)
        abort(500)


def sitemap_route():
    """sitemap路由处理函数"""
    base_url = os.getenv('BASE_URL', 'https://www.runjplib.com')
    client = get_mongo_client()
    all_universities_for_sitemap = []
    if client:
        try:
            pipeline = [{
                "$sort": {
                    "deadline": -1
                }
            }, {
                "$group": {
                    "_id": "$university_name",
                    "latest_deadline": {
                        "$first": "$deadline"
                    }
                }
            }, {
                "$project": {
                    "name": "$_id",
                    "deadline": "$latest_deadline",
                    "_id": 0
                }
            }]
            all_universities_for_sitemap = list(client.RunJPLib.universities.aggregate(pipeline))
        except Exception as e:
            logging.error(f"为站点地图生成大学列表时出错: {e}")

    response = make_response(render_template('sitemap.xml', base_url=base_url, blogs=get_all_blogs_for_sitemap(), universities=all_universities_for_sitemap))
    response.headers["Content-Type"] = "application/xml"
    return response
