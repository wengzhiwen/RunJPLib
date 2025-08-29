"""
Flask应用主文件
"""
from datetime import timedelta
import logging
from logging.handlers import RotatingFileHandler
import os
import time

from bson.objectid import ObjectId
from dotenv import load_dotenv
from flask import abort
from flask import Flask
from flask import make_response
from flask import send_from_directory
from flask_jwt_extended import JWTManager
from gridfs import GridFS
from werkzeug.routing import BaseConverter

from routes.admin import admin_bp
from routes.blog import blog_detail_route
from routes.blog import blog_list_route
from routes.index import index_route
from routes.index import sitemap_route
from routes.index import university_route
from utils.db_indexes import ensure_indexes
from utils.mongo_client import get_db

load_dotenv()


def setup_logging():
    """配置日志系统"""
    # 确保log目录存在
    if not os.path.exists('log'):
        os.makedirs('log')

    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # 获取根logger并设置级别
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 清除现有处理器，避免重复日志
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 文件处理器
    file_handler = RotatingFileHandler(
        'log/app.log',
        maxBytes=1024 * 1024,  # 1MB
        backupCount=10,
        encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 减少其他库的日志噪音
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    logging.getLogger('flask').setLevel(logging.INFO)

    # 控制pymongo日志级别
    pymongo_level_str = os.getenv('PYMONGO_LOG_LEVEL', 'INFO').upper()
    pymongo_level = getattr(logging, pymongo_level_str, logging.INFO)
    logging.getLogger('pymongo').setLevel(pymongo_level)


app = Flask(__name__)

# 设置文件上传大小限制 (100MB)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# 配置Flask-JWT-Extended
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret")
# 设置JWT在headers和cookies中均可找到
app.config["JWT_TOKEN_LOCATION"] = ["headers", "cookies"]
# 为简化管理面板的API调用，禁用CSRF保护
app.config["JWT_COOKIE_CSRF_PROTECT"] = False
# 为方便管理员操作，设置访问令牌7天后过期
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=7)
jwt = JWTManager(app)

# 注册蓝图
app.register_blueprint(admin_bp)


@app.route('/robots.txt')
def robots():
    """robots.txt路由"""
    return send_from_directory('static', 'robots.txt')


@app.route('/sitemap.xml')
def sitemap():
    """sitemap.xml路由"""
    return sitemap_route()


@app.route('/favicon.svg')
def favicon():
    """favicon.svg路由"""
    return send_from_directory('static', 'favicon.svg')


@app.route('/BingSiteAuth.xml')
def bing_site_auth():
    """Bing站点验证文件路由"""
    file_dir = 'static'
    file_name = 'BingSiteAuth.xml'
    file_path = os.path.join(file_dir, file_name)
    if not os.path.isfile(file_path):
        abort(404)
    return send_from_directory(file_dir, file_name)


@app.route('/')
def index():
    """首页路由"""
    return index_route()


class DateConverter(BaseConverter):
    """日期转换器"""
    regex = r'[^/]+'  # 匹配除斜杠外的任何字符


app.url_map.converters['date'] = DateConverter


@app.route('/university/<name>/<date:deadline>')
@app.route('/university/<name>/<date:deadline>/')
def university_report_with_deadline(name, deadline):
    """大学详情页路由"""
    return university_route(name, deadline=deadline, content="REPORT")


@app.route('/university/<name>/<date:deadline>/original')
@app.route('/university/<name>/<date:deadline>/original/')
def university_original_with_deadline(name, deadline):
    """大学详情页路由"""
    return university_route(name, deadline=deadline, content="ORIGINAL")


@app.route('/university/<name>/<date:deadline>/zh')
@app.route('/university/<name>/<date:deadline>/zh/')
def university_zh_with_deadline(name, deadline):
    """大学详情页路由"""
    return university_route(name, deadline=deadline, content="ZH")


@app.route('/university/<name>')
@app.route('/university/<name>/')
def university_report(name):
    """大学详情页路由 - 最新报告"""
    return university_route(name, content="REPORT")


@app.route('/university/<name>/original')
@app.route('/university/<name>/original/')
def university_original(name):
    """大学详情页路由 - 最新原文"""
    return university_route(name, content="ORIGINAL")


@app.route('/university/<name>/zh')
@app.route('/university/<name>/zh/')
def university_zh(name):
    """大学详情页路由 - 最新翻译"""
    return university_route(name, content="ZH")


@app.route('/blog')
@app.route('/blog/')
def blog_list():
    """博客列表路由"""
    return blog_list_route()


@app.route('/blog/<title>')
@app.route('/blog/<title>/')
def blog_detail(title):
    """博客详情路由"""
    return blog_detail_route(title)


@app.route('/pdf/resource/<resource_id>')
def serve_pdf_from_resource(resource_id):
    """通过GridFS提供PDF文件，并记录性能日志"""
    start_time = time.time()
    logging.debug(f"PDF请求已收到: {resource_id}")

    db = get_db()
    if db is None:
        abort(404)

    try:
        obj_id = ObjectId(resource_id)
    except Exception:
        abort(404)

    query_start_time = time.time()
    # 查找大学文档，获取PDF文件ID
    doc = db.universities.find_one({'_id': obj_id}, {'content.pdf_file_id': 1, 'university_name': 1, 'deadline': 1})
    query_end_time = time.time()
    logging.debug(f"MongoDB查询耗时: {query_end_time - query_start_time:.4f} 秒")

    if doc and 'content' in doc and 'pdf_file_id' in doc['content']:
        pdf_file_id = doc['content']['pdf_file_id']
        deadline = doc.get('deadline', 'unknown')

        # 从GridFS获取PDF文件
        fs = GridFS(db)
        try:
            grid_out = fs.get(pdf_file_id)

            pdf_data = grid_out.read()

            response = make_response(pdf_data)
            response.headers['Content-Type'] = 'application/pdf'

            # 使用安全的ASCII文件名，避免HTTP头编码问题和缓存冲突
            safe_filename = f"university_{resource_id}_{deadline}.pdf"

            # 尝试从GridFS元数据获取原始文件名，仅用于日志记录
            try:
                original_filename = grid_out.metadata.get('original_filename', '')
                if original_filename:
                    logging.debug(f"原始文件名: {original_filename}")
            except Exception as e:
                logging.error(f"获取元数据失败: {e}")

            response.headers['Content-Disposition'] = f'inline; filename="{safe_filename}"'
            response.headers['Access-Control-Allow-Origin'] = '*'

            send_start_time = time.time()
            logging.debug(f"准备发送PDF数据，大小: {len(pdf_data) / 1024:.2f} KB。从收到请求到开始发送共耗时: {send_start_time - start_time:.4f} 秒。")
            return response

        except Exception as e:
            logging.error(f"从GridFS获取PDF文件失败: {e}")
            abort(404)

    abort(404)


# 向后兼容的路由
@app.route('/pdf/mongo/<item_id>')
def serve_pdf_from_mongo_legacy(item_id):
    """向后兼容的MongoDB PDF服务路由（已弃用）"""
    logging.warning(f"使用了已弃用的PDF路由: /pdf/mongo/{item_id}")
    return serve_pdf_from_resource(item_id)


if __name__ == '__main__':
    setup_logging()
    logging.debug("日志系统配置完成。")
    logging.info("应用启动中...")

    # 确保数据库索引存在
    try:
        if ensure_indexes():
            logging.info("数据库索引已就绪")
        else:
            logging.warning("数据库索引未能创建或确保，请检查日志")
    except Exception as e:
        logging.error(f"初始化数据库索引失败: {e}", exc_info=True)

    # 启动应用
    if os.getenv('FLASK_APP_PORT') and os.getenv('FLASK_APP_PORT').isdigit():
        app_port = int(os.getenv('FLASK_APP_PORT'))
    else:
        logging.warning("FLASK_APP_PORT未设置，使用默认端口5000")
        app_port = 5000

    if os.getenv('LOG_LEVEL') == 'DEBUG':
        app.run(debug=True, host='0.0.0.0', port=app_port, threaded=True)
    else:
        app.run(host='0.0.0.0', port=app_port, threaded=True)
