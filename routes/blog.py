"""
博客路由模块 (MongoDB Version)
"""
import logging
import random
import re
from datetime import datetime

import markdown
from flask import render_template, abort
from utils.mongo_client import get_mongo_client

# --- MongoDB based Blog Functions ---

def get_all_blogs():
    """
    从MongoDB获取所有博客的列表，用于侧边栏。
    只获取必要字段以提高效率，并按日期降序排序。
    """
    logging.info("从MongoDB加载所有博客列表...")
    client = get_mongo_client()
    if not client:
        logging.error("无法连接到MongoDB")
        return []
    db = client.RunJPLib
    
    try:
        blogs_cursor = db.blogs.find(
            {},
            {"title": 1, "url_title": 1, "publication_date": 1, "_id": 0}
        ).sort("publication_date", -1)
        
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
    """
    logging.info(f"从MongoDB获取博客: {url_title}")
    client = get_mongo_client()
    if not client:
        logging.error(f"无法连接到MongoDB以获取博客: {url_title}")
        return None
    db = client.RunJPLib

    try:
        blog_doc = db.blogs.find_one({"url_title": url_title})
        if not blog_doc:
            logging.warning(f"在MongoDB中未找到 url_title 为 '{url_title}' 的博客。")
            return None

        # 处理Markdown内容
        md = markdown.Markdown(
            extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'],
            output_format="html5",
        )
        html_content = md.convert(blog_doc.get('content_md', ''))
        
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

def get_random_blogs_with_summary(count=3):
    """
    从MongoDB获取指定数量的随机博客，并生成摘要。
    """
    logging.info(f"从MongoDB获取 {count} 篇随机博客（带摘要）...")
    client = get_mongo_client()
    if not client:
        return []
    db = client.RunJPLib

    try:
        pipeline = [
            {"$sample": {"size": count}},
            {"$project": {
                "title": 1,
                "url_title": 1,
                "content_md": 1,
                "_id": 0
            }}
        ]
        random_blogs = list(db.blogs.aggregate(pipeline))
        
        result = []
        for blog in random_blogs:
            text_content = re.sub(r'<[^>]+>', '', blog.get('content_md', ''))
            summary = text_content[:100].strip() + '...' if len(text_content) > 100 else text_content
            result.append({
                'title': blog['title'],
                'url_title': blog['url_title'],
                'summary': summary
            })
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