"""
处理首页和大学相关路由的模块。
"""
import os
import csv
import re
import logging
from collections import defaultdict

import markdown
from flask import render_template, make_response
from .blog import get_all_blogs, get_random_blogs_with_summary


class University:
    # pylint: disable=too-few-public-methods
    """大学信息类"""
    def __init__(self, name, deadline, zh_md_path, md_path, report_md_path):
        self.name = name
        self.deadline = deadline
        self.zh_md_path = zh_md_path
        self.md_path = md_path
        self.report_md_path = report_md_path


def get_all_universities() -> list[University]:
    """获取所有大学的信息"""
    base_dir = os.getenv("CONTENT_BASE_DIR", ".")
    pdf_dirs = [d for d in os.listdir(base_dir) if d.startswith("pdf_with_md")]

    universities = []

    # 从每个pdf_with_md文件夹中获取所有大学的信息
    for pdf_dir in pdf_dirs:
        # 获取其下的所有一级子文件夹（大学）
        sub_dirs = [
            d for d in os.listdir(pdf_dir)
            if os.path.isdir(os.path.join(pdf_dir, d))
        ]
        for sub_dir in sub_dirs:
            # 将子文件夹的名称按"_"split
            sub_dir_name = sub_dir.split("_")
            if len(sub_dir_name) < 2:
                logging.info("忽略子文件夹: %s 。文件夹名不含有\"_\"", sub_dir)
                continue
            # 获取大学名称
            university_name = sub_dir_name[0]
            # 获取报名截止日期
            deadline = sub_dir_name[1]
            # 对报名截止日进行格式化
            # 如果报名截止日是一串8位数字，则认为它是YYYYMMDD格式，需要转换为YYYY/MM/DD格式
            if len(deadline) == 8 and deadline.isdigit():
                deadline = f"{deadline[:4]}-{deadline[4:6]}-{deadline[6:]}"
            # 如果报名截止日是YYYY/MM/DD格式或YYYY-MM-DD格式，为了保证显示效果，需要统一为YYYY-MM-DD格式
            elif len(deadline) == 10:
                deadline = deadline.replace("/", "-")
                # 检查格式是否正确
                if not re.match(r"\d{4}-\d{2}-\d{2}", deadline):
                    logging.info("忽略子文件夹: %s。无法解析的报名截止日", sub_dir)
                    continue
            else:
                logging.info("忽略子文件夹: %s。无法解析的报名截止日", sub_dir)
                continue

            # 检查文件夹下是否存在"文件夹名.md"
            if not os.path.exists(
                    os.path.join(pdf_dir, sub_dir, f"{sub_dir}.md")):
                logging.info("忽略子文件夹: %s。文件夹下没有\"文件夹名.md\"文件", sub_dir)
                continue

            # 检查文件夹下是否存在"文件夹名_report.md"
            if not os.path.exists(
                    os.path.join(pdf_dir, sub_dir, f"{sub_dir}_report.md")):
                logging.info("忽略子文件夹: %s。文件夹下没有\"文件夹名_report.md\"文件", sub_dir)
                continue

            # 检查文件夹下是否存在"文件夹名_中文.md"
            if not os.path.exists(
                    os.path.join(pdf_dir, sub_dir, f"{sub_dir}_中文.md")):
                logging.info("忽略子文件夹: %s。文件夹下没有\"文件夹名_中文.md\"文件", sub_dir)
                continue

            # 这是一所完整的大学的信息
            universities.append({
                "name":
                university_name,
                "deadline":
                deadline,
                "zh_md_path":
                os.path.join(pdf_dir, sub_dir, f"{sub_dir}_中文.md"),
                "md_path":
                os.path.join(pdf_dir, sub_dir, f"{sub_dir}.md"),
                "report_md_path":
                os.path.join(pdf_dir, sub_dir, f"{sub_dir}_report.md"),
            })

    # 修改返回值，将字典转换为 University 对象
    return [
        University(
            name=u["name"],
            deadline=u["deadline"],
            zh_md_path=u["zh_md_path"],
            md_path=u["md_path"],
            report_md_path=u["report_md_path"],
        ) for u in universities
    ]


def get_sorted_universities() -> list[University]:
    """获取排序后的大学列表"""
    logging.debug("####get_sorted_universities####")

    best_universities = set()
    base_dir = os.getenv("CONTENT_BASE_DIR", ".")
    pdf_dirs = [d for d in os.listdir(base_dir) if d.startswith("pdf_with_md")]
    logging.debug("pdf_dirs: %s", pdf_dirs)

    # 从每个文件夹读取best_list.csv并合并
    for pdf_dir in pdf_dirs:
        best_list_path = os.path.join(pdf_dir, "best_list.csv")
        if os.path.exists(best_list_path):
            with open(best_list_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:  # 确保行不为空
                        best_universities.add(row[0])

    # 按是否为优质大学和报名日期进行排序
    def get_sort_key(univ: University):
        is_best = 1 if univ.name in best_universities else 0
        return (is_best, univ.deadline)

    universities = get_all_universities()
    universities.sort(key=get_sort_key, reverse=True)
    return universities


def load_categories() -> defaultdict:
    """
    加载大学分类信息，并根据实际文件存在情况标记链接状态
    
    :return: 包含分类信息的defaultdict
    """
    logging.debug("####load_categories####")
    categories = defaultdict(list)

    try:
        with open('data/university_categories.csv', 'r',
                  encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 检查必要字段是否存在且不为空
                required_fields = ['category', 'name', 'ja_name', 'url']
                if not all(row.get(field) for field in required_fields):
                    missing_fields = [field for field in required_fields if not row.get(field)]
                    logging.warning("CSV行缺少必要字段: %s", missing_fields)
                    continue

                # 从URL中提取大学名称和截止日期
                url_parts = row['url'].split('/')
                logging.debug("url_parts: %s", url_parts)
                if len(url_parts) >= 4:  # URL格式应该是 /university/大学名/截止日期
                    name = url_parts[2]
                    deadline = url_parts[3]
                    # 直接使用get_university_by_name_and_deadline检查
                    file_exists = get_university_by_name_and_deadline(
                        name, deadline) is not None
                else:
                    file_exists = False

                categories[row['category']].append({
                    'name':
                    row['name'],
                    'ja_name':
                    row['ja_name'],
                    'url':
                    row['url'],
                    'file_exists':
                    file_exists
                })
    except FileNotFoundError as e:
        logging.error("找不到大学分类数据文件: %s", e)
    except PermissionError as e:
        logging.error("没有权限访问大学分类数据文件: %s", e)
    except UnicodeDecodeError as e:
        logging.error("大学分类数据文件编码错误: %s", e)
    except csv.Error as e:
        logging.error("大学分类数据CSV格式错误: %s", e)
    except IOError as e:
        logging.error("读取大学分类数据时发生IO错误: %s", e)
    return categories


def index_route():
    """首页路由"""
    universities = get_sorted_universities()
    categories = load_categories()
    recommended_blogs = get_random_blogs_with_summary(3)
    return render_template("index.html",
                         universities=universities,
                         categories=categories,
                         recommended_blogs=recommended_blogs,
                         mode='index')


def get_university_by_name_and_deadline(name, deadline=None) -> University | None:
    """
    根据大学名称和报名截止日期获取信息

    :param name: 大学名称
    :param deadline: 报名截止日期（YYYY-MM-DD / YYYYMMDD / YYYY/MM/DD）
    :return: 大学信息
    """
    # 如果没有提供deadline，返回最新的大学信息
    if deadline is None:
        return get_latest_university_by_name(name)

    # 对报名截止日期进行格式化
    # 如果报名截止日是一串8位数字，则认为它是YYYYMMDD格式，需要转换为YYYY/MM/DD格式
    if len(deadline) == 8 and deadline.isdigit():
        deadline = f"{deadline[:4]}-{deadline[4:6]}-{deadline[6:]}"
    # 如果报名截止日是YYYY/MM/DD格式或YYYY-MM-DD格式，为了保证显示效果，需要统一为YYYY-MM-DD格式
    elif len(deadline) == 10:
        deadline = deadline.replace("/", "-")
        # 检查格式是否正确
        if not re.match(r"\d{4}-\d{2}-\d{2}", deadline):
            logging.info("无法解析的报名截止日：%s", deadline)
            return None
    else:
        logging.info("无法解析的报名截止日：%s", deadline)
        return None

    # 获取所有大学的信息
    universities = get_all_universities()

    # 根据大学名称和报名截止日期获取信息
    for university in universities:
        if university.name == name and university.deadline == deadline:
            return university

    return None


def get_latest_university_by_name(name):
    """
    根据大学名称获取最新的招生信息
    
    :param name: 大学名称
    :return: 最新的大学信息或None
    """
    universities = get_all_universities()
    matching_universities = [u for u in universities if u.name == name]
    
    if not matching_universities:
        return None
        
    # 按deadline降序排序，返回最新的
    return sorted(matching_universities, key=lambda x: x.deadline, reverse=True)[0]


def university_route(name, deadline=None, content="REPORT"):
    """
    处理单个大学的路由

    :param name: 大学名称
    :param deadline: 报名截止日期（可选）
    :param content: 要显示的内容（REPORT = 分析报告，ZH = 翻译件， ORIGINAL = 原版）
    """
    # 如果没有提供deadline，获取最新的信息
    if deadline is None:
        university = get_latest_university_by_name(name)
    else:
        university = get_university_by_name_and_deadline(name, deadline)

    if not university:
        error_msg = f"未找到{name}的招生信息"
        if deadline:
            error_msg = f"未找到{name}在{deadline}的招生信息"
        return (
            render_template("index.html",
                          error=error_msg,
                          universities=get_sorted_universities(),
                          categories=load_categories()),
            404,
        )

    # 读取并渲染markdown内容
    try:
        if content == "ORIGINAL":
            md_path = university.md_path
            template = "content_original.html"
        elif content == "ZH":
            md_path = university.zh_md_path
            template = "content.html"
        else:
            md_path = university.report_md_path
            template = "content_report.html"

        if not os.path.exists(md_path):
            return (
                render_template("index.html",
                              error=f"未找到{name}在{university.deadline}的{content}信息",
                              universities=get_sorted_universities(),
                              categories=load_categories()),
                404,
            )

        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        # 使用markdown库渲染内容
        md = markdown.Markdown(
            extensions=[
                'extra', 'tables', 'fenced_code', 'sane_lists', 'nl2br',
                'smarty'
            ],
            output_format="html5",
        )
        html_content = md.convert(md_content)

        universities = get_sorted_universities()

        return render_template(
            template,
            content=html_content,
            universities=universities,
            current_university=university.name,
            current_deadline=university.deadline,
        )

    except (FileNotFoundError, IOError, UnicodeDecodeError) as e:
        return (
            render_template("index.html",
                          error=f"文件操作错误: {str(e)}",
                          universities=get_sorted_universities()),
            500,
        )
    except Exception as e:
        return (
            render_template("index.html",
                          error=f"Markdown解析错误: {str(e)}",
                          universities=get_sorted_universities()),
            500,
        )


def sitemap_route():
    """sitemap路由处理函数"""
    base_url = os.getenv('BASE_URL', 'https://www.runjplib.com')
    response = make_response(
        render_template('sitemap.xml',
                       base_url=base_url,
                       blogs=get_all_blogs(),
                       universities=get_all_universities()))
    response.headers["Content-Type"] = "application/xml"
    return response
