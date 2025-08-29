"""
博客路由模块 (MongoDB Version)
"""
from datetime import datetime
from datetime import timezone
import logging
import re

from cachetools import cached
from flask import render_template
import markdown

from utils.analytics import log_access
from utils.cache import blog_list_cache
from utils.mongo_client import get_db
from utils.thread_pool_manager import thread_pool_manager

# --- MongoDB based Blog Functions ---


@cached(blog_list_cache)
def get_all_blogs():
    """
    从MongoDB获取所有博客的列表，用于侧边栏。
    此函数的结果会被缓存5分钟。
    只获取必要字段以提高效率，并按日期降序排序。
    """
    logging.info("缓存未命中或已过期，正在从MongoDB重新加载所有博客列表...")
    db = get_db()
    if db is None:
        logging.error("无法连接到MongoDB")
        return []

    try:
        blogs_cursor = db.blogs.find({}, {"title": 1, "url_title": 1, "publication_date": 1, "_id": 0}).sort("publication_date", -1)

        blog_list = list(blogs_cursor)
        logging.info(f"成功从MongoDB加载了 {len(blog_list)} 篇博客。")
        # 为了模板兼容性，将 publication_date 重命名为 date
        for blog in blog_list:
            blog['date'] = blog.get('publication_date')
        return blog_list
    except Exception as e:
        logging.error(f"从MongoDB加载博客列表时出错: {e}")
        return []


def get_blog_by_url_title(url_title):
    """
    根据URL友好的标题从MongoDB获取单篇博客的完整内容。
    实现了 Lazy Rebuild 机制来处理Markdown到HTML的转换。
    """
    logging.info(f"从MongoDB获取博客: {url_title}")
    db = get_db()
    if db is None:
        logging.error(f"无法连接到MongoDB以获取博客: {url_title}")
        return None

    try:
        blog_doc = db.blogs.find_one({"url_title": url_title})
        if not blog_doc:
            logging.warning(f"在MongoDB中未找到 url_title 为 '{url_title}' 的博客。")
            return None

        html_content = blog_doc.get('content_html')
        md_last_updated = blog_doc.get('md_last_updated')
        html_last_updated = blog_doc.get('html_last_updated')

        # Lazy Rebuild 逻辑
        needs_rebuild = False
        if not html_content:
            needs_rebuild = True
            logging.info(f"博客 '{url_title}'缺少HTML内容，需要生成。")
        elif md_last_updated and html_last_updated and md_last_updated > html_last_updated:
            needs_rebuild = True
            logging.info(f"博客 '{url_title}'的Markdown已更新，需要重新生成HTML。")

        if needs_rebuild:
            md = markdown.Markdown(
                extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'],
                output_format="html5",
            )
            html_content = md.convert(blog_doc.get('content_md', ''))

            # 使用线程池更新数据库，避免阻塞当前请求
            update_time = datetime.now(timezone.utc)

            # 尝试提交到线程池
            success = thread_pool_manager.submit_blog_html_build(update_blog_html_in_db, db, blog_doc['_id'], html_content, update_time)

            if success:
                logging.info(f"已为博客 '{url_title}' 提交后台HTML更新任务到线程池。")
            else:
                # 线程池繁忙，降级为同步执行
                logging.warning(f"线程池繁忙，为博客 '{url_title}' 同步执行HTML更新。")
                try:
                    update_blog_html_in_db(db, blog_doc['_id'], html_content, update_time)
                except Exception as e:
                    logging.error(f"同步更新博客HTML失败: {e}")

        # 构建要在模板中使用的博客对象
        blog = {
            'id': str(blog_doc['_id']),
            'title': blog_doc['title'],
            'url_title': blog_doc['url_title'],
            'date': blog_doc.get('publication_date'),
            'content': html_content
        }
        logging.info(f"成功获取并处理了博客: {url_title}")
        return blog
    except Exception as e:
        logging.error(f"获取博客 '{url_title}' 时出错: {e}")
        return None


def update_blog_html_in_db(db, blog_id, html_content, update_time):
    """
    一个在后台线程中运行的函数，用于将新生成的HTML内容更新回MongoDB。
    """
    try:
        db.blogs.update_one({'_id': blog_id}, {'$set': {'content_html': html_content, 'html_last_updated': update_time}})
        logging.info(f"成功将博客 {blog_id} 的HTML内容更新到数据库。")
    except Exception as e:
        logging.error(f"后台更新博客 {blog_id} 的HTML时出错: {e}")


def get_random_blogs_with_summary(count=3):
    """
    从MongoDB获取指定数量的随机博客，并生成摘要。
    """
    logging.info(f"从MongoDB获取 {count} 篇随机博客（带摘要）...")
    db = get_db()
    if db is None:
        return []

    try:
        pipeline = [{"$sample": {"size": count}}, {"$project": {"title": 1, "url_title": 1, "content_md": 1, "_id": 0}}]
        random_blogs = list(db.blogs.aggregate(pipeline))

        result = []
        for blog in random_blogs:
            text_content = re.sub(r'<[^>]+>', '', blog.get('content_md', ''))
            summary = text_content[:100].strip() + '...' if len(text_content) > 100 else text_content
            result.append({'title': blog['title'], 'url_title': blog['url_title'], 'summary': summary})
        logging.info(f"成功获取了 {len(result)} 篇随机博客。")
        return result
    except Exception as e:
        logging.error(f"获取随机博客时出错: {e}")
        return []


# --- Blog Routes ---


def blog_list_route():
    """
    博客列表路由处理函数。
    现在默认显示最新的一篇博客。
    """
    logging.info("请求博客列表页面...")
    all_blogs = get_all_blogs()
    if not all_blogs:
        logging.warning("没有找到任何博客，渲染404页面。")
        # 即使没有博客，也尝试获取一些推荐内容（如果适用）
        return render_template('404.html', mode='blog', blogs=[], recommended_blogs=[]), 404

    # 获取最新的一篇博客（列表已按降序排列）
    latest_blog_meta = all_blogs[0]
    logging.debug(f"最新博客: {latest_blog_meta['title']}")

    # 获取这篇博客的详细内容
    blog_content = get_blog_by_url_title(latest_blog_meta['url_title'])
    if not blog_content:
        logging.error(f"无法获取最新博客 '{latest_blog_meta['url_title']}' 的内容，渲染404页面。")
        return render_template('404.html', mode='blog', blogs=all_blogs, recommended_blogs=get_random_blogs_with_summary(10)), 404

    return render_template(
        'content_blog.html',
        mode='blog',
        blogs=all_blogs,
        blog=blog_content,
        content=blog_content['content'],
        debug_file_path=None  # 文件路径不再适用
    )


def blog_detail_route(url_title):
    """
    博客详情路由处理函数。
    现在只从MongoDB获取数据。
    """
    log_access('blog')
    logging.info(f"请求博客详情页面: {url_title}")

    blog = get_blog_by_url_title(url_title)
    all_blogs_for_sidebar = get_all_blogs()

    if blog is None:
        logging.warning(f"博客 '{url_title}' 未找到，渲染404页面。")
        recommended_blogs = get_random_blogs_with_summary(10)
        return render_template('404.html', mode='blog', blogs=all_blogs_for_sidebar, recommended_blogs=recommended_blogs), 404

    return render_template(
        'content_blog.html',
        mode='blog',
        blogs=all_blogs_for_sidebar,
        blog=blog,
        content=blog['content'],
        debug_file_path=None  # 文件路径不再适用
    )
