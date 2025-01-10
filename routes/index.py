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
                # 获取图片的完整路径
                img_path = os.path.join('pdf_with_md', src)
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

# Define csv_path as a constant since it's used in multiple functions
CSV_PATH = os.path.join('pdf_with_md', 'index.csv')

def get_sorted_universities():
    """获取排序后的大学列表"""
    universities = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
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

            # Convert deadline slashes to hyphens for display
            display_deadline = row['deadline'].replace('/', '-') if row['deadline'] else None
            universities.append({
                'name': row['university_name'],
                'deadline': display_deadline,
                'zh_md_path': row['zh_md_path']
            })
    
    # 按报名日期排序
    universities.sort(key=lambda x: x['deadline'])
    return universities

def index_route():
    """首页路由"""
    universities = get_sorted_universities()
    return render_template('index.html', universities=universities)

def process_html_img_tags(content):
    """处理HTML格式的img标签"""
    def replace_img(match):
        src = re.search(r'src=["\'](.*?)["\']', match.group(0))
        if src:
            src = src.group(1)
            if not src.startswith(('http://', 'https://')):
                img_path = os.path.join('pdf_with_md', src)
                if not os.path.exists(img_path):
                    return '<span>受技术限制，图片未能保留在当前文档中</span>'
        return match.group(0)
    
    # 匹配HTML格式的img标签
    img_pattern = r'<img[^>]+>'
    return re.sub(img_pattern, replace_img, content)

def get_university_by_name_and_deadline(name, deadline=None):
    """根据大学名称和截止日期获取信息"""
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['university_name'] == name:
                # 如果提供了deadline参数，需要精确匹配
                if deadline is not None:
                    if row['deadline'] == deadline:
                        return row
                    continue
                # 如果没有提供deadline，返回第一个匹配的大学名称的记录
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
        full_path = os.path.join('pdf_with_md', md_path)
        
        if not os.path.exists(full_path):
            return render_template('index.html', error="未找到该大学的详细信息", universities=get_sorted_universities()), 404
            
        with open(full_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # 处理HTML格式的img标签
        md_content = process_html_img_tags(md_content)
            
        # 使用markdown库渲染内容
        html_content = markdown.markdown(
            md_content,
            extensions=['tables', 'fenced_code', CustomImageExtension()],
            output_format='html5'
        )
        
        universities = get_sorted_universities()
        
        template = 'content_original.html' if original else 'content.html'
        # Convert deadline slashes to hyphens for display
        display_deadline = university['deadline'].replace('/', '-') if university['deadline'] else None
        return render_template(template, 
                             content=html_content, 
                             universities=universities,
                             current_university=name,
                             current_deadline=display_deadline)
        
    except Exception as e:
        return render_template('index.html', error=str(e), universities=get_sorted_universities()), 500

def get_md_content(university_name):
    """获取原版markdown内容"""
    university = get_university_by_name_and_deadline(university_name)
    if not university:
        return jsonify({'error': '未找到该大学信息'}), 404
        
    try:
        # 使用原文md_path
        full_path = os.path.join('pdf_with_md', university['md_path'])
        if not os.path.exists(full_path):
            return jsonify({'error': 'File not found'}), 404
            
        with open(full_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        print(f"Processing MD content with length: {len(md_content)}")
        print(f"MD content preview: {md_content[:200]}")  # 打印前200个字符
        
        # 先处理HTML格式的img标签
        md_content = process_html_img_tags(md_content)
            
        # 使用markdown库渲染内容，添加自定义图片处理扩展
        html_content = markdown.markdown(
            md_content,
            extensions=['tables', 'fenced_code', CustomImageExtension()],
            output_format='html5'
        )
        print(f"Generated HTML length: {len(html_content)}")
        return jsonify({'content': html_content})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
