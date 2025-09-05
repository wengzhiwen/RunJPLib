# -*- coding: utf-8 -*-
"""
该脚本用于一次性将 MongoDB 中 'universities' 集合内的 'deadline' 字段
从字符串类型（例如 "20250101"）迁移到 BSON 的 Date 类型。

请在使用前务必备份您的数据库！
"""
from datetime import datetime
import os
import sys

import dotenv

dotenv.load_dotenv()

# 将项目根目录添加到 sys.path，以便导入 utils 包
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

try:
    from utils.mongo_client import get_mongo_client
except ImportError:
    print("错误：无法从 utils.mongo_client 导入 get_mongo_client。")
    print("请确保脚本位于项目的 'tools' 目录下，并且项目根目录结构正确。")
    sys.exit(1)


def migrate_deadlines():
    """
    执行数据迁移任务。
    """
    client = get_mongo_client()
    if not client:
        print("错误：无法连接到 MongoDB。请检查您的数据库连接配置。")
        return

    db = client.RunJPLib
    universities_collection = db.universities

    # 只查找 deadline 字段是字符串类型的文档
    query = {"deadline": {"$type": "string"}}

    # 使用投影只获取必要字段，减少网络开销
    projection = {"_id": 1, "deadline": 1, "university_name": 1}

    docs_to_migrate = list(universities_collection.find(query, projection))

    if not docs_to_migrate:
        print("数据库中没有找到需要迁移的 'deadline' 字段（字符串类型）。")
        return

    print(f"找到 {len(docs_to_migrate)} 个文档需要迁移。")

    updated_count = 0
    error_count = 0

    for doc in docs_to_migrate:
        deadline_str = doc.get("deadline")
        doc_id = doc["_id"]
        uni_name = doc.get("university_name", "N/A")

        if not deadline_str or not isinstance(deadline_str, str):
            continue

        parsed_date = None
        # 尝试多种可能的日期格式
        # 格式 1: YYYYMMDD
        if len(deadline_str) == 8 and deadline_str.isdigit():
            try:
                parsed_date = datetime.strptime(deadline_str, "%Y%m%d")
            except ValueError:
                pass  # 格式不匹配，继续尝试下一种

        # 格式 2: YYYY-MM-DD (或其他分隔符)
        if not parsed_date:
            try:
                # 替换常见分隔符
                cleaned_str = deadline_str.replace('-', '').replace('/', '')
                if len(cleaned_str) == 8 and cleaned_str.isdigit():
                    parsed_date = datetime.strptime(cleaned_str, "%Y%m%d")
            except (ValueError, AttributeError):
                pass

        if parsed_date:
            try:
                result = universities_collection.update_one({"_id": doc_id}, {"$set": {"deadline": parsed_date}})
                if result.modified_count > 0:
                    print(f"  [成功] ID: {doc_id}, 大学: {uni_name}, '{deadline_str}' -> {parsed_date.strftime('%Y-%m-%d')}")
                    updated_count += 1
                else:
                    print(f"  [警告] ID: {doc_id}, 大学: {uni_name}, 文档未被修改，可能已被其他进程更新。")

            except Exception as e:
                print(f"  [失败] ID: {doc_id}, 大学: {uni_name}, 更新时出错: {e}")
                error_count += 1
        else:
            print(f"  [跳过] ID: {doc_id}, 大学: {uni_name}, 无法解析日期字符串: '{deadline_str}'")
            error_count += 1

    print("\n迁移完成。")
    print(f"总计: {len(docs_to_migrate)} 个文档")
    print(f"成功更新: {updated_count} 个")
    print(f"失败/跳过: {error_count} 个")


if __name__ == "__main__":
    print("=" * 50)
    print("开始将 'deadline' 字段从 String 迁移到 Date 类型...")
    print("重要提示：在运行此脚本前，请务必备份您的数据库！")
    print("=" * 50)

    # 在实际执行前暂停，给用户确认的机会
    if input("您确定要继续吗？ (yes/no): ").lower() != 'yes':
        print("操作已取消。")
        sys.exit(0)

    migrate_deadlines()
