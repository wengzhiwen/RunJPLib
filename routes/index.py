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

def index_route():
    # 读取index.csv文件
    universities = []
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            universities.append({
                'name': row['university_name'],
                'deadline': row['deadline'],
                'zh_md_path': row['zh_md_path']
            })
    
    # 按报名日期排序
    universities.sort(key=lambda x: x['deadline'])
    
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

def get_university_by_name(name):
    """根据大学名称获取信息"""
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['university_name'] == name:
                return row
    return None

def university_route(name, original=False):
    """处理单个大学的路由"""
    university = get_university_by_name(name)
    if not university:
        return render_template('index.html', error="未找到该大学信息"), 404
        
    # 读取并渲染markdown内容
    try:
        md_path = university['md_path'] if original else university['zh_md_path']
        full_path = os.path.join('pdf_with_md', md_path)
        
        if not os.path.exists(full_path):
            return render_template('index.html', error="未找到该大学的详细信息"), 404
            
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
        
        # 读取所有大学列表用于侧边栏
        universities = []
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                universities.append({
                    'name': row['university_name'],
                    'deadline': row['deadline'],
                    'zh_md_path': row['zh_md_path']
                })
        
        # 按报名日期排序
        universities.sort(key=lambda x: x['deadline'])
        
        template = 'content_original.html' if original else 'content.html'
        return render_template(template, 
                             content=html_content, 
                             universities=universities,
                             current_university=name)
        
    except Exception as e:
        return render_template('index.html', error=str(e)), 500

def get_md_content(university_name):
    """获取原版markdown内容"""
    university = get_university_by_name(university_name)
    if not university:
        return jsonify({'error': '未找到该大学信息'}), 404
        
    try:
        full_path = os.path.join('pdf_with_md', md_path)
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
