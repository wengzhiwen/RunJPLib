"""
处理首页和大学相关路由的模块 (纯MongoDB版本)
"""
from collections import defaultdict
import csv
from datetime import datetime
import logging
import os

from cachetools import cached
from flask import abort
from flask import make_response
from flask import render_template
import markdown

from utils.analytics import log_access
from utils.cache import TTLCache
from utils.mongo_client import get_db

from .blog.views import get_all_blogs as get_all_blogs_for_sitemap
from .blog.views import get_weighted_recommended_blogs_with_summary

# --- 缓存定义 ---
university_list_cache = TTLCache(maxsize=1, ttl=600)
latest_updates_cache = TTLCache(maxsize=1, ttl=600)  # 为最新更新单独设置缓存
categories_cache = TTLCache(maxsize=1, ttl=3600)

# --- 数据获取函数 (MongoDB) ---


@cached(latest_updates_cache)
def get_latest_updates():
    """
    从MongoDB获取最新的15条大学更新记录。
    """
    logging.info("缓存未命中或过期，正在从MongoDB加载最新的15条大学更新...")
    db = get_db()
    if db is None:
        return []

    try:
        # 按文档创建时间（_id）降序排序，获取最新的15条
        cursor = db.universities.find({}, {"university_name": 1, "deadline": 1, "is_premium": 1, "_id": 0}).sort("_id", -1).limit(15)

        updates = []
        for doc in cursor:
            deadline_obj = doc.get('deadline')
            deadline_str = deadline_obj.strftime('%Y-%m-%d') if isinstance(deadline_obj, datetime) else 'N/A'
            updates.append({
                'name': doc.get('university_name'),
                'deadline': deadline_str,
                'is_premium': doc.get('is_premium', False),
                'url': f"/university/{doc.get('university_name')}"
            })
        logging.info(f"成功加载了 {len(updates)} 条最新更新。")
        return updates
    except Exception as e:
        logging.error(f"加载最新大学更新时出错: {e}", exc_info=True)
        return []


@cached(university_list_cache)
def get_sorted_universities_for_index():
    """
    从MongoDB获取所有大学的列表，并进行去重，为首页和侧边栏展示。
    使用聚合管道确保每个大学只返回其最新的记录，然后按 is_premium 和 deadline 降序排序。
    """
    logging.info("缓存未命中或过期，正在从MongoDB加载去重和排序后的大学列表...")
    db = get_db()
    if db is None:
        return []

    try:
        pipeline = [
            # 1. 按 premium 和 deadline 排序，确保每个分组的第一个文档是最新的
            {
                "$sort": {
                    "is_premium": -1,
                    "deadline": -1
                }
            },
            # 2. 按 university_name 分组，并获取第一个文档的 deadline 和 is_premium
            {
                "$group": {
                    "_id": "$university_name",
                    "deadline": {
                        "$first": "$deadline"
                    },
                    "is_premium": {
                        "$first": "$is_premium"
                    }
                }
            },
            # 3. 对去重后的结果再次排序
            {
                "$sort": {
                    "is_premium": -1,
                    "deadline": -1
                }
            },
            # 4. 投影，将 _id 重命名为 university_name
            {
                "$project": {
                    "university_name": "$_id",
                    "deadline": 1,
                    "is_premium": 1,
                    "_id": 0
                }
            }
        ]
        cursor = db.universities.aggregate(pipeline)

        universities = []
        for uni in cursor:
            uni_name = uni.get('university_name')
            if not uni_name:
                continue
            deadline_obj = uni.get('deadline')
            deadline_str = deadline_obj.strftime('%Y-%m-%d') if isinstance(deadline_obj, datetime) else 'N/A'
            universities.append({'name': uni_name, 'deadline': deadline_str, 'url': f"/university/{uni_name}"})

        logging.info(f"成功为首页加载了 {len(universities)} 所唯一的大学。")
        return universities
    except Exception as e:
        logging.error(f"为首页加载大学列表时出错: {e}", exc_info=True)
        return []


@cached(categories_cache)
def load_categories():
    """
    加载大学分类信息。
    对于“主要国公立”和“主要私立”，按地区进行分组。
    """
    logging.info("缓存未命中或过期，正在从CSV加载分类信息...")
    categories = defaultdict(list)
    area_order = ['関東', '関西', '中部', '東北', 'その他']  # 定义地区排序
    try:
        with open('data/university_categories.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                required_fields = ['category', 'name', 'ja_name', 'short_name', 'area']
                if not all(row.get(field) for field in required_fields):
                    continue

                categories[row['category']].append({
                    'name': row['name'],
                    'ja_name': row['ja_name'],
                    'short_name': row['short_name'],
                    'url': "/university/" + row['ja_name'],
                    'file_exists': True,
                    'area': row['area']
                })

        # 对特定分类进行按地区分组
        grouped_categories = {}
        for category, universities in categories.items():
            if category in ["主要国公立", "主要私立"]:
                grouped_by_area = defaultdict(list)
                for uni in universities:
                    grouped_by_area[uni['area']].append(uni)

                # 按自定义顺序对地区进行排序
                sorted_grouped = sorted(grouped_by_area.items(), key=lambda item: area_order.index(item[0]) if item[0] in area_order else len(area_order))
                grouped_categories[category] = dict(sorted_grouped)
            else:
                grouped_categories[category] = universities

        return grouped_categories
    except Exception as e:
        logging.error(f"加载分类信息时出错: {e}", exc_info=True)
        return defaultdict(list)


def get_university_details(name, deadline=None):
    """
    从MongoDB获取大学的详细信息。
    """
    logging.debug(f"从MongoDB获取大学详情: name='{name}', deadline='{deadline}'")
    db = get_db()
    if db is None:
        return None

    query_primary = {"university_name": name}
    if deadline:
        try:
            # 将 YYYY-MM-DD 格式的字符串转换为 datetime 对象
            dt = datetime.strptime(deadline, "%Y-%m-%d")
            query_primary["deadline"] = dt
        except (ValueError, TypeError):
            # 如果格式不正确或 deadline 不是字符串，则忽略该条件
            logging.warning(f"无效的 deadline 格式: '{deadline}'，查询时将忽略。")

    # 如果没有指定 deadline，则按 deadline 降序排序获取最新的一个
    sort_order = [("deadline", -1)] if not deadline else None

    try:
        # 1) 先按 university_name 匹配
        doc = db.universities.find_one(query_primary, sort=sort_order)
        if not doc:
            # 2) 未命中则按 university_name_zh 回退匹配
            query_fallback = {"university_name_zh": name}
            if deadline and isinstance(query_primary.get("deadline"), datetime):
                query_fallback["deadline"] = query_primary["deadline"]
            doc = db.universities.find_one(query_fallback, sort=sort_order)
            if not doc:
                logging.warning(f"在MongoDB中未找到大学: {query_primary} 或 {query_fallback}")

        if doc:
            deadline_val = doc.get('deadline')
            uni_log_name = doc.get('university_name') or doc.get('university_name_zh') or name
            if deadline_val and isinstance(deadline_val, datetime):
                logging.info(f"成功找到大学: {uni_log_name} ({deadline_val.strftime('%Y-%m-%d')})")
            else:
                logging.info(f"成功找到大学: {uni_log_name} (deadline: {deadline_val})")
        return doc
    except Exception as e:
        logging.error(f"查询大学详情时出错: {e}", exc_info=True)
        return None


# --- 路由处理函数 ---


def index_route():
    """首页路由"""
    universities = get_sorted_universities_for_index()
    categories = load_categories()
    recommended_blogs = get_weighted_recommended_blogs_with_summary(3)
    latest_updates = get_latest_updates()
    return render_template("index.html",
                           universities=universities,
                           categories=categories,
                           recommended_blogs=recommended_blogs,
                           latest_updates=latest_updates,
                           mode='index')


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

        deadline_obj = university_doc.get('deadline')
        current_deadline_formatted = deadline_obj.strftime('%Y-%m-%d') if isinstance(deadline_obj, datetime) else 'N/A'

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

        else:  # 默认处理 "ZH" (中文翻译) 的情况
            html_content = md.convert(content_data.get('translated_md', ''))
            template_vars["content"] = html_content
            return render_template("content.html", **template_vars)

    except Exception as e:
        logging.error(f"渲染大学页面时出错: {e}", exc_info=True)
        abort(500)


def sitemap_route():
    """sitemap路由处理函数"""
    base_url = os.getenv('BASE_URL', 'https://www.runjplib.com')
    db = get_db()
    all_universities_for_sitemap = []
    if db is not None:
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
                    "deadline": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$latest_deadline"
                        }
                    },
                    "_id": 0
                }
            }]
            all_universities_for_sitemap = list(db.universities.aggregate(pipeline))
        except Exception as e:
            logging.error(f"为站点地图生成大学列表时出错: {e}")

    response = make_response(render_template('sitemap.xml', base_url=base_url, blogs=get_all_blogs_for_sitemap(), universities=all_universities_for_sitemap))
    response.headers["Content-Type"] = "application/xml"
    return response
