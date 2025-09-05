from flask import request


def get_client_ip():
    """获取客户端IP地址"""
    # 优先使用X-Forwarded-For（考虑代理）
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    # 使用X-Real-IP
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip

    # 最后使用remote_addr
    return request.remote_addr or "unknown"
