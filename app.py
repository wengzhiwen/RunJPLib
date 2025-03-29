from flask import Flask, send_from_directory, render_template
from routes.index import index_route, university_route, sitemap_route, get_sorted_universities
import logging
from dotenv import load_dotenv
import os
import csv
from collections import defaultdict
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
    universities = get_sorted_universities()
    categories = defaultdict(list)
    
    try:
        # 从CSV文件加载分类信息，独立于文件系统
        with open('data/university_categories.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            required_fields = {'category', 'name', 'ja_name', 'url'}
            
            # 检查CSV文件是否包含所有必需字段
            if not required_fields.issubset(reader.fieldnames):
                missing_fields = required_fields - set(reader.fieldnames)
                logging.error(f"CSV文件缺少必需字段: {missing_fields}")
                return render_template('index.html', 
                                    universities=universities, 
                                    categories=categories,
                                    error="大学分类数据格式不正确")
            
            for row_num, row in enumerate(reader, start=2):
                try:
                    # 验证必需字段不为空
                    if not all(row[field] for field in required_fields):
                        logging.warning(f"第{row_num}行存在空字段")
                        continue
                    
                    # 检查文件是否存在
                    file_exists = False
                    for uni in universities:
                        if uni.name == row['name']:
                            file_exists = True
                            break
                    
                    categories[row['category']].append({
                        'name': row['name'],
                        'ja_name': row['ja_name'],
                        'url': row['url'],
                        'file_exists': file_exists
                    })
                except KeyError as e:
                    logging.error(f"第{row_num}行缺少字段: {e}")
                    continue
                except Exception as e:
                    logging.error(f"处理第{row_num}行时发生错误: {e}")
                    continue
                    
    except FileNotFoundError:
        logging.error("找不到大学分类数据文件: data/university_categories.csv")
        return render_template('index.html', 
                             universities=universities, 
                             categories=categories,
                             error="大学分类数据文件不存在")
    except csv.Error as e:
        logging.error(f"CSV文件格式错误: {e}")
        return render_template('index.html', 
                             universities=universities, 
                             categories=categories,
                             error="大学分类数据格式不正确")
    except Exception as e:
        logging.error(f"读取大学分类数据时发生未知错误: {e}")
        return render_template('index.html', 
                             universities=universities, 
                             categories=categories,
                             error="读取大学分类数据时发生错误")
    
    return render_template('index.html', universities=universities, categories=categories)

# RESTful路由 - 大学详情页（中文版和原版）
# 新的路由格式：/university/<name>/<deadline>
from werkzeug.routing import BaseConverter

class DateConverter(BaseConverter):
    regex = r'[^/]+' # Match any characters except forward slash

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
@app.route('/university/<name>')
def university(name):
    return university_route(name)

def load_universities():
    # 用于导航的大学列表
    universities = []
    # 用于快速索引的分类数据
    categories = defaultdict(list)
    
    with open('data/university_categories.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            university = {
                'name': row['name'],
                'ja_name': row['ja_name'],
                'short_name': row['short_name'],
                'deadline': row['deadline'],
                'url': row['url']
            }
            # 添加到导航列表
            universities.append(university)
            # 添加到分类索引
            categories[row['category']].append(university)
    
    # 对导航列表按名称排序
    universities.sort(key=lambda x: x['name'])
    
    return universities, categories

if __name__ == '__main__':
    # 设定日志配置
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'DEBUG'),
        format='%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s'
    )
    logging.debug("日志配置完成，准备启动应用")
    
    # 启动应用
    app.run(debug=True, host='0.0.0.0', port=os.getenv('FLASK_APP_PORT', 5000))
