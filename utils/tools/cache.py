"""
应用级缓存管理模块
"""
from cachetools import TTLCache, cached

# 为博客列表创建一个TTL（Time To Live）缓存
# maxsize=1: 因为我们总是缓存同一个对象（完整的博客列表）
# ttl=300: 缓存的有效期为300秒（5分钟），5分钟后会自动过期并从源头重新获取
blog_list_cache = TTLCache(maxsize=1, ttl=300)


def clear_blog_list_cache():
    """
    手动清除博客列表缓存。
    这可以在管理后台更新、创建或删除博客时调用，以确保用户能立即看到变化。
    """
    global blog_list_cache
    blog_list_cache.clear()
    print("博客列表缓存已清除。")


# 创建一个装饰器，方便在函数上使用
# @cached(blog_list_cache)
