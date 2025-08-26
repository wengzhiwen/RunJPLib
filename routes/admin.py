import os
import glob
import logging
import re
import datetime

from functools import wraps
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, make_response
from flask_jwt_extended import create_access_token, get_jwt_identity, set_access_cookies, unset_jwt_cookies, verify_jwt_in_request
from utils.mongo_client import get_mongo_client
from gridfs import GridFS
from bson import ObjectId

admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder='../templates/admin')

# Define the absolute path to the project's root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def admin_required(fn):
    """
    A decorator to protect admin routes.

    It differentiates between page loads and API requests.
    - For page loads, it redirects to the login page on auth failure.
    - For API requests, it returns a 401 JSON error on auth failure.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        is_api_request = request.path.startswith('/admin/api/')
        try:
            # Check for token in both headers and cookies
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
                # For page loads, redirect to login
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


@admin_bp.route('/api/university_folders')
@admin_required
def get_university_folders():
    search_path = os.path.join(PROJECT_ROOT, "pdf_with_md*")
    folders = [os.path.basename(p) for p in glob.glob(search_path)]
    return jsonify(folders)


@admin_bp.route('/api/upload/university', methods=['POST'])
@admin_required
def upload_university_data():
    data = request.get_json()
    folder_name = data.get('folder')
    folder_path = os.path.join(PROJECT_ROOT, folder_name)
    logging.info(f"开始处理大学数据上传，目标文件夹: {folder_path}")

    if not folder_name or not os.path.isdir(folder_path):
        logging.error(f"指定的文件夹无效或不存在: {folder_path}")
        return jsonify({"message": f"指定的文件夹无效: {folder_path}"}), 400

    client = get_mongo_client()
    if not client:
        logging.error("无法连接到 MongoDB。")
        return jsonify({"message": "无法连接到 MongoDB。"}), 500
    db = client.RunJPLib
    universities_collection = db.universities

    count = 0
    all_subdirs = glob.glob(os.path.join(folder_path, '*'))
    total_dirs = len([d for d in all_subdirs if os.path.isdir(d)])
    logging.info(f"在 {folder_name} 中找到 {total_dirs} 个子目录。")

    for univ_dir in all_subdirs:
        if not os.path.isdir(univ_dir):
            continue

        dir_name = os.path.basename(univ_dir)
        logging.info(f"正在处理目录: {dir_name}")

        parts = dir_name.split('_')
        if len(parts) != 2:
            logging.warning(f"跳过名称格式错误的目录: {dir_name}")
            continue

        univ_name, deadline_raw = parts
        deadline = deadline_raw.replace('-', '').replace('/', '')

        required_files = {
            "original_md": os.path.join(univ_dir, f"{dir_name}.md"),
            "translated_md": os.path.join(univ_dir, f"{dir_name}_中文.md"),
            "report_md": os.path.join(univ_dir, f"{dir_name}_report.md"),
        }

        pdf_path = os.path.join(univ_dir, f"{dir_name}.pdf")
        if not os.path.exists(pdf_path):
            pdf_files = glob.glob(os.path.join(univ_dir, '*.pdf'))
            if len(pdf_files) == 1:
                pdf_path = pdf_files[0]
                logging.info(f"未找到完全匹配的PDF，但找到了唯一的PDF文件，将使用: {os.path.basename(pdf_path)}")
            else:
                logging.warning(f"跳过目录 {dir_name}，因为找不到完全匹配的PDF，且目录中包含 {len(pdf_files)} 个PDF文件。")
                continue

        required_files["original_pdf"] = pdf_path

        missing_files = [key for key, path in required_files.items() if not os.path.exists(path)]
        if missing_files:
            logging.warning(f"跳过目录 {dir_name}，因为缺少文件: {', '.join(missing_files)}")
            continue

        doc = {"university_name": univ_name, "deadline": deadline, "source_path": univ_dir, "content": {}}

        try:
            with open(required_files["original_md"], 'r', encoding='utf-8') as f:
                doc['content']['original_md'] = f.read()
            with open(required_files["translated_md"], 'r', encoding='utf-8') as f:
                doc['content']['translated_md'] = f.read()
            with open(required_files["report_md"], 'r', encoding='utf-8') as f:
                doc['content']['report_md'] = f.read()

            fs = GridFS(db)
            existing_file = fs.find_one({"metadata.university_name": univ_name, "metadata.deadline": deadline})

            if existing_file:
                doc['content']['pdf_file_id'] = existing_file._id
                logging.info(f"PDF文件已存在，使用现有文件ID: {existing_file._id}")
            else:
                with open(required_files["original_pdf"], 'rb') as f:
                    file_id = fs.put(f,
                                     filename=str(ObjectId()),
                                     metadata={
                                         "university_name": univ_name,
                                         "deadline": deadline,
                                         "upload_time": datetime.datetime.now(datetime.timezone.utc),
                                         "original_filename": os.path.basename(pdf_path)
                                     })
                    doc['content']['pdf_file_id'] = file_id
                    logging.info(f"PDF文件已上传到GridFS，文件ID: {file_id}")

            update_query = {"university_name": univ_name, "deadline": deadline}
            update_data = {"$set": doc, "$setOnInsert": {"created_at": datetime.datetime.now(datetime.timezone.utc)}}
            universities_collection.update_one(update_query, update_data, upsert=True)
            logging.info(f"成功上传/更新大学数据: {dir_name}")
            count += 1
        except Exception as e:
            logging.error(f"处理 {dir_name} 时发生意外错误: {e}")

    logging.info(f"大学数据上传完成。共处理 {total_dirs} 个目录，成功上传 {count} 所大学。")
    return jsonify({"message": f"处理完成。在 {total_dirs} 个目录中，成功上传了 {count} 所大学的数据。"})


@admin_bp.route('/api/upload/blogs', methods=['POST'])
@admin_required
def upload_blog_data():
    logging.info("开始处理博客数据上传...")
    client = get_mongo_client()
    if not client:
        logging.error("无法连接到 MongoDB。")
        return jsonify({"message": "无法连接到 MongoDB。"}), 500
    db = client.RunJPLib
    blogs_collection = db.blogs

    count = 0
    search_path = os.path.join(PROJECT_ROOT, "blogs", "*.md")
    all_files = glob.glob(search_path)
    total_files = len(all_files)
    logging.info(f"在 blogs 目录中找到 {total_files} 个 Markdown 文件。")

    for md_file in all_files:
        file_name = os.path.basename(md_file)
        logging.info(f"正在处理文件: {file_name}")

        match = re.match(r'(.+)_(\d{14})\.md$', file_name)
        if not match:
            logging.warning(f"跳过名称格式错误的博客: {file_name}")
            continue

        title_part = match.group(1)
        date_str = match.group(2)

        try:
            dt_obj = datetime.datetime.strptime(date_str, '%Y%m%d%H%M%S')
            pub_date = dt_obj.strftime('%Y-%m-%d')
        except ValueError:
            logging.warning(f"跳过日期格式无效的博客: {file_name}")
            continue

        title = title_part.replace('_', ' ')
        url_title = title_part.lower()

        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            update_query = {"url_title": url_title}
            update_data = {
                "$set": {
                    "title": title,
                    "publication_date": pub_date,
                    "content_md": content,
                    "md_last_updated": datetime.datetime.now(datetime.timezone.utc)
                },
                "$setOnInsert": {
                    "created_at": datetime.datetime.now(datetime.timezone.utc)
                },
                "$unset": {
                    "source_file": ""
                }
            }

            blogs_collection.update_one(update_query, update_data, upsert=True)
            logging.info(f"成功上传/更新博客: {file_name}")
            count += 1
        except Exception as e:
            logging.error(f"处理 {file_name} 时发生错误: {e}")

    logging.info(f"博客数据上传完成。共处理 {total_files} 个文件，成功上传 {count} 篇博客。")
    return jsonify({"message": f"成功上传了 {count} 篇博客文章。"})


# --- Data Management Pages ---
@admin_bp.route('/manage/universities')
@admin_required
def manage_universities_page():
    """Renders the university management page."""
    return render_template('manage_universities.html')


@admin_bp.route('/manage/blogs')
@admin_required
def manage_blogs_page():
    """Renders the blog management page."""
    return render_template('manage_blogs.html')


# --- Data Management APIs ---
@admin_bp.route('/api/universities', methods=['GET'])
@admin_required
def get_universities():
    client = get_mongo_client()
    if not client:
        return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    cursor = db.universities.find({}, {"content": 0}).sort("university_name", 1)

    universities = []
    for u in cursor:
        u['_id'] = str(u['_id'])
        universities.append(u)

    return jsonify(universities)


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
            if md_last_updated and md_last_updated > html_last_updated:
                html_status = "待更新"
            else:
                html_status = "最新"

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
