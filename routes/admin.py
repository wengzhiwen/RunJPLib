import os
import glob
import logging
import re
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, make_response
from flask_jwt_extended import create_access_token, get_jwt_identity, unset_jwt_cookies, verify_jwt_in_request
from utils.mongo_client import get_mongo_client
from bson.binary import Binary
import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder='../templates/admin')

# Define the absolute path to the project's root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
            identity = get_jwt_identity()
            if identity != 'admin':
                logging.warning("在Token中发现非管理员身份。")
                return jsonify(msg="需要管理员权限"), 403
        except Exception as e:
            logging.warning(f"JWT 验证失败: {e}")
            return jsonify(msg="Token无效或已过期"), 401
            
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route('/')
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
    access_code = data.get('access_code')

    if not access_code or access_code != os.getenv('ACCESS_CODE'):
        return jsonify({"msg": "访问码错误"}), 401

    access_token = create_access_token(identity="admin")
    return jsonify(access_token=access_token)


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
        # Standardize the deadline format to YYYYMMDD before saving
        deadline = deadline_raw.replace('-', '').replace('/', '')

        # Define required files for text content first
        required_files = {
            "original_md": os.path.join(univ_dir, f"{dir_name}.md"),
            "translated_md": os.path.join(univ_dir, f"{dir_name}_中文.md"),
            "report_md": os.path.join(univ_dir, f"{dir_name}_report.md"),
        }

        # --- PDF File Handling ---
        pdf_path = os.path.join(univ_dir, f"{dir_name}.pdf")
        if not os.path.exists(pdf_path):
            pdf_files = glob.glob(os.path.join(univ_dir, '*.pdf'))
            if len(pdf_files) == 1:
                pdf_path = pdf_files[0]
                logging.info(f"未找到完全匹配的PDF，但找到了唯一的PDF文件，将使用: {os.path.basename(pdf_path)}")
            else:
                logging.warning(f"跳过目录 {dir_name}，因为找不到完全匹配的PDF，且目录中包含 {len(pdf_files)} 个PDF文件。")
                continue
        
        # Add the found PDF path to the required files dict
        required_files["original_pdf"] = pdf_path
        # --- End of PDF File Handling ---

        # Now, check for all required files together
        missing_files = [key for key, path in required_files.items() if not os.path.exists(path)]
        if missing_files:
            logging.warning(f"跳过目录 {dir_name}，因为缺少文件: {', '.join(missing_files)}")
            continue

        doc = {
            "university_name": univ_name,
            "deadline": deadline, # Use the standardized deadline
            "created_at": datetime.datetime.utcnow(),
            "source_path": univ_dir,
            "content": {}
        }

        try:
            with open(required_files["original_md"], 'r', encoding='utf-8') as f:
                doc['content']['original_md'] = f.read()
            with open(required_files["translated_md"], 'r', encoding='utf-8') as f:
                doc['content']['translated_md'] = f.read()
            with open(required_files["report_md"], 'r', encoding='utf-8') as f:
                doc['content']['report_md'] = f.read()
            with open(required_files["original_pdf"], 'rb') as f:
                doc['content']['original_pdf'] = Binary(f.read())

            universities_collection.update_one(
                {"university_name": univ_name, "deadline": deadline}, # Use standardized deadline
                {"$set": doc},
                upsert=True
            )
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

            doc = {
                "title": title,
                "url_title": url_title,
                "publication_date": pub_date,
                "created_at": datetime.datetime.utcnow(),
                "source_file": file_name,
                "content_md": content
            }

            blogs_collection.update_one({"source_file": file_name}, {"$set": doc}, upsert=True)
            logging.info(f"成功上传/更新博客: {file_name}")
            count += 1
        except Exception as e:
            logging.error(f"处理 {file_name} 时发生错误: {e}")

    logging.info(f"博客数据上传完成。共处理 {total_files} 个文件，成功上传 {count} 篇博客。")
    return jsonify({"message": f"成功上传了 {count} 篇博客文章。"})


# --- Data Management APIs ---
@admin_bp.route('/api/universities', methods=['GET'])
@admin_required
def get_universities():
    client = get_mongo_client()
    if not client: return jsonify({"error": "数据库连接失败"}), 500
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
    from bson.objectid import ObjectId
    client = get_mongo_client()
    if not client: return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    db.universities.delete_one({'_id': ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route('/api/universities', methods=['DELETE'])
@admin_required
def clear_universities():
    client = get_mongo_client()
    if not client: return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    db.universities.delete_many({})
    return jsonify({"message": "数据集合已清空"})


@admin_bp.route('/api/blogs', methods=['GET'])
@admin_required
def get_blogs():
    client = get_mongo_client()
    if not client: return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    cursor = db.blogs.find({}, {"content_md": 0}).sort("publication_date", -1)

    blogs = []
    for b in cursor:
        b['_id'] = str(b['_id'])
        blogs.append(b)

    return jsonify(blogs)


@admin_bp.route('/api/blogs/<item_id>', methods=['DELETE'])
@admin_required
def delete_blog(item_id):
    from bson.objectid import ObjectId
    client = get_mongo_client()
    if not client: return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    db.blogs.delete_one({'_id': ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route('/api/blogs', methods=['DELETE'])
@admin_required
def clear_blogs():
    client = get_mongo_client()
    if not client: return jsonify({"error": "数据库连接失败"}), 500
    db = client.RunJPLib

    db.blogs.delete_many({})
    return jsonify({"message": "数据集合已清空"})