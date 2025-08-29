import os
import sys

from dotenv import load_dotenv

# 将项目根目录添加到Python路径的开头，以确保优先导入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents import Agent
from agents import Runner
from pymongo.collection import Collection

from utils.mongo_client import get_db


def translate_name(name: str) -> str:
    """
    使用AI将给定的名称翻译成简体中文。
    """
    if not name:
        return ""

    print(f"正在翻译: {name}")

    # 创建一个专门用于翻译的Agent
    translator_agent = Agent(name="Translator_Agent", instructions="你是一个专业的翻译引擎，请将用户提供的日本大学名称准确地翻译成简体中文。只返回翻译后的中文名称，不要包含任何额外的解释或文字。", model="gpt-4o")

    input_items = [{"role": "user", "content": name}]

    try:
        result = Runner.run_sync(translator_agent, input_items)
        translated_name = result.final_output.strip()
        print(f"翻译结果: {translated_name}")
        return translated_name
    except Exception as e:
        print(f"翻译 '{name}' 时出错: {e}")
        return ""


def main():
    """
    主函数，用于执行大学名称翻译和数据库更新。
    """
    # 加载环境变量
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path=dotenv_path)

    if not os.getenv("OPENAI_API_KEY"):
        print("错误: OPENAI_API_KEY 环境变量未设置。请检查你的 .env 文件。")
        return

    db = get_db()
    if db is None:
        print("错误: 无法连接到 MongoDB。")
        return

    universities_collection: Collection = db.universities

    # 查找所有大学
    universities = list(universities_collection.find({}))
    total = len(universities)
    print(f"共找到 {total} 所大学需要处理。")

    for i, uni in enumerate(universities):
        japanese_name = uni.get("university_name")

        if not japanese_name:
            print(f"警告: _id 为 {uni['_id']} 的文档缺少 'university_name' 字段，已跳过。")
            continue

        print(f"--- 处理进度: {i+1}/{total} ---")
        chinese_name = translate_name(japanese_name)

        if chinese_name:
            # 更新数据库
            universities_collection.update_one({"_id": uni["_id"]}, {"$set": {"university_name_zh": chinese_name}})
            print(f"成功更新 '{japanese_name}' -> '{chinese_name}'")
        else:
            print(f"未能获取 '{japanese_name}' 的翻译，跳过数据库更新。")
        print("-" * 20)

    print("所有大学名称翻译和更新完成！")


if __name__ == "__main__":
    main()
