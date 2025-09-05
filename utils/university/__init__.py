"""
大学相关模块
包含大学文档管理、标签分类、搜索等功能
"""

from .manager import UniversityRepository
from .search import VectorSearchEngine
from .tagger import UniversityClassifier

# 向后兼容的别名
UniversityDocumentManager = UniversityRepository
UniversityTagger = UniversityClassifier
LlamaIndexIntegration = VectorSearchEngine

__all__ = ['UniversityRepository', 'UniversityDocumentManager', 'UniversityClassifier', 'UniversityTagger', 'VectorSearchEngine', 'LlamaIndexIntegration']
