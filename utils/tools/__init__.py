"""
工具类模块
包含缓存、IP地理位置等通用工具
"""

from .cache import blog_list_cache, clear_blog_list_cache
from .ip_geo import GeoLocationResolver

# 向后兼容的别名
IPGeoManager = GeoLocationResolver

__all__ = ['blog_list_cache', 'clear_blog_list_cache', 'GeoLocationResolver', 'IPGeoManager']
