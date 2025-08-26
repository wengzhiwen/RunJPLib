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
