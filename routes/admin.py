from functools import wraps
import logging
import os

from bson.objectid import ObjectId
from flask import Blueprint
from flask import jsonify
from flask import make_response
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_jwt_extended import create_access_token
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import set_access_cookies
from flask_jwt_extended import unset_jwt_cookies
from flask_jwt_extended import verify_jwt_in_request

from utils.mongo_client import get_mongo_client
from utils.blog_generator import BlogGenerator
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder='../templates/admin')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):
        is_api_request = request.path.startswith('/admin/api/')
        try:
            verify_jwt_in_request(locations=['headers', 'cookies'])
            identity = get_jwt_identity()
            if identity != 'admin':
                logging.warning("A non-admin identity was found in a valid JWT.")
                if is_api_request:
                    return jsonify(msg="需要管理员权限"), 403
                else:
                    return redirect(url_for('admin.login'))
        except Exception as e:
            logging.warning(f"JWT validation failed for path '{request.path}': {e}")
            if is_api_request:
                return jsonify(msg="Token无效或已过期"), 401
            else:
                return redirect(url_for('admin.login'))
        return fn(*args, **kwargs)

    return wrapper


@admin_bp.route('/')
@admin_required
def dashboard():
    return render_template('dashboard.html')


@admin_bp.route('/login')
def login():
    return render_template('login.html')


@admin_bp.route('/logout')
def logout():
    response = make_response(redirect(url_for('admin.login')))
    unset_jwt_cookies(response)
    return response


@admin_bp.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        logging.error("登录失败: 请求体不是有效的JSON或Content-Type头缺失。")
        return jsonify({"msg": "无效的请求格式"}), 400
    access_code = data.get('access_code')
    env_access_code = os.getenv('ACCESS_CODE')
    if not env_access_code:
        logging.error("严重安全配置错误: 环境变量 ACCESS_CODE 未设置。")
        return jsonify({"msg": "服务器配置错误"}), 500
    if not access_code or access_code != env_access_code:
        logging.warning("收到一个错误的访问码。")
        return jsonify({"msg": "访问码错误"}), 401
    logging.info("管理员登录成功。")
    access_token = create_access_token(identity="admin")
    response = jsonify(msg="登录成功")
    set_access_cookies(response, access_token)
    return response


@admin_bp.route('/api/verify_token')
@admin_required
def verify_token():
    return jsonify(status="ok")


# --- Data Management Pages ---
@admin_bp.route('/manage/universities')
@admin_required
def manage_universities_page():
    return render_template('manage_universities.html')


@admin_bp.route('/manage/blogs')
@admin_required
def manage_blogs_page():
    return render_template('manage_blogs.html')


# --- Data Management APIs ---
@admin_bp.route('/api/universities', methods=['GET'])
@admin_required
def get_universities():
    client = get_mongo_client()
    if not client:
        logging.error("[Admin API] Get universities failed: DB connection error.")
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    try:
        logging.debug("[Admin API] Fetching universities from database...")
        projection = {"content": 0, "source_path": 0}
        cursor = db.universities.find({}, projection).sort("university_name", 1)

        # --- 关键修复点：让 jsonify 自动处理 BSON 类型 ---
        universities = list(cursor)

        # ObjectId 仍然需要手动转换为字符串
        for u in universities:
            u['_id'] = str(u['_id'])

        logging.info(f"[Admin API] Successfully fetched {len(universities)} university documents.")
        if universities:
            logging.debug(f"[Admin API] First university document sample: {universities[0]}")

        return jsonify(universities)
    except Exception as e:
        logging.error(f"[Admin API] An exception occurred while fetching universities: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route('/api/universities/<item_id>', methods=['DELETE'])
@admin_required
def delete_university(item_id):
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    db.universities.delete_one({'_id': ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route('/api/universities', methods=['DELETE'])
@admin_required
def clear_universities():
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    db.universities.delete_many({})
    return jsonify({"message": "数据集合已清空"})


@admin_bp.route('/api/blogs', methods=['GET'])
@admin_required
def get_blogs():
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    cursor = db.blogs.find({}).sort("publication_date", -1)
    blogs = []
    for b in cursor:
        b['_id'] = str(b['_id'])
        html_status = "未生成"
        md_last_updated = b.get('md_last_updated')
        html_last_updated = b.get('html_last_updated')
        if html_last_updated:
            html_status = "最新"
            if md_last_updated and md_last_updated > html_last_updated:
                html_status = "待更新"
        b['html_status'] = html_status
        if md_last_updated:
            b['md_last_updated'] = md_last_updated.strftime('%Y-%m-%d %H:%M:%S')
        if html_last_updated:
            b['html_last_updated'] = html_last_updated.strftime('%Y-%m-%d %H:%M:%S')
        b.pop('content_md', None)
        b.pop('content_html', None)
        blogs.append(b)
    return jsonify(blogs)


@admin_bp.route('/api/blogs/<item_id>', methods=['DELETE'])
@admin_required
def delete_blog(item_id):
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    db.blogs.delete_one({'_id': ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route('/api/blogs', methods=['DELETE'])
@admin_required
def clear_blogs():
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib
    db.blogs.delete_many({})
    return jsonify({"message": "数据集合已清空"})


# --- Blog Creator ---


@admin_bp.route('/blog/create')
@admin_required
def create_blog_page():
    """Renders the blog creation page."""
    return render_template('create_blog.html')


@admin_bp.route('/api/universities/search', methods=['GET'])
@admin_required
def search_universities():
    """
    Searches for universities by name.
    Accepts a 'q' query parameter for the search term.
    """
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    try:
        # Search for universities where the name contains the query string (case-insensitive)
        universities = list(db.universities.find({
            "university_name": {
                "$regex": query,
                "$options": "i"
            }
        }, {
            "_id": 1,
            "university_name": 1
        }).limit(20))  # Limit to 20 results for performance

        for u in universities:
            u['_id'] = str(u['_id'])

        return jsonify(universities)
    except Exception as e:
        logging.error(f"[Admin API] University search failed: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route('/api/blog/generate', methods=['POST'])
@admin_required
def generate_blog():
    """
    Generates blog content using the AI generator.
    Expects a JSON payload with 'university_ids', 'user_prompt', and 'system_prompt'.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效的请求格式"}), 400

    university_ids = data.get('university_ids', [])
    user_prompt = data.get('user_prompt', '')
    system_prompt = data.get('system_prompt', '')
    mode = data.get('mode', 'expand')  # Default to expand for safety

    if not system_prompt:
        return jsonify({"error": "系统提示词不能为空"}), 400

    # Validate inputs based on mode
    if mode in ['expand', 'compare'] and not university_ids:
        return jsonify({"error": "该模式需要至少选择一所大学"}), 400
    if mode == 'compare' and len(university_ids) < 2:
        return jsonify({"error": "对比分析模式需要至少选择两所大学"}), 400
    if mode == 'user_prompt_only' and not user_prompt:
        return jsonify({"error": "该模式需要填写用户提示词"}), 400

    try:
        generator = BlogGenerator()
        result = generator.generate_blog_content(mode, university_ids, user_prompt, system_prompt)
        if result:
            return jsonify(result)
        else:
            return jsonify({"error": "生成文章失败"}), 500
    except Exception as e:
        logging.error(f"[Admin API] Blog generation failed: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route('/api/blog/save', methods=['POST'])
@admin_required
def save_blog():
    """
    Saves a new blog post to the database.
    Expects a JSON payload with 'title' and 'content_md'.
    """
    data = request.get_json()
    if not data or 'title' not in data or 'content_md' not in data:
        return jsonify({"error": "无效的请求格式，需要'title'和'content_md'"}), 400

    title = data['title'].strip()
    content_md = data['content_md'].strip()

    if not title or not content_md:
        return jsonify({"error": "标题和内容不能为空"}), 400

    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    try:
        # Create a URL-friendly title
        url_title = title.lower().replace(' ', '-').replace('/', '-')
        # Remove any characters that are not safe for URLs
        url_title = ''.join(c for c in url_title if c.isalnum() or c == '-')

        new_blog = {
            "title": title,
            "url_title": url_title,
            "publication_date": datetime.now().strftime("%Y-%m-%d"),
            "created_at": datetime.now(),
            "md_last_updated": datetime.now(),
            "html_last_updated": None,
            "content_md": content_md,
            "content_html": None
        }

        result = db.blogs.insert_one(new_blog)
        logging.info(f"New blog post created with ID: {result.inserted_id}")

        return jsonify({"message": "文章保存成功", "blog_id": str(result.inserted_id)})
    except Exception as e:
        logging.error(f"[Admin API] Failed to save blog: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500
