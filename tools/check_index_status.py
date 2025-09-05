from datetime import datetime
import logging
import os
import sys

import dotenv

# 将项目根目录添加到Python路径的最前面，以优先导入项目内的模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from utils.core.database import get_db
from utils.university.search import VectorSearchEngine

dotenv.load_dotenv()

# 基本日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def check_university_status(university_name: str):
    """
    检查指定大学在MongoDB中的状态和在LlamaIndex中的索引状态。
    """
    if not university_name:
        logging.error("错误：请输入大学名称。")
        return

    logging.info(f"--- 开始检查大学: {university_name} ---")

    # 1. 检查 MongoDB
    logging.info("\n[步骤 1/2] 正在查询 MongoDB...")
    db = get_db()
    if db is None:
        logging.error("无法连接到 MongoDB。请检查数据库连接配置。")
        return

    university_doc = db.universities.find_one({"university_name": university_name})

    if not university_doc:
        logging.error(f"在 MongoDB 中未找到大学: {university_name}")
        return

    university_id = str(university_doc['_id'])
    last_modified_db = university_doc.get('last_modified')

    print(f"  - MongoDB 文档 ID: {university_id}")
    if isinstance(last_modified_db, datetime):
        print(f"  - MongoDB last_modified: {last_modified_db.isoformat()} (类型: {type(last_modified_db)})")
    else:
        print(f"  - MongoDB last_modified: {last_modified_db} (类型: {type(last_modified_db)})")

    # 2. 检查 LlamaIndex (ChromaDB)
    logging.info("\n[步骤 2/2] 正在查询 LlamaIndex/ChromaDB...")
    try:
        llama_integration = VectorSearchEngine()
        index_metadata = llama_integration.get_index_metadata(university_id)

        if not index_metadata:
            logging.warning("在 LlamaIndex 中未找到该大学的索引。 ")
            index_last_modified = None
        else:
            print(f"  - 索引元数据: {index_metadata}")
            index_last_modified = index_metadata.get('source_last_modified')

        print(f"  - 索引 source_last_modified: {index_last_modified} (类型: {type(index_last_modified)})")

    except Exception as e:
        logging.error(f"查询 LlamaIndex 时发生错误: {e}", exc_info=True)
        return

    # 3. 结论
    logging.info("\n--- 结论 ---")
    if not last_modified_db or not index_last_modified:
        print("  - 无法进行比较，因为一个或两个时间戳缺失。")
        if not index_last_modified:
            print("  - 建议：需要为该大学创建索引。 ")
        return

    # 转换时间戳进行比较
    try:
        db_time = last_modified_db
        index_time = datetime.fromisoformat(index_last_modified)

        if db_time > index_time:
            print(f"  - 发现差异！数据库版本 ({db_time.isoformat()}) 比索引版本 ({index_time.isoformat()}) 更新。")
            print("  - 结论：索引应该被更新，但程序未能触发更新。问题可能在 ChatManager 的比较逻辑中。")
        elif db_time < index_time:
            print(f"  - 发现异常！索引版本 ({index_time.isoformat()}) 比数据库版本 ({db_time.isoformat()}) 还要新。")
            print("  - 结论：这不应该发生，请检查系统时间或更新逻辑。 ")
        else:
            print(f"  - 时间戳一致。数据库版本和索引版本相同。({db_time.isoformat()})")
            print("  - 结论：如果问题仍然存在，说明问题与时间戳检查无关，可能在其他地方。")

    except Exception as e:
        print(f"  - 比较时间戳时出错: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        uni_name = sys.argv[1]
        check_university_status(uni_name)
    else:
        print("用法: python tools/check_index_status.py \"大学名称\"")
