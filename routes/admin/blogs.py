from datetime import datetime
import logging
import uuid

from bson.objectid import ObjectId
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for

from routes.admin.auth import admin_required
from utils import BlogGenerator, clear_blog_list_cache, get_db, thread_pool_manager

from . import admin_bp


def _save_blog_to_db(blog_data):
    """异步保存博客到数据库"""
    try:
        db = get_db()
        if db is None:
            logging.error("Admin异步保存博客失败：无法连接数据库")
            return None

        # 应用Wiki功能：自动识别学校名称并添加超链接
        from utils import blog_wiki_processor
        original_content = blog_data.get('content_md', '')
        processed_content = blog_wiki_processor.process_blog_content(original_content)

        # 如果内容被处理了，更新blog_data
        if processed_content != original_content:
            blog_data['content_md'] = processed_content
            logging.info("Blog内容已应用Wiki功能，自动添加了学校名称超链接")

        result = db.blogs.insert_one(blog_data)
        logging.info(f"New blog post created with ID: {result.inserted_id} (async).")

        # 清除推荐博客缓存，确保新博客能及时出现在推荐中
        from routes.blog.cache import clear_recommended_blogs_cache
        clear_recommended_blogs_cache()
        clear_blog_list_cache()

        return str(result.inserted_id)
    except Exception as e:
        logging.error(f"异步保存博客失败: {e}")
        return None


def _update_blog_in_db(object_id, update_data, blog_id):
    """异步更新博客到数据库"""
    try:
        db = get_db()
        if db is None:
            logging.error("Admin异步更新博客失败：无法连接数据库")
            return

        # 应用Wiki功能：自动识别学校名称并添加超链接
        if 'content_md' in update_data['$set']:
            from utils import blog_wiki_processor
            original_content = update_data['$set']['content_md']
            processed_content = blog_wiki_processor.process_blog_content(original_content)

            # 如果内容被处理了，更新update_data
            if processed_content != original_content:
                update_data['$set']['content_md'] = processed_content
                logging.info("Blog内容已应用Wiki功能，自动添加了学校名称超链接")

        db.blogs.update_one({"_id": object_id}, update_data)
        logging.info(f"Blog post with ID {blog_id} was updated (async).")

        # 清除推荐博客缓存，确保更新的博客能及时反映在推荐中
        from routes.blog.cache import clear_recommended_blogs_cache
        clear_recommended_blogs_cache()
        clear_blog_list_cache()
    except Exception as e:
        logging.error(f"异步更新博客失败: {e}")


def _generate_and_save_blog_async(mode, university_ids, user_prompt, system_prompt):
    """
    异步生成博客内容并保存到数据库。
    这是一个将在后台线程中执行的函数。
    """
    logging.info(f"开始异步生成博客: mode={mode}, university_ids={university_ids}")
    try:
        generator = BlogGenerator()
        result = generator.generate_blog_content(mode, university_ids, user_prompt, system_prompt)

        if not result or 'title' not in result or 'content_md' not in result:
            logging.error("博客生成失败或返回格式不正确。")
            return

        title = result['title'].strip()
        content_md = result['content_md'].strip()
        if not title or not content_md:
            logging.error("生成的内容中缺少标题或正文。")
            return

        db = get_db()
        if db is None:
            logging.error("无法连接到数据库，无法保存生成的博客。")
            return

        # 创建URL友好标题
        url_title = title.lower().replace(" ", "-").replace("/", "-")
        url_title = "".join(c for c in url_title if c.isalnum() or c == "-")
        # 防止URL标题重复
        if db.blogs.find_one({"url_title": url_title}):
            url_title = f"{url_title}-{uuid.uuid4().hex[:6]}"

        new_blog = {
            "title": title,
            "url_title": url_title,
            "publication_date": datetime.now().strftime("%Y-%m-%d"),
            "created_at": datetime.now(),
            "md_last_updated": datetime.now(),
            "html_last_updated": None,
            "content_md": content_md,
            "content_html": None,
            "is_public": False,  # 默认不公开
            "generation_details": {
                "mode": mode,
                "university_ids": university_ids,
                "user_prompt": user_prompt,
                "system_prompt": system_prompt,
                "generated_at": datetime.now()
            }
        }

        # 直接在这里保存，不再使用_save_blog_to_db以避免循环导入和逻辑混淆
        result = db.blogs.insert_one(new_blog)
        logging.info(f"异步生成并保存了新的博客，ID: {result.inserted_id}")

        # 清除缓存
        from routes.blog.cache import clear_recommended_blogs_cache
        clear_recommended_blogs_cache()

    except Exception as e:
        logging.error(f"异步生成博客任务失败: {e}", exc_info=True)


@admin_bp.route("/manage/blogs")
@admin_required
def manage_blogs_page():
    return render_template("manage_blogs.html")


@admin_bp.route("/api/blogs", methods=["GET"])
@admin_required
def get_blogs():
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    cursor = db.blogs.find({}).sort("created_at", -1)
    blogs = []
    for b in cursor:
        b["_id"] = str(b["_id"])
        html_status = "未生成"
        md_last_updated = b.get("md_last_updated")
        html_last_updated = b.get("html_last_updated")
        if html_last_updated:
            html_status = "最新"
            if md_last_updated and md_last_updated > html_last_updated:
                html_status = "待更新"
        b["html_status"] = html_status

        # 处理公开状态
        is_public = b.get("is_public")
        if is_public is False:
            b["public_status"] = "私密"
        else:
            b["public_status"] = "公开"  # 默认为公开

        if md_last_updated and isinstance(md_last_updated, datetime):
            b["md_last_updated"] = md_last_updated.strftime("%Y-%m-%d %H:%M:%S")
        if html_last_updated and isinstance(html_last_updated, datetime):
            b["html_last_updated"] = html_last_updated.strftime("%Y-%m-%d %H:%M:%S")

        # 在API响应中移除大的字段
        b.pop("content_md", None)
        b.pop("content_html", None)
        blogs.append(b)
    return jsonify(blogs)


@admin_bp.route("/api/blogs/<item_id>", methods=["DELETE"])
@admin_required
def delete_blog(item_id):
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    db.blogs.delete_one({"_id": ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route("/blog/create")
@admin_required
def create_blog_page():
    """渲染博客创建页面，并处理用于'再生成'的查询参数"""
    # 从查询参数获取用于再生成的数据
    generation_data = {
        "mode": request.args.get("mode", "expand"),
        "university_ids": request.args.getlist("university_ids"),
        "user_prompt": request.args.get("user_prompt", ""),
        "system_prompt": request.args.get("system_prompt", "")
    }
    # 如果存在大学ID，需要获取大学名称以在模板中显示
    if generation_data["university_ids"]:
        db = get_db()
        if db is not None:
            try:
                university_docs = db.universities.find({"_id": {"$in": [ObjectId(uid) for uid in generation_data["university_ids"]]}}, {"university_name": 1})
                generation_data["universities"] = [{"_id": str(doc["_id"]), "university_name": doc["university_name"]} for doc in university_docs]
            except Exception as e:
                logging.error(f"为'再生成'查询大学名称失败: {e}")

    return render_template("create_blog.html", generation_data=generation_data)


@admin_bp.route("/api/blog/generate", methods=["POST"])
@admin_required
def generate_blog():
    """
    接收博客生成请求，并将其作为后台任务异步执行。
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求格式"}), 400

    university_ids = data.get("university_ids", [])
    user_prompt = data.get("user_prompt", "")
    system_prompt = data.get("system_prompt", "")
    mode = data.get("mode", "expand")

    if not system_prompt:
        return jsonify({"error": "系统提示词不能为空"}), 400

    # 根据模式验证输入
    if mode in ["expand", "compare"] and not university_ids:
        return jsonify({"error": "该模式需要至少选择一所大学"}), 400
    if mode == "compare" and len(university_ids) < 2:
        return jsonify({"error": "对比分析模式需要至少选择两所大学"}), 400
    if mode == "user_prompt_only" and not user_prompt:
        return jsonify({"error": "该模式需要填写用户提示词"}), 400

    # 提交到后台线程池执行
    success = thread_pool_manager.submit_admin_task(_generate_and_save_blog_async,
                                                    mode=mode,
                                                    university_ids=university_ids,
                                                    user_prompt=user_prompt,
                                                    system_prompt=system_prompt)

    if success:
        logging.info("博客生成任务已成功提交到后台。")
        return jsonify({"message": "博客生成任务已开始，请稍后在博客管理页面查看结果。"})
    else:
        logging.error("无法提交博客生成任务到线程池，可能线程池已满。")
        return jsonify({"error": "无法开始生成任务，服务器繁忙，请稍后再试。"}), 503


@admin_bp.route("/api/blog/save", methods=["POST"])
@admin_required
def save_blog():
    """
    保存新博客文章到数据库。
    需要包含'title'和'content_md'的JSON。
    """
    data = request.get_json()
    if not data or "title" not in data or "content_md" not in data:
        return jsonify({"error": "无效的请求格式，需要'title'和'content_md'"}), 400

    title = data["title"].strip()
    content_md = data["content_md"].strip()

    if not title or not content_md:
        return jsonify({"error": "标题和内容不能为空"}), 400

    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        # 创建URL友好标题
        url_title = title.lower().replace(" ", "-").replace("/", "-")
        # 移除不安全的URL字符
        url_title = "".join(c for c in url_title if c.isalnum() or c == "-")

        new_blog = {
            "title": title,
            "url_title": url_title,
            "publication_date": datetime.now().strftime("%Y-%m-%d"),
            "created_at": datetime.now(),
            "md_last_updated": datetime.now(),
            "html_last_updated": None,
            "content_md": content_md,
            "content_html": None,
            "is_public": True,  # 手动创建的博客默认为公开
        }

        # 尝试异步保存博客
        success = thread_pool_manager.submit_admin_task(_save_blog_to_db, new_blog)

        if not success:
            # 线程池满，同步执行
            logging.warning("Admin线程池繁忙，同步保存博客")
            try:
                # 应用Wiki功能
                from utils import blog_wiki_processor
                original_content = new_blog.get('content_md', '')
                processed_content = blog_wiki_processor.process_blog_content(original_content)

                if processed_content != original_content:
                    new_blog['content_md'] = processed_content
                    logging.info("Blog内容已应用Wiki功能，自动添加了学校名称超链接")

                result = db.blogs.insert_one(new_blog)
                logging.info(f"New blog post created with ID: {result.inserted_id} (sync).")

                # 清除推荐博客缓存，确保新博客能及时出现在推荐中
                from routes.blog.cache import clear_recommended_blogs_cache
                clear_recommended_blogs_cache()
                clear_blog_list_cache()

                return jsonify({"message": "文章保存成功", "blog_id": str(result.inserted_id)})
            except Exception as sync_e:
                logging.error(f"同步保存博客失败: {sync_e}")
                return jsonify({"error": "保存失败，请重试"}), 500
        else:
            # 异步任务已提交
            logging.info("Blog save task submitted to thread pool.")
            return jsonify({"message": "文章保存任务已提交", "blog_id": "pending"})
    except Exception as e:
        logging.error(f"[Admin API] Failed to save blog: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/blog/edit/<blog_id>", methods=["GET", "POST"])
@admin_required
def edit_blog(blog_id):
    """
    处理博客文章编辑。
    GET: 显示编辑表单。
    POST: 更新数据库中的文章。
    """
    db = get_db()
    if db is None:
        return render_template("edit_blog.html", error="数据库连接失败")

    try:
        object_id = ObjectId(blog_id)
    except Exception:
        return render_template("404.html"), 404

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content_md = request.form.get("content_md", "").strip()
        # 新增：获取is_public状态，来自表单的值是字符串'true'或'false'
        is_public_str = request.form.get("is_public", "true")
        is_public = is_public_str.lower() == 'true'

        if not title or not content_md:
            blog = db.blogs.find_one({"_id": object_id})
            return render_template("edit_blog.html", blog=blog, error="标题和内容不能为空")

        # 创建URL友好标题
        url_title = title.lower().replace(" ", "-").replace("/", "-")
        url_title = "".join(c for c in url_title if c.isalnum() or c == "-")

        update_data = {
            "$set": {
                "title": title,
                "url_title": url_title,
                "content_md": content_md,
                "md_last_updated": datetime.now(),
                "is_public": is_public,  # 更新is_public字段
            }
        }

        # 尝试异步更新博客
        success = thread_pool_manager.submit_admin_task(_update_blog_in_db, object_id, update_data, blog_id)

        if not success:
            # 线程池满，同步执行
            logging.warning("Admin线程池繁忙，同步更新博客")
            try:
                # 应用Wiki功能
                if 'content_md' in update_data['$set']:
                    from utils import blog_wiki_processor
                    original_content = update_data['$set']['content_md']
                    processed_content = blog_wiki_processor.process_blog_content(original_content)

                    if processed_content != original_content:
                        update_data['$set']['content_md'] = processed_content
                        logging.info("Blog内容已应用Wiki功能，自动添加了学校名称超链接")

                db.blogs.update_one({"_id": object_id}, update_data)
                logging.info(f"Blog post with ID {blog_id} was updated (sync).")

                # 清除推荐博客缓存，确保更新的博客能及时反映在推荐中
                from routes.blog.cache import clear_recommended_blogs_cache
                clear_recommended_blogs_cache()
                clear_blog_list_cache()
            except Exception as e:
                logging.error(f"同步更新博客失败: {e}")
                return render_template(
                    "edit_blog.html",
                    blog=db.blogs.find_one({"_id": object_id}),
                    error="更新失败，请重试",
                )
        else:
            logging.info(f"Blog post with ID {blog_id} update task submitted to thread pool.")

        return redirect(url_for("admin.manage_blogs_page"))

    # GET请求
    blog = db.blogs.find_one({"_id": object_id})
    if not blog:
        return render_template("404.html"), 404

    blog["_id"] = str(blog["_id"])

    return render_template("edit_blog.html", blog=blog)
