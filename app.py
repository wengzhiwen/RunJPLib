"""
Flask应用主文件
"""
import logging
import os

from dotenv import load_dotenv
from flask import Flask, send_from_directory
from werkzeug.routing import BaseConverter

from routes.index import index_route, university_route, sitemap_route
from routes.blog import blog_list_route, blog_detail_route


app = Flask(__name__)


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


if __name__ == '__main__':
    load_dotenv()

    # 设定日志配置
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'DEBUG'),
        format=
        '%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s'
    )
    logging.debug("日志配置完成，准备启动应用")

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
