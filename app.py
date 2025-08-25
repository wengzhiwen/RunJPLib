"""
Flask应用主文件
"""
import logging
import os
import io
import time
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from flask import Flask, send_from_directory, abort, send_file, make_response
from werkzeug.routing import BaseConverter
from flask_jwt_extended import JWTManager

from bson.objectid import ObjectId
from utils.mongo_client import get_mongo_client

from routes.index import index_route, university_route, sitemap_route, serve_pdf
from routes.blog import blog_list_route, blog_detail_route
from routes.admin import admin_bp


load_dotenv()

# 配置日志
def setup_logging():
    """配置日志系统"""
    # 确保log目录存在
    if not os.path.exists('log'):
        os.makedirs('log')

    # 1. 从环境变量获取日志级别，默认为INFO
    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # 2. 获取根logger并设置其级别为最低（DEBUG），以捕获所有消息
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 3. 清除所有现有的处理器，以避免重复日志
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 4. 创建日志格式器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 5. 创建文件处理器 (INFO级别)
    file_handler = RotatingFileHandler(
        'log/app.log',
        maxBytes=1024 * 1024,  # 1MB
        backupCount=10,
        encoding='utf-8')
    file_handler.setLevel(log_level) # 文件日志级别也由env决定
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 6. 创建控制台处理器 (根据环境变量设置级别)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level) # 控制台日志级别由env决定
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 7. 将其他库的日志级别设置为INFO，以减少噪音
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    logging.getLogger('flask').setLevel(logging.INFO)



app = Flask(__name__)

# Setup the Flask-JWT-Extended extension
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret")  # Change this!
jwt = JWTManager(app)

# Register blueprints
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


# 首页路由
@app.route('/')
def index():
    """首页路由"""
    return index_route()


class DateConverter(BaseConverter):
    """日期转换器"""
    regex = r'[^/]+'  # Match any characters except forward slash


app.url_map.converters['date'] = DateConverter


# 大学相关路由 - 带deadline的完整路径
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


# 大学相关路由 - 简化路径（自动使用最新deadline）
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


# 博客相关路由
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


@app.route('/pdf/<name>/<date:deadline>')
def get_pdf_by_name_and_deadline(name, deadline):
    """PDF文件服务路由"""
    return serve_pdf(name, deadline)


@app.route('/pdf/mongo/<item_id>')
def serve_pdf_from_mongo(item_id):
    """Serve PDF from MongoDB with performance logging."""
    start_time = time.time()
    logging.debug(f"PDF请求已收到: {item_id}")

    client = get_mongo_client()
    if not client:
        abort(404)
    db = client.RunJPLib

    try:
        obj_id = ObjectId(item_id)
    except Exception:
        abort(404)

    query_start_time = time.time()
    doc = db.universities.find_one({'_id': obj_id}, {'content.original_pdf': 1})
    query_end_time = time.time()
    logging.debug(f"MongoDB查询耗时: {query_end_time - query_start_time:.4f} 秒")

    if doc and 'content' in doc and 'original_pdf' in doc['content']:
        pdf_data = doc['content']['original_pdf']
        
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={item_id}.pdf'
        response.headers['Access-Control-Allow-Origin'] = '*'
        
        send_start_time = time.time()
        logging.debug(f"准备发送PDF数据，大小: {len(pdf_data) / 1024:.2f} KB。从收到请求到开始发送共耗时: {send_start_time - start_time:.4f} 秒。")
        return response
    
    abort(404)


if __name__ == '__main__':
    # 设置日志配置
    setup_logging()
    logging.debug("日志系统配置完成，DEBUG级别已启用（如果env中设置）。")
    logging.info("应用启动中...")

    # 启动应用
    if os.getenv('FLASK_APP_PORT') and os.getenv('FLASK_APP_PORT').isdigit():
        app_port = int(os.getenv('FLASK_APP_PORT'))
    else:
        logging.warning("FLASK_APP_PORT未设置，使用默认端口5000")
        app_port = 5000

    if os.getenv('LOG_LEVEL') == 'DEBUG':
        app.run(debug=True, host='0.0.0.0', port=app_port)
    else:
        app.run(host='0.0.0.0', port=app_port)
