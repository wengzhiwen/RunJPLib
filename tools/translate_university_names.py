import os
import sys

from dotenv import load_dotenv

# 将项目根目录添加到Python路径的开头，以确保优先导入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents import Agent
from agents import Runner
from pymongo.collection import Collection

from utils.mongo_client import get_db


def translate_names_batch(names: list[str]) -> dict[str, str]:
    """
    批量翻译大学名称，使用AI将给定的日文名称翻译成简体中文。
    
    Args:
        names: 需要翻译的日文名称列表
        
    Returns:
        翻译结果字典，键为日文名称，值为中文名称
    """
    if not names:
        return {}

    print(f"正在批量翻译 {len(names)} 个大学名称...")

    # 创建一个专门用于翻译的Agent
    translator_agent = Agent(name="Translator_Agent",
                             instructions="你是一个专业的翻译引擎，请将用户提供的日本大学名称准确地翻译成简体中文。用户会提供多个大学名称，请按照以下格式返回结果：每个大学名称占一行，格式为'日文名称:中文名称'。只返回翻译结果，不要包含任何额外的解释或文字。",
                             model=os.getenv("OPENAI_TRANSLATE_MODEL", "gpt-4o"))

    # 将所有名称组合成一个输入
    combined_names = "\n".join(names)
    input_items = [{"role": "user", "content": f"请翻译以下日本大学名称：\n{combined_names}"}]

    try:
        result = Runner.run_sync(translator_agent, input_items)
        translated_text = result.final_output.strip()

        # 解析翻译结果
        translations = {}
        for line in translated_text.split('\n'):
            line = line.strip()
            if ':' in line:
                japanese, chinese = line.split(':', 1)
                japanese = japanese.strip()
                chinese = chinese.strip()
                if japanese and chinese:
                    translations[japanese] = chinese

        print(f"成功翻译 {len(translations)} 个名称")
        return translations

    except Exception as e:
        print(f"批量翻译时出错: {e}")
        return {}


def main():
    """
    主函数，用于执行大学名称增量翻译和数据库更新。
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

    # 查找所有没有中文名称的大学
    universities_without_chinese = list(
        universities_collection.find({"$or": [{
            "university_name_zh": {
                "$exists": False
            }
        }, {
            "university_name_zh": ""
        }, {
            "university_name_zh": None
        }]}))

    total = len(universities_without_chinese)

    if total == 0:
        print("所有大学都已经有中文名称，无需翻译。")
        return

    print(f"找到 {total} 所大学需要翻译中文名称。")

    # 提取日文名称和对应的文档ID
    japanese_names_with_ids = []
    for uni in universities_without_chinese:
        japanese_name = uni.get("university_name")
        if japanese_name:
            japanese_names_with_ids.append((japanese_name, uni["_id"]))
        else:
            print(f"警告: _id 为 {uni['_id']} 的文档缺少 'university_name' 字段，已跳过。")

    if not japanese_names_with_ids:
        print("没有找到需要翻译的大学名称。")
        return

    # 提取日文名称用于翻译
    japanese_names = [name for name, _ in japanese_names_with_ids]

    # 批量翻译
    translations = translate_names_batch(japanese_names)

    if not translations:
        print("翻译失败，无法更新数据库。")
        return

    # 更新数据库
    updated_count = 0
    for japanese_name, chinese_name in translations.items():
        # 找到对应的文档ID
        doc_id = None
        for name, doc_id_val in japanese_names_with_ids:
            if name == japanese_name:
                doc_id = doc_id_val
                break

        if doc_id is None:
            print(f"警告: 未找到 '{japanese_name}' 对应的文档ID，跳过更新")
            continue

        try:
            result = universities_collection.update_one({"_id": doc_id}, {"$set": {"university_name_zh": chinese_name}})
            if result.modified_count > 0:
                updated_count += 1
                print(f"成功更新 '{japanese_name}' -> '{chinese_name}'")
            else:
                print(f"警告: 更新失败，文档ID: {doc_id}")
        except Exception as e:
            print(f"更新数据库时出错 '{japanese_name}': {e}")

    print(f"翻译完成！成功更新了 {updated_count} 所大学的中文名称。")


if __name__ == "__main__":
    main()
