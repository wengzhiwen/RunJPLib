"""
博客路由模块
"""
import glob
import os
import re
from datetime import datetime
import random

import markdown
from flask import render_template, abort


def get_all_blogs():
    """获取所有博客列表"""
    blogs = []
    blog_files = glob.glob('blogs/*.md')
    for file in blog_files:
        filename = os.path.basename(file)
        if not os.path.getsize(file):  # 跳过空文件
            continue

        # 从文件名中提取标题和日期
        match = re.match(r'(.+)_(\d{14})\.md$', filename)
        if not match:
            continue

        title = match.group(1)
        date_str = match.group(2)

        # 将日期字符串转换为datetime对象
        date = datetime.strptime(date_str, '%Y%m%d%H%M%S')

        blogs.append({
            'id': filename[:-3],  # 移除.md后缀
            'title': title,
            'date': date.strftime('%Y-%m-%d'),
            'datetime': date,
            'md_path': file  # 添加文件路径
        })

    # 按日期降序排序
    return sorted(blogs, key=lambda x: x['datetime'], reverse=True)


def get_blog_by_id(blog_id):
    """获取特定博客内容"""
    file_path = f'blogs/{blog_id}.md'
    if not os.path.exists(file_path) or not os.path.getsize(file_path):
        return None

    # 从blog_id中提取标题和日期
    match = re.match(r'(.+)_(\d{14})$', blog_id)
    if not match:
        return None

    title = match.group(1)
    date_str = match.group(2)

    # 将日期字符串转换为datetime对象
    date = datetime.strptime(date_str, '%Y%m%d%H%M%S')

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 使用与大学信息相同的markdown处理方式
        md = markdown.Markdown(
            extensions=['extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br', 'smarty'],
            output_format="html5",
        )
        html_content = md.convert(md_content)

        return {'id': blog_id, 'title': title, 'date': date.strftime('%Y-%m-%d'), 'content': html_content}
    except (FileNotFoundError, IOError, UnicodeDecodeError) as e:
        abort(500, description=f"文件操作错误: {str(e)}")
    except Exception as e:
        abort(500, description=f"Markdown解析错误: {str(e)}")


def get_random_blogs(n=10):
    """获取n篇随机博客"""
    all_blogs = get_all_blogs()
    return random.sample(all_blogs, min(n, len(all_blogs)))


def get_random_blogs_with_summary(count=3):
    """获取指定数量的随机博客，并生成摘要
    
    Args:
        count: 需要获取的博客数量
        
    Returns:
        list: 包含博客信息的列表，每个博客包含id、title和summary
    """
    all_blogs = get_all_blogs()
    if not all_blogs:
        return []
        
    # 随机选择指定数量的博客
    selected_blogs = random.sample(all_blogs, min(count, len(all_blogs)))
    
    result = []
    for blog in selected_blogs:
        try:
            # 读取博客内容
            with open(blog['md_path'], 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 移除Markdown标记
            # 首先将内容转换为HTML
            md = markdown.Markdown(extensions=['extra'])
            html_content = md.convert(content)
            
            # 移除HTML标签
            text_content = re.sub(r'<[^>]+>', '', html_content)
            
            # 生成摘要（取前100个字符）
            summary = text_content[:100].strip() + '...' if len(text_content) > 100 else text_content
            
            result.append({
                'id': blog['id'],
                'title': blog['title'],
                'summary': summary
            })
        except Exception as e:
            # 如果处理某篇博客出错，跳过它
            continue
            
    return result


def blog_list_route():
    """博客列表路由处理函数"""
    blogs = get_all_blogs()
    
    # 如果有博客文章，随机选择一篇作为默认显示
    if blogs:
        random_blog = random.choice(blogs)
        return blog_detail_route(random_blog['id'])
    
    # 如果没有博客文章，显示404页面并推荐其他博客
    recommended_blogs = get_random_blogs(10)
    return render_template('404.html', mode='blog', blogs=blogs, recommended_blogs=recommended_blogs), 404


def blog_detail_route(blog_id):
    """博客详情路由处理函数"""
    blog = get_blog_by_id(blog_id)
    if blog is None:
        # 获取10篇随机推荐的博客
        recommended_blogs = get_random_blogs(10)
        return render_template('404.html', mode='blog', blogs=get_all_blogs(), recommended_blogs=recommended_blogs), 404
        
    return render_template(
        'content.html',  # 使用与大学信息相同的模板
        mode='blog',
        blogs=get_all_blogs(),
        content=blog['content'],
        current_blog=blog['title'],
        current_blog_date=blog['date'])
