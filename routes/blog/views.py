from datetime import datetime
from datetime import timedelta
from datetime import timezone
import logging
import random
import re

from cachetools import cached
from flask import render_template
import markdown

from routes.blog.cache import recommended_blogs_cache
from routes.blog.cache import update_blog_html_in_db
from utils.core.database import get_db
from utils.system.analytics import log_access
from utils.system.thread_pool import thread_pool_manager
from utils.tools.cache import blog_list_cache


@cached(blog_list_cache)
def get_all_blogs():
    """
    从MongoDB获取所有公开博客的列表，用于侧边栏。
    此函数的结果会被缓存5分钟。
    只获取必要字段以提高效率，并按日期降序排序。
    """
    logging.info("缓存未命中或已过期，正在从MongoDB重新加载所有公开博客列表...")
    db = get_db()
    if db is None:
        logging.error("无法连接到MongoDB")
        return []

    try:
        # 只查找is_public不为false的博客
        query = {"is_public": {"$ne": False}}
        blogs_cursor = db.blogs.find(query, {"title": 1, "url_title": 1, "publication_date": 1, "_id": 0}).sort("publication_date", -1)

        blog_list = list(blogs_cursor)
        logging.info(f"成功从MongoDB加载了 {len(blog_list)} 篇公开博客。")
        # 为了模板兼容性，将 publication_date 重命名为 date
        for blog in blog_list:
            blog['date'] = blog.get('publication_date')
        return blog_list
    except Exception as e:
        logging.error(f"从MongoDB加载博客列表时出错: {e}")
        return []


def get_blog_by_url_title(url_title):
    """
    根据URL友好的标题从MongoDB获取单篇公开博客的完整内容。
    实现了 Lazy Rebuild 机制来处理Markdown到HTML的转换。
    """
    logging.info(f"从MongoDB获取博客: {url_title}")
    db = get_db()
    if db is None:
        logging.error(f"无法连接到MongoDB以获取博客: {url_title}")
        return None

    try:
        # 只查找is_public不为false的博客
        query = {"url_title": url_title, "is_public": {"$ne": False}}
        blog_doc = db.blogs.find_one(query)
        if not blog_doc:
            logging.warning(f"在MongoDB中未找到公开的、url_title 为 '{url_title}' 的博客。")
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


@cached(recommended_blogs_cache)
def get_weighted_recommended_blogs_with_summary(count=3):
    """
    根据时间权重算法获取推荐博客，并生成摘要。
    
    算法逻辑：
    1. 从最近3天的blog中选2条
    2. 从最近7天的blog中选不重复的补足3条
    3. 从剩下的blog中选不重复的补足3条
    
    如果某个时间段没有足够的blog，会从其他时间段补充。
    """
    logging.info(f"缓存未命中或过期，开始时间权重推荐算法，目标获取 {count} 篇博客 ===")
    db = get_db()
    if db is None:
        logging.error("无法连接到MongoDB")
        return []

    try:
        # 获取当前时间
        now = datetime.now()
        logging.info(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        # 计算时间范围
        three_days_ago = now - timedelta(days=3)
        seven_days_ago = now - timedelta(days=7)
        logging.info(f"时间范围: 最近3天({three_days_ago.strftime('%Y-%m-%d')}) ~ 最近7天({seven_days_ago.strftime('%Y-%m-%d')})")

        # 获取所有公开博客，按日期降序排序
        pipeline = [{
            "$match": {
                "is_public": {
                    "$ne": False
                }
            }
        }, {
            "$sort": {
                "publication_date": -1
            }
        }, {
            "$project": {
                "title": 1,
                "url_title": 1,
                "content_md": 1,
                "publication_date": 1,
                "_id": 0
            }
        }]
        all_blogs = list(db.blogs.aggregate(pipeline))

        if not all_blogs:
            logging.warning("没有找到任何公开的博客")
            return []

        logging.info(f"数据库中共有 {len(all_blogs)} 篇公开博客")

        # 按时间范围分组博客
        recent_3_days = []
        recent_7_days = []
        older_blogs = []

        for blog in all_blogs:
            pub_date = blog.get('publication_date')
            if isinstance(pub_date, str):
                try:
                    pub_date = datetime.strptime(pub_date, '%Y-%m-%d')
                except ValueError:
                    # 如果日期格式不正确，归类到较老的文章中
                    older_blogs.append(blog)
                    continue

            # 使用日期部分进行比较，忽略时间部分
            pub_date_only = pub_date.date()
            three_days_ago_date = three_days_ago.date()
            seven_days_ago_date = seven_days_ago.date()

            if pub_date_only >= three_days_ago_date:
                recent_3_days.append(blog)
            elif pub_date_only >= seven_days_ago_date:
                recent_7_days.append(blog)
            else:
                older_blogs.append(blog)

        logging.debug("=== 博客分组结果 ===")
        logging.debug(f"最近3天: {len(recent_3_days)} 篇")
        if recent_3_days:
            for i, blog in enumerate(recent_3_days[:3], 1):  # 只显示前3个
                logging.debug(f"  {i}. {blog['title']} ({blog['publication_date']})")

        logging.debug(f"最近7天: {len(recent_7_days)} 篇")
        if recent_7_days:
            for i, blog in enumerate(recent_7_days[:3], 1):  # 只显示前3个
                logging.debug(f"  {i}. {blog['title']} ({blog['publication_date']})")

        logging.debug(f"更早: {len(older_blogs)} 篇")
        if older_blogs:
            for i, blog in enumerate(older_blogs[:3], 1):  # 只显示前3个
                logging.debug(f"  {i}. {blog['title']} ({blog['publication_date']})")

        # 按算法选择博客
        selected_blogs = []
        used_url_titles = set()

        # 步骤1: 从最近3天的blog中选2条
        logging.debug("\n=== Step 1: 从最近3天的blog中选2条 ===")
        if recent_3_days:
            # 选择2条，但不超过可用的数量
            select_count = min(2, len(recent_3_days))
            selected_3_days = random.sample(recent_3_days, select_count)
            for i, selected in enumerate(selected_3_days, 1):
                selected_blogs.append(selected)
                used_url_titles.add(selected['url_title'])
                logging.debug(f"✅ 成功选择 {i}: {selected['title']} ({selected['publication_date']})")
        else:
            logging.debug("❌ 最近3天没有博客，跳过Step 1")

        # 步骤2: 从最近7天的blog中选不重复的补足3条
        logging.debug("\n=== Step 2: 从最近7天的blog中选不重复的补足3条 ===")
        available_7_days = [blog for blog in recent_7_days if blog['url_title'] not in used_url_titles]
        logging.debug(f"可选的7天博客数量: {len(available_7_days)} (已排除已选择的 {len(used_url_titles)} 篇)")

        if available_7_days:
            # 计算还需要多少篇才能达到3篇
            needed_from_7_days = 3 - len(selected_blogs)
            if needed_from_7_days > 0:
                # 选择需要的数量，但不超过可用的数量
                select_count = min(needed_from_7_days, len(available_7_days))
                selected_7_days = random.sample(available_7_days, select_count)
                for i, selected in enumerate(selected_7_days, 1):
                    selected_blogs.append(selected)
                    used_url_titles.add(selected['url_title'])
                    logging.debug(f"✅ 成功选择: {selected['title']} ({selected['publication_date']})")
        else:
            logging.debug("❌ 最近7天没有可选的博客，跳过Step 2")

        # 步骤3: 从剩下的blog中选不重复的补足3条
        logging.debug(f"\n=== Step 3: 从剩下的blog中选不重复的补足{count}条 ===")
        remaining_blogs = []
        for blog in all_blogs:
            if blog['url_title'] not in used_url_titles:
                remaining_blogs.append(blog)

        logging.debug(f"剩余可选博客数量: {len(remaining_blogs)}")
        needed_count = count - len(selected_blogs)
        logging.debug(f"还需要选择: {needed_count} 篇")

        if needed_count > 0 and remaining_blogs:
            # 随机选择需要的数量
            additional_selection = random.sample(remaining_blogs, min(needed_count, len(remaining_blogs)))
            selected_blogs.extend(additional_selection)
            for i, blog in enumerate(additional_selection, 1):
                logging.debug(f"✅ 补充选择 {i}: {blog['title']} ({blog['publication_date']})")
        elif needed_count > 0:
            logging.warning("❌ 没有更多博客可选，无法补足目标数量")

        # 生成结果
        logging.debug("\n=== 最终选择结果 ===")
        result = []
        for i, blog in enumerate(selected_blogs, 1):
            # 使用markdown库将markdown内容转换为纯文本
            md_content = blog.get('content_md', '')
            # 先转换为HTML，然后去除HTML标签得到纯文本
            md = markdown.Markdown(extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'])
            html_content = md.convert(md_content)
            text_content = re.sub(r'<[^>]+>', '', html_content)
            summary = text_content[:100].strip() + '...' if len(text_content) > 100 else text_content
            result.append({'title': blog['title'], 'url_title': blog['url_title'], 'summary': summary})
            logging.debug(f"最终推荐 {i}: {blog['title']} ({blog['publication_date']})")

        logging.info(f"=== 算法执行完成，成功获取了 {len(result)} 篇推荐博客 ===")
        return result

    except Exception as e:
        logging.error(f"获取推荐博客时出错: {e}")
        # 如果出错，回退到随机选择
        logging.info("回退到随机推荐算法")
        return get_random_blogs_with_summary(count)


def get_random_blogs_with_summary(count=3):
    """
    从MongoDB获取指定数量的随机公开博客，并生成摘要。
    这是原有的随机推荐算法，作为备选方案。
    """
    logging.debug(f"从MongoDB获取 {count} 篇随机公开博客（带摘要）...")
    db = get_db()
    if db is None:
        return []

    try:
        pipeline = [{
            "$match": {
                "is_public": {
                    "$ne": False
                }
            }
        }, {
            "$sample": {
                "size": count
            }
        }, {
            "$project": {
                "title": 1,
                "url_title": 1,
                "content_md": 1,
                "_id": 0
            }
        }]
        random_blogs = list(db.blogs.aggregate(pipeline))

        result = []
        for blog in random_blogs:
            # 使用markdown库将markdown内容转换为纯文本
            md_content = blog.get('content_md', '')
            # 先转换为HTML，然后去除HTML标签得到纯文本
            md = markdown.Markdown(extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'])
            html_content = md.convert(md_content)
            text_content = re.sub(r'<[^>]+>', '', html_content)
            summary = text_content[:100].strip() + '...' if len(text_content) > 100 else text_content
            result.append({'title': blog['title'], 'url_title': blog['url_title'], 'summary': summary})
        logging.info(f"成功获取了 {len(result)} 篇随机博客。")
        return result
    except Exception as e:
        logging.error(f"获取随机博客时出错: {e}")
        return []


def blog_list_route():
    """
    博客列表路由处理函数。
    现在默认显示最新的一篇博客。
    """
    logging.info("请求博客列表页面...")
    all_blogs = get_all_blogs()
    if not all_blogs:
        logging.warning("没有找到任何博客，渲染404页面。")
        return render_template('404.html', mode='blog', blogs=[], recommended_blogs=[]), 404

    # 获取最新的一篇博客（列表已按降序排列）
    latest_blog_meta = all_blogs[0]
    logging.debug(f"最新博客: {latest_blog_meta['title']}")

    # 获取这篇博客的详细内容
    blog_content = get_blog_by_url_title(latest_blog_meta['url_title'])
    if not blog_content:
        logging.error(f"无法获取最新博客 '{latest_blog_meta['url_title']}' 的内容，渲染404页面。")
        return render_template('404.html', mode='blog', blogs=all_blogs, recommended_blogs=get_weighted_recommended_blogs_with_summary(10)), 404

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
    # 以url_title作为资源标识
    log_access('blog', resource_key=url_title)
    logging.info(f"请求博客详情页面: {url_title}")

    blog = get_blog_by_url_title(url_title)
    all_blogs_for_sidebar = get_all_blogs()

    if blog is None:
        logging.warning(f"博客 '{url_title}' 未找到，渲染404页面。")
        recommended_blogs = get_weighted_recommended_blogs_with_summary(10)
        return render_template('404.html', mode='blog', blogs=all_blogs_for_sidebar, recommended_blogs=recommended_blogs), 404

    # 获取推荐阅读数据，排除当前博客
    recommended_blogs = get_weighted_recommended_blogs_with_summary(3)
    # 过滤掉当前博客，避免推荐自己
    recommended_blogs = [b for b in recommended_blogs if b['url_title'] != url_title]

    return render_template(
        'content_blog.html',
        mode='blog',
        blogs=all_blogs_for_sidebar,
        blog=blog,
        content=blog['content'],
        recommended_blogs=recommended_blogs,
        debug_file_path=None  # 文件路径不再适用
    )
