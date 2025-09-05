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
from routes.chat import chat_bp
from routes.index import index_route
from routes.index import sitemap_route
from routes.index import university_route
from utils.db_indexes import ensure_indexes
from utils.mongo_client import get_db

load_dotenv()


def setup_logging():
    """配置日志系统"""
    # 确保log目录存在
    log_dir = os.getenv('LOG_DIR', 'log')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_level_env = os.getenv('LOG_LEVEL', 'INFO').upper()
    app_log_level = getattr(logging, log_level_env, logging.INFO)

    # 获取根logger并设置级别
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 清除现有处理器，避免重复日志
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 文件处理器 - 根据环境调整日志文件大小
    max_bytes = int(os.getenv('LOG_MAX_BYTES', '10485760'))  # 默认10MB
    backup_count = int(os.getenv('LOG_BACKUP_COUNT', '50'))

    file_handler = RotatingFileHandler(os.path.join(log_dir, 'app.log'), maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    file_handler.setLevel(app_log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 控制台处理器 - 仅在非生产环境时启用
    is_production_log = log_level_env == 'INFO'
    if not is_production_log or os.getenv('ENABLE_CONSOLE_LOG', 'false').lower() == 'true':
        console_handler = logging.StreamHandler()
        console_handler.setLevel(app_log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # 减少其他库的日志噪音
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    logging.getLogger('flask').setLevel(logging.INFO)

    # 控制pymongo日志级别
    pymongo_level_str = os.getenv('PYMONGO_LOG_LEVEL', 'INFO').upper()
    pymongo_level = getattr(logging, pymongo_level_str, logging.INFO)
    logging.getLogger('pymongo').setLevel(pymongo_level)


def create_app(_config_name=None):
    """应用工厂函数"""
    flask_app = Flask(__name__)

    # 环境检测 - 使用LOG_LEVEL判断生产环境
    log_level_app = os.getenv('LOG_LEVEL', 'INFO').upper()
    is_production_mode = log_level_app == 'INFO'

    # 基础配置
    flask_app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', '104857600'))  # 默认100MB

    # JWT配置 - 生产环境安全检查
    jwt_secret = os.getenv("JWT_SECRET_KEY")
    if is_production_mode and (not jwt_secret or jwt_secret == "super-secret"):
        raise ValueError("JWT_SECRET_KEY must be set to a secure value in production")

    flask_app.config["JWT_SECRET_KEY"] = jwt_secret or "super-secret"
    flask_app.config["JWT_TOKEN_LOCATION"] = ["headers", "cookies"]

    # CSRF保护 - 生产环境建议启用
    if is_production_mode:
        flask_app.config["JWT_COOKIE_CSRF_PROTECT"] = os.getenv('JWT_CSRF_PROTECT', 'true').lower() == 'true'
    else:
        flask_app.config["JWT_COOKIE_CSRF_PROTECT"] = False

    flask_app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=int(os.getenv('JWT_EXPIRES_DAYS', '7')))

    # 初始化JWT
    JWTManager(flask_app)

    # 注册蓝图
    flask_app.register_blueprint(admin_bp)
    flask_app.register_blueprint(chat_bp)

    # 注册路由
    register_routes(flask_app)

    # 注册错误处理器
    register_error_handlers(flask_app)

    # 初始化应用 - 确保数据库索引存在
    with flask_app.app_context():
        try:
            if ensure_indexes():
                logging.info("数据库索引已就绪")
            else:
                logging.warning("数据库索引未能创建或确保，请检查日志")
        except Exception as e:
            logging.error(f"初始化数据库索引失败: {e}", exc_info=True)

    return flask_app


def register_routes(flask_app):
    """注册所有路由"""
    # 注册日期转换器
    flask_app.url_map.converters['date'] = DateConverter

    @flask_app.route('/robots.txt')
    def robots():
        """robots.txt路由"""
        return send_from_directory('static', 'robots.txt')

    @flask_app.route('/sitemap.xml')
    def sitemap():
        """sitemap.xml路由"""
        return sitemap_route()

    @flask_app.route('/favicon.svg')
    def favicon():
        """favicon.svg路由"""
        return send_from_directory('static', 'favicon.svg')

    @flask_app.route('/BingSiteAuth.xml')
    def bing_site_auth():
        """Bing站点验证文件路由"""
        file_dir = 'static'
        file_name = 'BingSiteAuth.xml'
        file_path = os.path.join(file_dir, file_name)
        if not os.path.isfile(file_path):
            abort(404)
        return send_from_directory(file_dir, file_name)

    @flask_app.route('/')
    def index():
        """首页路由"""
        return index_route()

    @flask_app.route('/university/<name>/<date:deadline>')
    @flask_app.route('/university/<name>/<date:deadline>/')
    def university_report_with_deadline(name, deadline):
        """大学详情页路由"""
        return university_route(name, deadline=deadline, content="REPORT")

    @flask_app.route('/university/<name>/<date:deadline>/original')
    @flask_app.route('/university/<name>/<date:deadline>/original/')
    def university_original_with_deadline(name, deadline):
        """大学详情页路由"""
        return university_route(name, deadline=deadline, content="ORIGINAL")

    @flask_app.route('/university/<name>/<date:deadline>/zh')
    @flask_app.route('/university/<name>/<date:deadline>/zh/')
    def university_zh_with_deadline(name, deadline):
        """大学详情页路由"""
        return university_route(name, deadline=deadline, content="ZH")

    @flask_app.route('/university/<name>')
    @flask_app.route('/university/<name>/')
    def university_report(name):
        """大学详情页路由 - 最新报告"""
        return university_route(name, content="REPORT")

    @flask_app.route('/university/<name>/original')
    @flask_app.route('/university/<name>/original/')
    def university_original(name):
        """大学详情页路由 - 最新原文"""
        return university_route(name, content="ORIGINAL")

    @flask_app.route('/university/<name>/zh')
    @flask_app.route('/university/<name>/zh/')
    def university_zh(name):
        """大学详情页路由 - 最新翻译"""
        return university_route(name, content="ZH")

    @flask_app.route('/university/<name>/chat/api/<path:endpoint>', methods=['GET', 'POST'])
    @flask_app.route('/university/<name>/<date:deadline>/chat/api/<path:endpoint>', methods=['GET', 'POST'])
    def university_chat_api(name, endpoint, deadline=None):
        """大学聊天API路由"""
        from routes.university_chat import handle_university_chat_api
        return handle_university_chat_api(name, endpoint, deadline)

    @flask_app.route('/blog')
    @flask_app.route('/blog/')
    def blog_list():
        """博客列表路由"""
        return blog_list_route()

    @flask_app.route('/blog/<title>')
    @flask_app.route('/blog/<title>/')
    def blog_detail(title):
        """博客详情路由"""
        return blog_detail_route(title)

    @flask_app.route('/pdf/resource/<resource_id>')
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
                # 设置缓存，缓存一天
                response.headers['Cache-Control'] = 'public, max-age=86400'

                send_start_time = time.time()
                logging.debug(f"准备发送PDF数据，大小: {len(pdf_data) / 1024:.2f} KB。从收到请求到开始发送共耗时: {send_start_time - start_time:.4f} 秒。")
                return response

            except Exception as e:
                logging.error(f"从GridFS获取PDF文件失败: {e}")
                abort(404)

        abort(404)

    # 向后兼容的路由
    @flask_app.route('/pdf/mongo/<item_id>')
    def serve_pdf_from_mongo_legacy(item_id):
        """向后兼容的MongoDB PDF服务路由（已弃用）"""
        logging.warning(f"使用了已弃用的PDF路由: /pdf/mongo/{item_id}")
        return serve_pdf_from_resource(item_id)

    # 健康检查端点
    @flask_app.route('/health')
    def health_check():
        """健康检查端点"""
        try:
            db = get_db()
            if db is None:
                return {"status": "unhealthy", "database": "disconnected"}, 503

            # 简单的数据库连接测试
            db.admin.command('ismaster')
            return {"status": "healthy", "database": "connected"}, 200
        except Exception as e:
            logging.error(f"健康检查失败: {e}")
            return {"status": "unhealthy", "error": str(e)}, 503


def register_error_handlers(flask_app):
    """注册错误处理器"""

    @flask_app.errorhandler(404)
    def not_found(_error):
        """404错误处理"""
        return {"error": "Not Found", "message": "The requested resource was not found"}, 404

    @flask_app.errorhandler(500)
    def internal_error(_error):
        """500错误处理"""
        logging.error(f"Internal server error: {_error}")
        return {"error": "Internal Server Error", "message": "An internal error occurred"}, 500

    @flask_app.errorhandler(413)
    def request_entity_too_large(_error):
        """文件过大错误处理"""
        return {"error": "Request Entity Too Large", "message": "File size exceeds limit"}, 413


class DateConverter(BaseConverter):
    """日期转换器"""
    regex = r'[^/]+'  # 匹配除斜杠外的任何字符


# 创建应用实例 - 用于Gunicorn
app = create_app()


# 初始化应用 - 仅在直接运行时执行
def init_app():
    """初始化应用"""
    setup_logging()
    logging.debug("日志系统配置完成。")
    logging.info("应用启动中...")
    # 注意：数据库索引初始化已移至 create_app() 函数中


if __name__ == '__main__':
    # 开发环境直接运行
    init_app()

    # 启动应用
    if os.getenv('FLASK_APP_PORT') and os.getenv('FLASK_APP_PORT').isdigit():
        app_port = int(os.getenv('FLASK_APP_PORT'))
    else:
        logging.warning("FLASK_APP_PORT未设置，使用默认端口5000")
        app_port = 5000

    log_level_startup = os.getenv('LOG_LEVEL', 'INFO').upper()
    is_production_startup = log_level_startup == 'INFO'
    if not is_production_startup:
        app.run(debug=True, host='0.0.0.0', port=app_port, threaded=True)
    else:
        app.run(host='0.0.0.0', port=app_port, threaded=True)
