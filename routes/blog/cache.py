import logging

from cachetools import TTLCache

# 缓存定义
recommended_blogs_cache = TTLCache(maxsize=1, ttl=1800)  # 30分钟缓存，避免频繁重新计算


def update_blog_html_in_db(db, blog_id, html_content, update_time):
    """
    一个在后台线程中运行的函数，用于将新生成的HTML内容更新回MongoDB。
    """
    try:
        db.blogs.update_one({'_id': blog_id}, {'$set': {'content_html': html_content, 'html_last_updated': update_time}})
        logging.info(f"成功将博客 {blog_id} 的HTML内容更新到数据库。")
    except Exception as e:
        logging.error(f"后台更新博客 {blog_id} 的HTML时出错: {e}")


def clear_recommended_blogs_cache():
    """
    清除推荐博客缓存，用于在博客更新后刷新推荐内容
    """
    global recommended_blogs_cache
    recommended_blogs_cache.clear()
    logging.info("已清除推荐博客缓存")
