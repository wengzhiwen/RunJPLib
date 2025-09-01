"""
对话管理器
负责管理AI对话会话和消息处理
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from openai import OpenAI

from utils.llama_index_integration import LlamaIndexIntegration
from utils.university_document_manager import UniversityDocumentManager

logger = logging.getLogger(__name__)


class ChatSession:
    """对话会话类"""

    def __init__(self, session_id: str, university_id: str, university_name: str):
        self.session_id = session_id
        self.university_id = university_id
        self.university_name = university_name
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.messages = []  # 对话历史
        self.context_cache = {}  # 上下文缓存

    def add_message(self, role: str, content: str) -> None:
        """添加消息到会话"""
        message = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        self.messages.append(message)
        self.last_activity = datetime.now()

    def get_recent_messages(self, count: int = 6) -> List[Dict]:
        """获取最近的消息（用于上下文）"""
        return self.messages[-count:] if len(self.messages) > count else self.messages

    def is_expired(self, timeout_hours: int = 1) -> bool:
        """检查会话是否过期"""
        expire_time = self.last_activity + timedelta(hours=timeout_hours)
        return datetime.now() > expire_time

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "university_id": self.university_id,
            "university_name": self.university_name,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "message_count": len(self.messages),
        }


class ChatManager:
    """对话管理器"""

    def __init__(self):
        """初始化对话管理器"""
        # 检查OpenAI API密钥
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY环境变量未设置")

        # 初始化OpenAI客户端
        self.client = OpenAI(api_key=api_key)

        # 配置模型
        self.model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

        # 初始化依赖组件（懒加载）
        self.llama_index = None
        self.doc_manager = None

        # 会话管理
        self.sessions = {}  # session_id -> ChatSession
        self.session_timeout = int(os.getenv("CHAT_SESSION_TIMEOUT", "3600"))  # 秒

        logger.info("对话管理器初始化完成")

    def create_chat_session(self, university_id: str) -> Optional[ChatSession]:
        """
        创建对话会话

        Args:
            university_id: 大学ID

        Returns:
            ChatSession对象，如果创建失败则返回None
        """
        try:
            # 懒加载文档管理器
            if self.doc_manager is None:
                self.doc_manager = UniversityDocumentManager()

            # 获取大学信息
            university_doc = self.doc_manager.get_university_by_id(university_id)
            if not university_doc:
                logger.error(f"未找到大学 ID: {university_id}")
                return None

            university_name = university_doc.get("university_name", "未知大学")

            # 懒加载LlamaIndex集成器
            if self.llama_index is None:
                self.llama_index = LlamaIndexIntegration()

            # 检查是否已有索引，如果没有则创建
            index = self.llama_index.get_university_index(university_id)
            if not index:
                logger.info(f"为大学 {university_name} 创建索引")
                self.llama_index.create_university_index(university_doc)

            # 创建会话
            session_id = str(uuid.uuid4())
            session = ChatSession(session_id, university_id, university_name)

            # 存储会话
            self.sessions[session_id] = session

            logger.info(f"创建对话会话: {session_id} for {university_name}")
            return session

        except Exception as e:
            logger.error(f"创建对话会话时出错: {e}", exc_info=True)
            return None

    def restore_session_from_db(self, session_data: Dict) -> Optional[ChatSession]:
        """
        从数据库数据恢复会话

        Args:
            session_data: 数据库中的会话数据

        Returns:
            ChatSession对象，如果恢复失败则返回None
        """
        try:
            session_id = session_data.get("session_id")
            university_id = session_data.get("university_id")
            university_name = session_data.get("university_name")

            if not all([session_id, university_id, university_name]):
                logger.error(f"会话数据不完整: {session_data}")
                return None

            # 创建会话对象
            session = ChatSession(session_id, university_id, university_name)

            # 恢复会话时间信息
            if "start_time" in session_data:
                session.created_at = session_data["start_time"]
            if "last_activity" in session_data:
                session.last_activity = session_data["last_activity"]

            # 恢复聊天历史（只保留最近的消息）
            if "messages" in session_data and session_data["messages"]:
                # 转换数据库消息格式为标准格式
                formatted_messages = []
                for msg in session_data["messages"][-6:]:  # 只保留最近的6条消息
                    # 添加用户消息
                    if "user_input" in msg and msg["user_input"]:
                        formatted_messages.append(
                            {
                                "role": "user",
                                "content": msg["user_input"],
                                "timestamp": (
                                    msg.get("timestamp", datetime.now()).isoformat()
                                    if hasattr(msg.get("timestamp", datetime.now()), "isoformat")
                                    else str(msg.get("timestamp", datetime.now()))
                                ),
                            }
                        )

                    # 添加AI回复
                    if "ai_response" in msg and msg["ai_response"]:
                        formatted_messages.append(
                            {
                                "role": "assistant",
                                "content": msg["ai_response"],
                                "timestamp": (
                                    msg.get("timestamp", datetime.now()).isoformat()
                                    if hasattr(msg.get("timestamp", datetime.now()), "isoformat")
                                    else str(msg.get("timestamp", datetime.now()))
                                ),
                            }
                        )

                session.messages = formatted_messages

            # 存储到内存中
            self.sessions[session_id] = session

            logger.info(f"恢复对话会话: {session_id} for {university_name}")
            return session

        except Exception as e:
            logger.error(f"恢复对话会话时出错: {e}", exc_info=True)
            return None

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """
        获取对话会话

        Args:
            session_id: 会话ID

        Returns:
            ChatSession对象，如果不存在或已过期则返回None
        """
        session = self.sessions.get(session_id)
        if not session:
            return None

        # 检查是否过期
        if session.is_expired(self.session_timeout // 3600):
            self.cleanup_session(session_id)
            return None

        return session

    def process_message(self, session_id: str, user_message: str) -> Dict[str, Any]:
        """
        处理用户消息

        Args:
            session_id: 会话ID
            user_message: 用户消息

        Returns:
            包含AI回答的字典
        """
        try:
            # 获取会话
            session = self.get_session(session_id)
            if not session:
                return {"success": False, "error": "会话不存在或已过期", "error_code": "SESSION_NOT_FOUND"}

            logger.info(f"处理消息: {session_id} - {user_message[:50]}...")

            # 添加用户消息到会话
            session.add_message("user", user_message)

            # 确保LlamaIndex已初始化
            if self.llama_index is None:
                self.llama_index = LlamaIndexIntegration()

            # 检索相关文档
            relevant_docs = self.llama_index.search_university_content(
                university_id=session.university_id, query=user_message, top_k=5
            )

            # 构建上下文
            context = self._build_context(session, relevant_docs)

            # 构建提示词
            system_prompt = self._build_system_prompt(session.university_name)
            messages = self._build_messages(system_prompt, context, user_message, session)

            # 调用OpenAI API
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0.1, max_tokens=1000, top_p=0.9
            )

            # 提取AI回答
            ai_response = response.choices[0].message.content

            # 添加AI回答到会话
            session.add_message("assistant", ai_response)

            logger.info(f"AI回答生成完成: {session_id}")

            return {
                "success": True,
                "response": ai_response,
                "sources": [doc.get("metadata", {}) for doc in relevant_docs],
                "session_info": session.to_dict(),
            }

        except Exception as e:
            logger.error(f"处理消息时出错: {e}", exc_info=True)
            return {"success": False, "error": f"处理消息时出错: {str(e)}", "error_code": "PROCESSING_ERROR"}

    def get_session_history(self, session_id: str) -> Optional[List[Dict]]:
        """
        获取会话历史

        Args:
            session_id: 会话ID

        Returns:
            消息列表，如果会话不存在则返回None
        """
        session = self.get_session(session_id)
        if not session:
            return None

        return session.messages

    def clear_session_history(self, session_id: str) -> bool:
        """
        清空会话历史

        Args:
            session_id: 会话ID

        Returns:
            True如果成功，False如果会话不存在
        """
        session = self.get_session(session_id)
        if not session:
            return False

        session.messages = []
        session.context_cache = {}
        logger.info(f"清空会话历史: {session_id}")
        return True

    def cleanup_session(self, session_id: str) -> bool:
        """
        清理会话

        Args:
            session_id: 会话ID

        Returns:
            True如果成功，False如果会话不存在
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"清理会话: {session_id}")
            return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话

        Returns:
            清理的会话数量
        """
        expired_sessions = []
        for session_id, session in self.sessions.items():
            if session.is_expired(self.session_timeout // 3600):
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self.cleanup_session(session_id)

        if expired_sessions:
            logger.info(f"清理了 {len(expired_sessions)} 个过期会话")

        return len(expired_sessions)

    def get_active_sessions(self) -> List[Dict]:
        """
        获取活跃会话列表

        Returns:
            会话信息列表
        """
        active_sessions = []
        for session in self.sessions.values():
            if not session.is_expired(self.session_timeout // 3600):
                active_sessions.append(session.to_dict())

        return active_sessions

    def _build_context(self, session: ChatSession, relevant_docs: List[Dict]) -> str:
        """
        构建上下文

        Args:
            session: 对话会话
            relevant_docs: 相关文档列表

        Returns:
            构建的上下文字符串
        """
        context_parts = []

        # 添加相关文档片段
        if relevant_docs:
            context_parts.append("--- 相关文档信息 ---")
            for i, doc in enumerate(relevant_docs[:3]):  # 最多使用3个相关文档
                metadata = doc.get("metadata", {})
                content_type = metadata.get("content_type", "未知")
                title = metadata.get("title", f"文档片段 {i+1}")
                content = doc.get("content", "")

                context_parts.append(f"[{content_type}] {title}")
                context_parts.append(content[:500])  # 限制长度
                context_parts.append("")

        # 添加对话历史
        recent_messages = session.get_recent_messages(4)  # 最近2轮对话
        if recent_messages and len(recent_messages) > 2:
            context_parts.append("--- 对话历史 ---")
            for msg in recent_messages[:-1]:  # 排除当前消息
                role_name = "用户" if msg["role"] == "user" else "助手"
                context_parts.append(f"{role_name}: {msg['content']}")

        return "\n".join(context_parts)

    def _build_system_prompt(self, university_name: str) -> str:
        """
        构建系统提示词

        Args:
            university_name: 大学名称

        Returns:
            系统提示词
        """
        return f"""你是一位专业的日本大学招生信息咨询助手。

当前大学：{university_name}

你只能基于提供的大学信息来回答问题，不要编造任何信息。

注意事项：
1. 只回答与当前大学相关的问题
2. 如果信息不明确，请明确说明
3. 用中文回答
4. 保持专业、友好的语调
5. 拒绝回答与当前大学无关的问题
6. 如果用户询问其他大学的信息，请明确拒绝并说明只能回答{university_name}的相关问题
7. 如果没有相关信息，请诚实地说明没有找到相关信息

请根据提供的文档信息和对话历史来回答用户的问题。"""

    def _build_messages(self, system_prompt: str, context: str, user_message: str, session: ChatSession) -> List[Dict]:
        """
        构建消息列表

        Args:
            system_prompt: 系统提示词
            context: 上下文
            user_message: 用户消息
            session: 会话对象

        Returns:
            消息列表
        """
        messages = [{"role": "system", "content": system_prompt}]

        # 添加上下文（如果有）
        if context:
            messages.append({"role": "system", "content": f"相关信息：\n{context}"})

        # 添加对话历史（最近的消息）
        recent_messages = session.get_recent_messages(4)  # 获取最近4条消息作为上下文
        for msg in recent_messages:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # 添加当前用户消息
        messages.append({"role": "user", "content": user_message})

        return messages

    def get_stats(self) -> Dict[str, Any]:
        """
        获取对话管理器统计信息

        Returns:
            统计信息字典
        """
        active_sessions = [s for s in self.sessions.values() if not s.is_expired(self.session_timeout // 3600)]

        total_messages = sum(len(s.messages) for s in active_sessions)

        return {
            "total_sessions": len(self.sessions),
            "active_sessions": len(active_sessions),
            "total_messages": total_messages,
            "indexed_universities": len(self.llama_index.list_indexed_universities()) if self.llama_index else 0,
            "session_timeout_hours": self.session_timeout // 3600,
        }
