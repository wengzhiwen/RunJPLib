"""
LlamaIndex集成器
负责处理文档向量化和检索
"""
import logging
import os
from typing import Dict, List, Optional, Callable
import chromadb
from chromadb.config import Settings

from llama_index.core import Document, VectorStoreIndex, Settings as LlamaSettings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)


class LlamaIndexIntegration:
    """LlamaIndex集成器"""
    
    def __init__(self):
        """初始化LlamaIndex集成器"""
        # 设置OpenAI API密钥
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY环境变量未设置")
        
        # 配置嵌入模型
        self.embedding_model = OpenAIEmbedding(
            model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002"),
            api_key=api_key
        )
        
        # 配置LlamaIndex全局设置
        LlamaSettings.embed_model = self.embedding_model
        
        # 初始化ChromaDB客户端
        chroma_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # 文档分割器
        self.text_splitter = SentenceSplitter(
            chunk_size=800,
            chunk_overlap=100
        )
        
        # 索引缓存
        self.index_cache = {}
        
        logger.info("LlamaIndex集成器初始化完成")
    
    def create_university_index(self, university_doc: Dict, 
                              progress_callback: Optional[Callable] = None) -> str:
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
        
        try:
            logger.info(f"开始为大学 {university_name} 创建索引")
            
            if progress_callback:
                progress_callback("开始处理文档", 10)
            
            # 提取文档内容
            documents = self._extract_documents(university_doc)
            
            if not documents:
                logger.warning(f"大学 {university_name} 没有可索引的内容")
                return ""
            
            if progress_callback:
                progress_callback("准备向量存储", 30)
            
            # 创建集合名称（使用大学ID）
            collection_name = f"university_{university_id}"
            
            # 删除已存在的集合（如果有）
            try:
                self.chroma_client.delete_collection(collection_name)
                logger.info(f"删除了已存在的集合: {collection_name}")
            except Exception:
                pass  # 集合不存在，忽略错误
            
            # 创建新集合
            chroma_collection = self.chroma_client.create_collection(
                name=collection_name,
                metadata={"university_name": university_name}
            )
            
            if progress_callback:
                progress_callback("创建向量存储", 50)
            
            # 创建向量存储
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            
            if progress_callback:
                progress_callback("生成向量嵌入", 70)
            
            # 创建索引
            index = VectorStoreIndex.from_documents(
                documents,
                vector_store=vector_store,
                transformations=[self.text_splitter]
            )
            
            if progress_callback:
                progress_callback("完成索引创建", 100)
            
            # 缓存索引
            self.index_cache[university_id] = index
            
            logger.info(f"成功为大学 {university_name} 创建索引")
            return university_id
            
        except Exception as e:
            logger.error(f"为大学 {university_name} 创建索引时出错: {e}", exc_info=True)
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
        # 先检查缓存
        if university_id in self.index_cache:
            logger.info(f"从缓存获取大学 {university_id} 的索引")
            return self.index_cache[university_id]
        
        try:
            # 尝试从ChromaDB加载现有索引
            collection_name = f"university_{university_id}"
            chroma_collection = self.chroma_client.get_collection(collection_name)
            
            # 创建向量存储
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            
            # 创建索引
            index = VectorStoreIndex.from_vector_store(vector_store)
            
            # 缓存索引
            self.index_cache[university_id] = index
            
            logger.info(f"从ChromaDB加载大学 {university_id} 的索引")
            return index
            
        except Exception as e:
            logger.warning(f"无法加载大学 {university_id} 的索引: {e}")
            return None
    
    def search_university_content(self, university_id: str, query: str, 
                                top_k: int = 5) -> List[Dict]:
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
            # 创建查询引擎
            query_engine = index.as_query_engine(
                similarity_top_k=top_k,
                response_mode="no_text"  # 只返回检索的节点，不生成回答
            )
            
            # 执行查询
            response = query_engine.query(query)
            
            # 提取搜索结果
            results = []
            for node in response.source_nodes:
                result = {
                    "content": node.node.text,
                    "score": node.score,
                    "metadata": node.node.metadata
                }
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
            
            # 从ChromaDB删除集合
            self.chroma_client.delete_collection(collection_name)
            
            # 从缓存中删除
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
        
        # 基础元数据
        base_metadata = {
            "university_id": university_id,
            "university_name": university_name,
            "deadline": str(deadline)
        }
        
        # 处理原始markdown内容
        original_md = content.get('original_md', '')
        if original_md:
            doc = Document(
                text=original_md,
                metadata={
                    **base_metadata,
                    "content_type": "original",
                    "language": "japanese"
                }
            )
            documents.append(doc)
        
        # 处理翻译markdown内容
        translated_md = content.get('translated_md', '')
        if translated_md:
            doc = Document(
                text=translated_md,
                metadata={
                    **base_metadata,
                    "content_type": "translated",
                    "language": "chinese"
                }
            )
            documents.append(doc)
        
        # 处理报告markdown内容
        report_md = content.get('report_md', '')
        if report_md:
            doc = Document(
                text=report_md,
                metadata={
                    **base_metadata,
                    "content_type": "report",
                    "language": "chinese"
                }
            )
            documents.append(doc)
        
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
            
            stats = {
                "document_count": count,
                "collection_metadata": metadata,
                "collection_name": collection_name
            }
            
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
        # 这里可以根据需要实现清理逻辑
        # 目前简单返回0
        logger.info(f"清理旧索引功能暂未实现，keep_days参数: {keep_days}")
        return 0
