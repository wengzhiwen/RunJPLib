"""
LlamaIndex集成器
负责处理文档向量化和检索
"""
from datetime import datetime
import os
from typing import Callable, Dict, List, Optional

import chromadb
from chromadb.config import Settings
from llama_index.core import Document, StorageContext
from llama_index.core import Settings as LlamaSettings
from llama_index.core import VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

# 使用retrieval logger确保日志能正确输出
from utils.logging_config import setup_retrieval_logger

logger = setup_retrieval_logger()


class LlamaIndexIntegration:
    """LlamaIndex集成器"""

    def __init__(self):
        """初始化LlamaIndex集成器"""
        # 设置OpenAI API密钥
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY环境变量未设置")

        # 配置嵌入模型
        self.embedding_model = OpenAIEmbedding(model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002"), api_key=api_key)

        # 配置LlamaIndex全局设置
        LlamaSettings.embed_model = self.embedding_model

        # 初始化ChromaDB客户端
        chroma_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
        self.chroma_client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False, allow_reset=True))

        # 文档分割器
        self.text_splitter = SentenceSplitter(chunk_size=800, chunk_overlap=100)

        # 索引缓存
        self.index_cache = {}

        logger.info("LlamaIndex集成器初始化完成")

    def create_university_index(self, university_doc: Dict, progress_callback: Optional[Callable] = None) -> str:
        """
        为大学创建索引

        Args:
            university_doc: 大学文档
            progress_callback: 进度回调函数

        Returns:
            索引ID
        """
        university_id = str(university_doc.get('_id', ''))
        university_name = university_doc.get('university_name', '未知大学')
        last_modified_iso = university_doc.get("last_modified", datetime.utcnow()).isoformat()

        try:
            logger.info(f"=== 开始为大学 {university_name} 创建或更新索引 ===")
            logger.info(f"大学ID: {university_id}")
            logger.info(f"最后修改时间: {last_modified_iso}")

            if progress_callback:
                progress_callback("开始处理文档", 10)

            # 步骤1: 提取文档内容
            logger.info("--- 步骤1: 提取文档内容 ---")
            documents = self._extract_documents(university_doc)
            if not documents:
                logger.warning(f"大学 {university_name} 没有可索引的内容")
                return ""

            # 详细记录每个文档的信息
            total_text_length = 0
            for i, doc in enumerate(documents):
                text_length = len(doc.text)
                total_text_length += text_length
                logger.info(f"文档 {i+1}: {doc.metadata.get('content_type', 'unknown')} - {text_length} 字符")
                logger.info(f"  元数据: {doc.metadata}")

            logger.info(f"总文档数: {len(documents)}, 总文本长度: {total_text_length} 字符")

            if progress_callback:
                progress_callback("准备向量存储", 30)

            # 步骤2: 准备ChromaDB集合
            logger.info("--- 步骤2: 准备ChromaDB集合 ---")
            collection_name = f"university_{university_id}"
            logger.info(f"集合名称: {collection_name}")

            # 确保清除旧索引
            try:
                self.chroma_client.delete_collection(name=collection_name)
                logger.info(f"已删除旧的索引集合: {collection_name}")
            except Exception:
                logger.info(f"集合 {collection_name} 不存在或已删除")

            # 使用 get_or_create_collection 原子化地创建集合并设置元数据
            collection_metadata = {"university_name": university_name, "source_last_modified": last_modified_iso}
            chroma_collection = self.chroma_client.get_or_create_collection(name=collection_name, metadata=collection_metadata)
            logger.info(f"已创建新的索引集合，元数据: {collection_metadata}")

            if progress_callback:
                progress_callback("创建向量存储", 50)

            # 步骤3: 创建向量存储和存储上下文
            logger.info("--- 步骤3: 创建向量存储和存储上下文 ---")
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            logger.info("成功创建ChromaVectorStore")

            # 创建存储上下文 - 这是关键！
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            logger.info("成功创建StorageContext")

            if progress_callback:
                progress_callback("生成向量嵌入", 70)

            # 步骤4: 生成向量嵌入和创建索引
            logger.info("--- 步骤4: 生成向量嵌入和创建索引 ---")
            logger.info(f"使用文本分割器: {self.text_splitter}")
            logger.info(f"文本分割器配置: chunk_size={self.text_splitter.chunk_size}, chunk_overlap={self.text_splitter.chunk_overlap}")

            # 记录文本分割前的状态
            logger.info("开始文本分割和向量化...")
            logger.info(f"预计分割后节点数: 约 {total_text_length // self.text_splitter.chunk_size + len(documents)} 个")

            try:
                index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, transformations=[self.text_splitter])
                logger.info("VectorStoreIndex.from_documents调用成功")

                # 强制持久化到向量存储 - 确保数据写入ChromaDB
                logger.info("强制同步向量存储到ChromaDB...")
                if hasattr(index, '_vector_store') and hasattr(index._vector_store, '_collection'):
                    # 触发向量存储的同步操作（如果有的话）
                    logger.info("触发向量存储同步...")

                # 验证索引是否包含节点
                if hasattr(index, 'docstore') and hasattr(index.docstore, 'docs'):
                    node_count = len(index.docstore.docs)
                    logger.info(f"✅ 索引创建成功！索引中的节点数量: {node_count}")

                    # 统计每个文档类型产生的节点数
                    node_type_count = {}
                    for _, node in index.docstore.docs.items():
                        content_type = node.metadata.get('content_type', 'unknown')
                        node_type_count[content_type] = node_type_count.get(content_type, 0) + 1

                    logger.info(f"节点类型分布: {node_type_count}")

                    # 验证ChromaDB中的实际存储
                    try:
                        # 等待一下，确保写入完成
                        import time
                        time.sleep(1)

                        collection_count = chroma_collection.count()
                        logger.info(f"ChromaDB集合中的实际文档数: {collection_count}")

                        if collection_count > 0:
                            logger.info("✅ ChromaDB存储验证成功")
                        else:
                            logger.error("❌ ChromaDB存储验证失败：集合为空")

                            # 尝试获取更多诊断信息
                            logger.info("=== ChromaDB诊断信息 ===")
                            try:
                                # 检查集合元数据
                                collection_metadata = chroma_collection.metadata
                                logger.info(f"集合元数据: {collection_metadata}")

                                # 尝试获取集合名称
                                logger.info(f"集合名称: {chroma_collection.name}")

                                # 尝试列出所有集合
                                all_collections = self.chroma_client.list_collections()
                                logger.info(f"所有集合: {[col.name for col in all_collections]}")

                                # 尝试直接查询集合
                                try:
                                    # 尝试获取一个样本文档
                                    sample_result = chroma_collection.get(limit=1)
                                    logger.info(f"样本查询结果: {sample_result}")
                                except Exception as e:
                                    logger.error(f"样本查询失败: {e}")

                            except Exception as e:
                                logger.error(f"ChromaDB诊断失败: {e}")

                            logger.info("=== 诊断信息结束 ===")

                    except Exception as e:
                        logger.error(f"ChromaDB验证失败: {e}")
                        logger.error(f"错误类型: {type(e)}")
                        logger.error(f"错误详情: {str(e)}")

                else:
                    logger.warning("⚠️ 无法获取索引中的节点数量")

            except Exception as e:
                logger.error(f"❌ VectorStoreIndex.from_documents调用失败: {e}")
                logger.error(f"错误类型: {type(e)}")
                logger.error(f"错误详情: {str(e)}")
                raise

            if progress_callback:
                progress_callback("完成索引创建", 100)

            # 步骤5: 缓存索引并验证
            logger.info("--- 步骤5: 缓存索引并验证 ---")
            self.index_cache[university_id] = index
            logger.info(f"索引已缓存到内存，缓存键: {university_id}")

            # 验证索引是否可用
            try:
                logger.info("验证索引是否可用...")
                index.as_query_engine(similarity_top_k=1, response_mode="no_text")
                logger.info("✅ 索引查询引擎创建成功，索引可用")
            except Exception as e:
                logger.error(f"❌ 索引验证失败: {e}")
                raise

            logger.info(f"=== 成功为大学 {university_name} 创建索引 ===")
            logger.info(f"源文档版本: {last_modified_iso}")
            logger.info(f"索引ID: {university_id}")

            return university_id

        except Exception as e:
            logger.error(f"=== 为大学 {university_name} 创建索引时出错 ===")
            logger.error(f"错误类型: {type(e)}")
            logger.error(f"错误详情: {str(e)}")
            logger.error("错误堆栈:", exc_info=True)

            if progress_callback:
                progress_callback(f"索引创建失败: {str(e)}", -1)
            raise

    def get_university_index(self, university_id: str) -> Optional[VectorStoreIndex]:
        """
        获取大学索引

        Args:
            university_id: 大学ID

        Returns:
            VectorStoreIndex对象，如果不存在则返回None
        """
        if university_id in self.index_cache:
            logger.info(f"从缓存获取大学 {university_id} 的索引")
            return self.index_cache[university_id]

        try:
            collection_name = f"university_{university_id}"
            chroma_collection = self.chroma_client.get_collection(collection_name)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            _ = StorageContext.from_defaults(vector_store=vector_store)
            index = VectorStoreIndex.from_vector_store(vector_store)
            self.index_cache[university_id] = index
            logger.info(f"从ChromaDB加载大学 {university_id} 的索引")
            return index

        except Exception:
            logger.warning(f"大学 {university_id} 的索引不存在")
            return None

    def get_index_metadata(self, university_id: str) -> Optional[Dict]:
        """
        获取索引的元数据，主要用于检查索引版本。

        Args:
            university_id: 大学ID

        Returns:
            包含元数据（如source_last_modified）的字典
        """
        try:
            collection_name = f"university_{university_id}"
            collection = self.chroma_client.get_collection(collection_name)
            return collection.metadata
        except Exception:
            return None

    def search_university_content(self, university_id: str, query: str, top_k: int = 5) -> List[Dict]:
        """
        在大学内容中搜索

        Args:
            university_id: 大学ID
            query: 搜索查询
            top_k: 返回结果数量

        Returns:
            搜索结果列表
        """
        index = self.get_university_index(university_id)
        if not index:
            logger.warning(f"大学 {university_id} 的索引不存在")
            return []

        try:
            query_engine = index.as_query_engine(similarity_top_k=top_k, response_mode="no_text")
            response = query_engine.query(query)
            results = []
            for node in response.source_nodes:
                result = {"content": node.node.text, "score": node.score, "metadata": node.node.metadata}
                results.append(result)
            logger.info(f"在大学 {university_id} 中搜索 '{query}' 返回 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"搜索大学 {university_id} 内容时出错: {e}", exc_info=True)
            return []

    def delete_university_index(self, university_id: str) -> bool:
        """
        删除大学索引

        Args:
            university_id: 大学ID

        Returns:
            True如果删除成功，False否则
        """
        try:
            collection_name = f"university_{university_id}"
            self.chroma_client.delete_collection(collection_name)
            if university_id in self.index_cache:
                del self.index_cache[university_id]
            logger.info(f"成功删除大学 {university_id} 的索引")
            return True

        except Exception as e:
            logger.error(f"删除大学 {university_id} 索引时出错: {e}", exc_info=True)
            return False

    def list_indexed_universities(self) -> List[str]:
        """
        列出所有已索引的大学

        Returns:
            大学ID列表
        """
        try:
            collections = self.chroma_client.list_collections()
            university_ids = []
            for collection in collections:
                if collection.name.startswith("university_"):
                    university_id = collection.name.replace("university_", "")
                    university_ids.append(university_id)
            logger.info(f"找到 {len(university_ids)} 个已索引的大学")
            return university_ids

        except Exception as e:
            logger.error(f"列出已索引大学时出错: {e}", exc_info=True)
            return []

    def _extract_documents(self, university_doc: Dict) -> List[Document]:
        """
        从大学文档中提取LlamaIndex文档

        Args:
            university_doc: 大学文档

        Returns:
            Document对象列表
        """
        documents = []
        content = university_doc.get('content', {})
        university_name = university_doc.get('university_name', '未知大学')
        university_id = str(university_doc.get('_id', ''))
        deadline = university_doc.get('deadline', '')

        base_metadata = {"university_id": university_id, "university_name": university_name, "deadline": str(deadline)}

        # 记录文档内容状态
        logger.info(f"提取文档内容 - 大学: {university_name}")
        logger.info(f"内容字段: {list(content.keys()) if isinstance(content, dict) else 'N/A'}")

        original_md = content.get('original_md', '')
        if original_md:
            logger.info(f"原始日文文档: {len(original_md)} 字符")
            doc = Document(text=original_md, metadata={**base_metadata, "content_type": "original", "language": "japanese"})
            documents.append(doc)
        else:
            logger.warning("原始日文文档为空")

        translated_md = content.get('translated_md', '')
        if translated_md:
            logger.info(f"中文翻译文档: {len(translated_md)} 字符")
            doc = Document(text=translated_md, metadata={**base_metadata, "content_type": "translated", "language": "chinese"})
            documents.append(doc)
        else:
            logger.warning("中文翻译文档为空")

        report_md = content.get('report_md', '')
        if report_md:
            logger.info(f"报告文档: {len(report_md)} 字符")
            doc = Document(text=report_md, metadata={**base_metadata, "content_type": "report", "language": "chinese"})
            documents.append(doc)
        else:
            logger.warning("报告文档为空")

        logger.info(f"从大学 {university_name} 提取了 {len(documents)} 个文档")
        return documents

    def get_index_stats(self, university_id: str) -> Optional[Dict]:
        """
        获取索引统计信息

        Args:
            university_id: 大学ID

        Returns:
            统计信息字典
        """
        try:
            collection_name = f"university_{university_id}"
            chroma_collection = self.chroma_client.get_collection(collection_name)
            count = chroma_collection.count()
            metadata = chroma_collection.metadata
            stats = {"document_count": count, "collection_metadata": metadata, "collection_name": collection_name}
            return stats

        except Exception as e:
            logger.error(f"获取大学 {university_id} 索引统计时出错: {e}")
            return None

    def cleanup_old_indexes(self, keep_days: int = 30) -> int:
        """
        清理旧的索引

        Args:
            keep_days: 保留天数（暂未使用，预留参数）

        Returns:
            删除的索引数量
        """
        logger.info(f"清理旧索引功能暂未实现，keep_days参数: {keep_days}")
        return 0
