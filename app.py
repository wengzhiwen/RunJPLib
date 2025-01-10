from flask import Flask, send_from_directory
from routes.index import index_route, university_route

app = Flask(__name__)

@app.route('/robots.txt')
def robots():
    return send_from_directory('static', 'robots.txt')

@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory('static', 'sitemap.xml')

# 首页路由
@app.route('/')
def index():
    return index_route()

# RESTful路由 - 大学详情页（中文版和原版）
# 新的路由格式：/university/<name>/<deadline>
from werkzeug.routing import BaseConverter

class DateConverter(BaseConverter):
    regex = r'[^/]+' # Match any characters except forward slash

app.url_map.converters['date'] = DateConverter

@app.route('/university/<name>/<date:deadline>')
def university_with_deadline(name, deadline):
    return university_route(name, deadline=deadline)

@app.route('/university/<name>/<date:deadline>/original')
def university_original_with_deadline(name, deadline):
    return university_route(name, deadline=deadline, original=True)

# 保留旧的路由格式以保持向后兼容
@app.route('/university/<name>')
def university(name):
    return university_route(name)

@app.route('/university/<name>/original')
def university_original(name):
    return university_route(name, original=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
