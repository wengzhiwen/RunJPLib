from functools import wraps
import logging
import os

from flask import jsonify
from flask import redirect
from flask import request
from flask import url_for
from flask_jwt_extended import create_access_token
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import set_access_cookies
from flask_jwt_extended import unset_jwt_cookies
from flask_jwt_extended import verify_jwt_in_request

from ..blueprints import admin_bp


def admin_required(fn):
    """管理员权限验证装饰器"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        is_api_request = request.path.startswith("/admin/api/")
        try:
            verify_jwt_in_request(locations=["headers", "cookies"])
            identity = get_jwt_identity()
            if identity != "admin":
                logging.warning("A non-admin identity was found in a valid JWT.")
                if is_api_request:
                    return jsonify(msg="需要管理员权限"), 403
                else:
                    return redirect(url_for("admin.login"))
        except Exception as e:
            logging.warning(f"JWT validation failed for path '{request.path}': {e}")
            logging.warning(f"Request method: {request.method}")
            logging.warning(f"Request headers: {dict(request.headers)}")
            logging.warning(f"Request cookies: {dict(request.cookies)}")
            # 添加表单数据日志
            if request.method == 'POST':
                logging.warning(f"Request form data: {dict(request.form)}")
                logging.warning(f"CSRF token in form: {request.form.get('csrf_token', 'NOT FOUND')}")
            if is_api_request:
                return jsonify(msg="Token无效或已过期"), 401
            else:
                return redirect(url_for("admin.login"))
        return fn(*args, **kwargs)

    return wrapper


@admin_bp.route("/login")
def login():
    from flask import render_template
    return render_template("login.html")


@admin_bp.route("/logout")
def logout():
    from flask import make_response
    response = make_response(redirect(url_for("admin.login")))
    unset_jwt_cookies(response)
    return response


@admin_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    if not data:
        logging.error("登录失败: 请求体不是有效的JSON或Content-Type头缺失。")
        return jsonify({"msg": "无效的请求格式"}), 400
    access_code = data.get("access_code")
    env_access_code = os.getenv("ACCESS_CODE")
    if not env_access_code:
        logging.error("严重安全配置错误: 环境变量 ACCESS_CODE 未设置。")
        return jsonify({"msg": "服务器配置错误"}), 500
    if not access_code or access_code != env_access_code:
        logging.warning("收到一个错误的访问码。")
        return jsonify({"msg": "访问码错误"}), 401
    logging.info("管理员登录成功。")
    access_token = create_access_token(identity="admin")
    response = jsonify(msg="登录成功")
    set_access_cookies(response, access_token)
    return response


@admin_bp.route("/api/verify_token")
@admin_required
def verify_token():
    return jsonify(status="ok")
