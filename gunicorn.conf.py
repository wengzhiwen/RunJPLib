# Gunicorn配置文件
# 用于生产环境部署

import os


# 环境变量 - 自动从 .env 文件读取所有变量
def load_all_env_vars():
    """从 .env 文件加载所有环境变量到 raw_env"""
    env_vars = []
    if os.path.exists('.env'):
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if line and not line.startswith('#') and '=' in line:
                    # 移除引号（如果存在）
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env_vars.append(f"{key}={value}")
    return env_vars


# 先加载环境变量
raw_env = load_all_env_vars()

# 服务器套接字
# 优先使用环境变量中的端口，否则使用默认端口
app_port = os.getenv('FLASK_APP_PORT', '5070')
bind = f"0.0.0.0:{app_port}"
backlog = 2048

# Worker进程
workers = 4  # CPU核心数的2倍
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# 重启
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# 日志
accesslog = "log/gunicorn_access.log"
errorlog = "log/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 确保错误信息也输出到控制台
capture_output = False

# 进程管理
daemon = False
pidfile = "gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (如果需要)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# 优雅重启
graceful_timeout = 30

# 进程名称
proc_name = "runjplib"