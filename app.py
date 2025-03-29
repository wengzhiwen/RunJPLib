from flask import Flask, send_from_directory, render_template
from routes.index import index_route, university_route, sitemap_route
import logging
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)


@app.route('/robots.txt')
def robots():
    return send_from_directory('static', 'robots.txt')


@app.route('/sitemap.xml')
def sitemap():
    return sitemap_route()


@app.route('/favicon.svg')
def favicon():
    return send_from_directory('static', 'favicon.svg')


# 首页路由
@app.route('/')
def index():
    return index_route()


# RESTful路由 - 大学详情页（中文版和原版）
# 新的路由格式：/university/<name>/<deadline>
from werkzeug.routing import BaseConverter


class DateConverter(BaseConverter):
    regex = r'[^/]+'  # Match any characters except forward slash


app.url_map.converters['date'] = DateConverter


@app.route('/university/<name>/<date:deadline>')
def university_report_with_deadline(name, deadline):
    return university_route(name, deadline=deadline, content="REPORT")


@app.route('/university/<name>/<date:deadline>/original')
def university_original_with_deadline(name, deadline):
    return university_route(name, deadline=deadline, content="ORIGINAL")


@app.route('/university/<name>/<date:deadline>/zh')
def university_zh_with_deadline(name, deadline):
    return university_route(name, deadline=deadline, content="ZH")


# 保留旧的路由格式以保持向后兼容
@app.route('/university/<n>')
def university(name):
    return university_route(name)


if __name__ == '__main__':
    # 设定日志配置
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'DEBUG'),
        format=
        '%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s'
    )
    logging.debug("日志配置完成，准备启动应用")

    # 启动应用
    app.run(debug=True, host='0.0.0.0', port=os.getenv('FLASK_APP_PORT', 5000))
