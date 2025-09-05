# RunJPLib 生产环境部署指南

本文档介绍如何使用 Gunicorn 在生产环境中部署 RunJPLib 应用。

## 🚀 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
pip install gunicorn
```

### 2. 配置环境变量

```bash
# 复制环境变量示例文件
cp env.sample .env

# 编辑 .env 文件，填入实际值
nano .env
```

**必需的环境变量：**
- `MONGODB_URI`: MongoDB 连接字符串
- `JWT_SECRET_KEY`: JWT 密钥（生产环境必须设置）

### 3. 启动应用

#### 开发环境
```bash
./start.sh dev
# 或
python app.py
```

#### 生产环境
```bash
./start.sh prod
# 或
gunicorn -c gunicorn.conf.py app:app
```

## 📋 详细配置

### 环境变量说明

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志级别 (INFO=生产环境, DEBUG=开发环境) |
| `MONGODB_URI` | - | MongoDB 连接字符串 (必需) |
| `JWT_SECRET_KEY` | - | JWT 密钥 (必需) |
| `JWT_EXPIRES_DAYS` | `7` | JWT 过期天数 |
| `JWT_CSRF_PROTECT` | `true` | 是否启用 CSRF 保护 |
| `LOG_DIR` | `log` | 日志目录 |
| `LOG_MAX_BYTES` | `10485760` | 日志文件最大大小 (10MB) |
| `LOG_BACKUP_COUNT` | `50` | 日志备份数量 |
| `MAX_CONTENT_LENGTH` | `104857600` | 文件上传大小限制 (100MB) |
| `FLASK_APP_PORT` | `5000` | 应用端口 |

### Gunicorn 配置

Gunicorn 配置文件 `gunicorn.conf.py` 包含以下主要设置：

- **Worker 进程**: 4个 (CPU核心数的2倍)
- **绑定地址**: `0.0.0.0:5000`
- **超时时间**: 30秒
- **日志文件**: `log/gunicorn_access.log`, `log/gunicorn_error.log`
- **进程管理**: 自动重启，最大请求数1000
- **环境变量**: 自动从 `.env` 文件加载所有环境变量

**重要**: Gunicorn 会自动加载 `.env` 文件中的环境变量，无需手动设置。

### 启动脚本功能

`start.sh` 脚本提供以下命令：

```bash
./start.sh dev          # 启动开发环境
./start.sh prod         # 启动生产环境
./start.sh stop         # 停止应用
./start.sh restart      # 重启应用
./start.sh status       # 查看应用状态
./start.sh install      # 安装依赖
./start.sh help         # 显示帮助
```

## 🔧 生产环境优化

### 1. 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 静态文件
    location /static {
        alias /path/to/your/app/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 2. 使用 systemd 管理服务

创建 `/etc/systemd/system/runjplib.service`:

```ini
[Unit]
Description=RunJPLib Flask Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/your/app
Environment=PATH=/path/to/your/app/venv/bin
ExecStart=/path/to/your/app/venv/bin/gunicorn -c gunicorn.conf.py app:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable runjplib
sudo systemctl start runjplib
```

### 3. 监控和日志

#### 健康检查
应用提供健康检查端点：
```bash
curl http://localhost:5000/health
```

#### 日志查看
```bash
# 查看应用日志
tail -f log/app.log

# 查看 Gunicorn 访问日志
tail -f log/gunicorn_access.log

# 查看 Gunicorn 错误日志
tail -f log/gunicorn_error.log
```

## 🛠️ 故障排除

### 常见问题

1. **JWT 密钥未设置**
   ```
   ValueError: JWT_SECRET_KEY must be set to a secure value in production
   ```
   解决：设置 `JWT_SECRET_KEY` 环境变量

2. **MongoDB 连接失败**
   ```
   Error connecting to MongoDB: ...
   ```
   解决：检查 `MONGODB_URI` 环境变量和 MongoDB 服务状态

3. **端口被占用**
   ```
   Address already in use
   ```
   解决：更改端口或停止占用端口的进程

4. **权限问题**
   ```
   Permission denied
   ```
   解决：确保应用有写入日志目录的权限

### 性能调优

1. **调整 Worker 数量**
   ```python
   # 在 gunicorn.conf.py 中
   workers = 2 * multiprocessing.cpu_count() + 1
   ```

2. **启用预加载**
   ```python
   # 在 gunicorn.conf.py 中
   preload_app = True
   ```

3. **调整超时时间**
   ```python
   # 在 gunicorn.conf.py 中
   timeout = 60  # 根据应用需求调整
   ```

## 📚 更多信息

- [Gunicorn 官方文档](https://gunicorn.org/)
- [Flask 部署指南](https://flask.palletsprojects.com/en/2.0.x/deploying/)
- [MongoDB 连接字符串格式](https://docs.mongodb.com/manual/reference/connection-string/)
