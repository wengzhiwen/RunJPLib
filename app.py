from flask import Flask
from routes.index import index_route, university_route

app = Flask(__name__)

# 首页路由
@app.route('/')
def index():
    return index_route()

# RESTful路由 - 大学详情页（中文版和原版）
@app.route('/university/<name>')
def university(name):
    return university_route(name)

@app.route('/university/<name>/original')
def university_original(name):
    return university_route(name, original=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
