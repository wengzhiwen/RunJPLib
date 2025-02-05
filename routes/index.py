import os
import csv
import markdown
import re
from flask import render_template, jsonify
from config import CONTENT_DIR
from markdown.inlinepatterns import ImageInlineProcessor, IMAGE_LINK_RE
from markdown.extensions import Extension
import logging

class CustomImageProcessor(ImageInlineProcessor):
    def handleMatch(self, m, data):
        el, start, end = super().handleMatch(m, data)
        if el is not None:
            src = el.get('src')
            # 检查是否是本地图片路径（不是http/https开头的URL）
            if not src.startswith(('http://', 'https://')):
                # 从markdown文件路径推断图片所在的文件夹
                md_dir = os.path.dirname(self.md.current_path) if hasattr(self.md, 'current_path') else 'pdf_with_md'
                # 获取图片的完整路径
                img_path = os.path.join(md_dir, src)
                if not os.path.exists(img_path):
                    # 如果图片不存在，替换为提示文字
                    el.tag = 'span'
                    el.text = '受技术限制，图片未能保留在当前文档中'
                    el.attrib.clear()  # 清除所有属性
        return el, start, end

class CustomImageExtension(Extension):
    def extendMarkdown(self, md):
        # 替换默认的图片处理器
        image_pattern = CustomImageProcessor(IMAGE_LINK_RE, md)
        md.inlinePatterns.register(image_pattern, 'image_link', 150)
        print("CustomImageExtension registered successfully")

def get_sorted_universities():
    """获取排序后的大学列表"""
    logging.debug("####get_sorted_universities####")
    
    best_universities = set()
    base_dir = os.getenv('CONTENT_BASE_DIR', '.')
    pdf_dirs = [d for d in os.listdir(base_dir) if d.startswith('pdf_with_md')]
    logging.debug(f"pdf_dirs: {pdf_dirs}")
    
    # 从每个文件夹读取best_list.csv并合并
    for pdf_dir in pdf_dirs:
        best_list_path = os.path.join(pdf_dir, 'best_list.csv')
        if os.path.exists(best_list_path):
            with open(best_list_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:  # 确保行不为空
                        best_universities.add(row[0])
    
    universities = []
    
    # 获取所有pdf_with_md开头的文件夹
    base_dir = os.getenv('CONTENT_BASE_DIR', '.')
    pdf_dirs = [d for d in os.listdir(base_dir) if d.startswith('pdf_with_md')]
    
    # 从每个文件夹读取index.csv
    for pdf_dir in pdf_dirs:
        csv_path = os.path.join(pdf_dir, 'index.csv')
        if not os.path.exists(csv_path):
            continue
            
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['university_name'] is None or len(row['university_name']) == 0:
                    print("大学名为空")
                    continue
                
                if row['deadline'] is None or len(row['deadline']) == 0:
                    print(f"报名截止日为空: {row['university_name']}")
                    continue

                if row['zh_md_path'] is None or len(row['zh_md_path']) == 0:
                    print(f"Markdown地址为空：{row['university_name'] } / {row['deadline'] }")
                    continue

                # 保存原始日期用于排序，并添加文件夹前缀到路径
                universities.append({
                    'name': row['university_name'],
                    'deadline': row['deadline'],  # 保存原始日期格式
                    'display_deadline': row['deadline'].replace('/', '-') if row['deadline'] else None,  # 用于显示的格式
                    'zh_md_path': os.path.join(pdf_dir, row['zh_md_path'])
                })
    
    # 按是否为优质大学和报名日期进行排序
    def get_sort_key(univ):
        is_best = 1 if univ['name'] in best_universities else 0
        deadline = univ['deadline']  # 使用原始日期格式进行排序
        if not deadline:
            return (is_best, '9999/99/99')  # 空值放最后
        # 检查是否符合YYYY/MM/DD格式
        if len(deadline.split('/')) == 3:
            try:
                year, month, day = map(int, deadline.split('/'))
                if 1900 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 31:
                    return (is_best, deadline)
            except ValueError:
                pass
        return (is_best, '9999/99/99')  # 非标准日期格式放最后
    
    universities.sort(key=get_sort_key, reverse=True)
    return universities

def index_route():
    """首页路由"""
    universities = get_sorted_universities()
    return render_template('index.html', universities=universities)

def process_html_img_tags(content, md_path=None):
    """处理HTML格式的img标签"""
    def replace_img(match):
        src = re.search(r'src=["\'](.*?)["\']', match.group(0))
        if src:
            src = src.group(1)
            if not src.startswith(('http://', 'https://')):
                # 从markdown文件路径推断图片所在的文件夹
                md_dir = os.path.dirname(md_path) if md_path else 'pdf_with_md'
                img_path = os.path.join(md_dir, src)
                if not os.path.exists(img_path):
                    return '<span>受技术限制，图片未能保留在当前文档中</span>'
        return match.group(0)
    
    # 匹配HTML格式的img标签
    img_pattern = r'<img[^>]+>'
    return re.sub(img_pattern, replace_img, content)

def get_university_by_name_and_deadline(name, deadline=None):
    """根据大学名称和截止日期获取信息"""
    # 获取所有pdf_with_md开头的文件夹
    base_dir = os.getenv('CONTENT_BASE_DIR', '.')
    pdf_dirs = [d for d in os.listdir(base_dir) if d.startswith('pdf_with_md')]
    
    for pdf_dir in pdf_dirs:
        csv_path = os.path.join(pdf_dir, 'index.csv')
        if not os.path.exists(csv_path):
            continue
            
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['university_name'] == name:
                    # 如果提供了deadline参数，需要精确匹配
                    if deadline is not None:
                        if row['deadline'] == deadline:
                            # 添加文件夹前缀到路径
                            row['zh_md_path'] = os.path.join(pdf_dir, row['zh_md_path'])
                            row['md_path'] = os.path.join(pdf_dir, row['md_path'])
                            return row
                        continue
                    # 如果没有提供deadline，返回第一个匹配的大学名称的记录
                    # 添加文件夹前缀到路径
                    row['zh_md_path'] = os.path.join(pdf_dir, row['zh_md_path'])
                    row['md_path'] = os.path.join(pdf_dir, row['md_path'])
                    return row
    return None

def university_route(name, deadline=None, original=False):
    """处理单个大学的路由"""
    # Convert hyphens back to slashes in the deadline
    if deadline:
        deadline = deadline.replace('-', '/')
    
    # 获取大学信息
    university = get_university_by_name_and_deadline(name, deadline)
    if not university:
        error_msg = f"未找到{name}的招生信息"
        if deadline:
            error_msg = f"未找到{name}在{deadline}的招生信息"
        return render_template('index.html', error=error_msg, universities=get_sorted_universities()), 404
        
    # 读取并渲染markdown内容
    try:
        md_path = university['md_path'] if original else university['zh_md_path']
        full_path = md_path  # 路径已经包含了文件夹前缀
        
        if not os.path.exists(full_path):
            return render_template('index.html', error="未找到该大学的详细信息", universities=get_sorted_universities()), 404
            
        with open(full_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # 处理HTML格式的img标签
        md_content = process_html_img_tags(md_content, full_path)
            
        # 使用markdown库渲染内容
        md = markdown.Markdown(
            extensions=['tables', 'fenced_code', CustomImageExtension()],
            output_format='html5'
        )
        # 设置当前处理的文件路径
        md.current_path = full_path
        html_content = md.convert(md_content)
        
        universities = get_sorted_universities()
        
        template = 'content_original.html' if original else 'content.html'
        return render_template(template, 
                             content=html_content, 
                             universities=universities,
                             current_university=name,
                             current_deadline=university['deadline'].replace('/', '-') if university['deadline'] else None)
        
    except Exception as e:
        return render_template('index.html', error=str(e), universities=get_sorted_universities()), 500

def get_md_content(university_name):
    """获取原版markdown内容"""
    university = get_university_by_name_and_deadline(university_name)
    if not university:
        return jsonify({'error': '未找到该大学信息'}), 404
        
    try:
        # 使用原文md_path，路径已经包含了文件夹前缀
        full_path = university['md_path']
        if not os.path.exists(full_path):
            return jsonify({'error': 'File not found'}), 404
            
        with open(full_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        print(f"Processing MD content with length: {len(md_content)}")
        print(f"MD content preview: {md_content[:200]}")  # 打印前200个字符
        
        # 先处理HTML格式的img标签
        md_content = process_html_img_tags(md_content, full_path)
            
        # 使用markdown库渲染内容，添加自定义图片处理扩展
        md = markdown.Markdown(
            extensions=['tables', 'fenced_code', CustomImageExtension()],
            output_format='html5'
        )
        # 设置当前处理的文件路径
        md.current_path = full_path
        html_content = md.convert(md_content)
        print(f"Generated HTML length: {len(html_content)}")
        return jsonify({'content': html_content})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
