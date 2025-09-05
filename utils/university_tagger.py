from datetime import datetime
import json
import logging
import os

from agents import Agent
from agents import Runner
from bson import ObjectId
from dotenv import load_dotenv

from utils.mongo_client import get_db

# Use a standard logger for file-based logging, not for task-specific DB logging.
file_logger = logging.getLogger(__name__)


class UniversityTagger:
    """
    A class to tag universities using an LLM.
    """

    def __init__(self, task_id):
        """
        Initializes the UniversityTagger.
        Args:
            task_id (str): The ID of the task being executed.
        """
        load_dotenv()
        self.task_id = task_id
        self.db = get_db()
        self.universities_collection = self.db.universities
        self.tasks_collection = self.db.processing_tasks

        self.model = os.getenv("OPENAI_TAGGER_MODEL", "gpt-4o-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            self._log_message("OPENAI_API_KEY environment variable not set.", "ERROR")
            raise ValueError("OpenAI API key not set.")
        os.environ["OPENAI_MAX_RETRIES"] = "0"

    def _log_message(self, message: str, level: str = "INFO"):
        """记录日志消息到数据库和文件。"""
        timestamp = datetime.utcnow()
        log_entry = {"timestamp": timestamp, "level": level, "message": message}

        # 写入任务数据库日志
        try:
            self.tasks_collection.update_one({"_id": ObjectId(self.task_id)}, {"$push": {"logs": log_entry}})
        except Exception as e:
            file_logger.error(f"[Tagger-{self.task_id}] Failed to write log to DB: {e}")

        # 同时写入文件日志
        full_message = f"[Tagger-{self.task_id}] {message}"
        if level == "ERROR":
            file_logger.error(full_message)
        elif level == "WARNING":
            file_logger.warning(full_message)
        else:
            file_logger.info(full_message)

    def run_tagging_process(self):
        """
        Runs the complete university tagging process.
        """
        self._log_message("Starting university tagging process...")
        try:
            # 1. Fetch universities from DB
            universities = self._get_all_universities()
            if not universities:
                self._log_message("No universities found to tag. Aborting.", "WARNING")
                self._update_task_status("completed", summary="No universities to process.")
                return

            self._log_message(f"Fetched {len(universities)} universities from the database.")

            # 2. Construct the prompt
            prompt = self._construct_prompt(universities)
            self._log_message("Constructed prompt for LLM.")

            # 3. Call the LLM
            self._log_message(f"Sending request to LLM model: {self.model}. This may take a while...")
            llm_response_str = self._call_llm(prompt)
            self._log_message("Received response from LLM.")

            # 4. Parse the response
            try:
                new_tags_data = self._parse_response(llm_response_str)
            except json.JSONDecodeError as e:
                self._log_message(f"Failed to parse LLM response as JSON: {e}", "ERROR")
                self._log_message(f"LLM Response: \n{llm_response_str}", "ERROR")
                raise

            # 5. Update universities in DB
            summary = self._update_universities(new_tags_data)

            self._log_message("University tagging process finished successfully.")
            self._update_task_status("completed", summary=summary)

        except Exception as e:
            self._log_message(f"An error occurred during the tagging process: {e}", "ERROR")
            self._update_task_status("failed", error_message=str(e))

    def _update_task_status(self, status: str, error_message: str = None, summary: dict = None):
        """Updates the task status in the database."""
        try:
            update_doc = {"$set": {"status": status, "updated_at": datetime.utcnow()}}
            if error_message:
                update_doc["$set"]["error_message"] = error_message
            if summary:
                update_doc["$set"]["result_summary"] = summary

            self.tasks_collection.update_one({"_id": ObjectId(self.task_id)}, update_doc)
        except Exception as e:
            self._log_message(f"Failed to update task status for task {self.task_id}: {e}", "ERROR")

    def _get_all_universities(self):
        """
        Fetches all universities from the database.
        """
        universities = list(self.universities_collection.find({}, {"university_name": 1, "tags": 1, "_id": 0}))
        # Ensure 'tags' field exists
        for uni in universities:
            if 'tags' not in uni:
                uni['tags'] = []
        return universities

    def _construct_prompt(self, universities):
        """
        Constructs the prompt for the LLM.
        """
        # The system prompt is part of the main prompt string
        prompt_template = """
あなたは日本の大学事情に精通した専門家です。以下の大学リストに基づき、それぞれの大学に最も的確なタグを1～5個付与してください。これらのタグはユーザーに直接表示されるため、分かりやすく一般的な言葉を選んでください。

# 指示
- 各大学に1から5個のタグを付与してください。
- タグは日本の大学に関する一般的な分類（例：「国立」「公立」「私立」「難関」「GMARCH」「関関同立」「女子大」「理系名門」など）を使用してください。
- 既存のタグが付与されている大学については、そのタグを参考にし、変更は慎重に行ってください。不必要にタグを削除しないでください。
- 出力は必ず指定されたJSON形式に従ってください。

# 大学リスト
{university_list_json}

# 出力形式 (JSON)
{{
  "universities": [
    {{
      "university_name": "大学の日本語名",
      "tags": ["タグ1", "タグ2", ...]
    }}
  ]
}}
"""
        university_list_json = json.dumps(universities, ensure_ascii=False, indent=2)
        return prompt_template.format(university_list_json=university_list_json)

    def _call_llm(self, prompt: str) -> str:
        """
        Calls the LLM using the agents library and returns the response string.
        """
        # The prompt contains all instructions, so we use a minimal system prompt for the Agent.
        agent = Agent(name="university_tagger_agent", model=self.model, instructions="You are a helpful assistant.")
        input_items = [{"role": "user", "content": prompt}]
        try:
            result = Runner.run_sync(agent, input_items)
            if not result or not result.final_output:
                raise Exception("Agent returned no content.")
            return result.final_output
        except Exception as e:
            self._log_message(f"Agent execution failed: {e}", "ERROR")
            if "429" in str(e):
                self._log_message("Rate limit error detected.", "ERROR")
            raise e

    def _parse_response(self, response_str: str) -> list:
        """
        Parses the JSON response from the LLM.
        """
        try:
            # The response might be wrapped in ```json ... ```, so we extract it.
            if response_str.strip().startswith("```json"):
                response_str = response_str.strip()[7:-3].strip()

            data = json.loads(response_str)
            return data.get("universities", [])
        except json.JSONDecodeError as e:
            self._log_message(f"Failed to decode JSON. Raw response snippet: {response_str[:500]}", "ERROR")
            raise e

    def _update_universities(self, new_tags_data) -> dict:
        """
        Updates the universities in the database with new tags.
        Returns a summary of the tags.
        """
        updated_count = 0
        tag_summary = {}

        for uni_data in new_tags_data:
            uni_name = uni_data.get("university_name")
            new_tags = uni_data.get("tags", [])

            if not uni_name:
                self._log_message("Found university data with no name in LLM response. Skipping.", "WARNING")
                continue

            # For now, we update tags for all universities received from LLM
            result = self.universities_collection.update_one({"university_name": uni_name}, {"$set": {"tags": new_tags}})

            if result.modified_count > 0:
                updated_count += 1
                self._log_message(f"Updated tags for '{uni_name}': {new_tags}")
            elif result.matched_count > 0:
                # This means the tags were the same, so no update happened, which is fine.
                pass
            else:
                self._log_message(f"University '{uni_name}' from LLM response not found in DB. Skipping.", "WARNING")

            for tag in new_tags:
                tag_summary[tag] = tag_summary.get(tag, 0) + 1

        self._log_message(f"Updated {updated_count} universities.")
        self._log_message("--- Tag Summary ---")

        # Sort summary by count descending
        sorted_summary = sorted(tag_summary.items(), key=lambda item: item[1], reverse=True)

        summary_log = []
        for tag, count in sorted_summary:
            log_line = f"{tag}: {count} universities"
            self._log_message(log_line)
            summary_log.append(log_line)

        return {"updated_universities": updated_count, "total_universities_processed": len(new_tags_data), "tag_distribution": dict(sorted_summary)}


if __name__ == '__main__':
    # For local testing
    logging.basicConfig(level=logging.INFO)
    tagger = UniversityTagger("test_task_id")
    tagger.run_tagging_process()
