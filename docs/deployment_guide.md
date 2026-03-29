# RunJPLib 生产环境部署指南

## 快速开始

### 1. 环境准备

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

### 2. 配置环境变量

```bash
cp env.sample .env
nano .env
```

**必需的环境变量：**
- `MONGODB_URI`: MongoDB 连接字符串
- `JWT_SECRET_KEY`: JWT 密钥（生产环境必须设置为安全值）
- `ACCESS_CODE`: Admin 后台访问码

### 3. 启动应用

```bash
# 开发环境
./start.sh dev

# 生产环境
./start.sh prod
```

## 环境变量说明

### 基础配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `MONGODB_URI` | - | MongoDB 连接字符串（必需） |
| `JWT_SECRET_KEY` | - | JWT 密钥（必需） |
| `JWT_EXPIRES_DAYS` | `7` | JWT 过期天数 |
| `ACCESS_CODE` | - | Admin 后台访问码 |
| `FLASK_APP_PORT` | `5000` | 应用端口 |
| `MAX_CONTENT_LENGTH` | `104857600` | 文件上传大小限制（100MB） |

### AI 模型配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `OCR_MODEL_NAME` | `gpt-4o-mini` | OCR 模型 |
| `OPENAI_TRANSLATE_MODEL` | `gpt-4o-mini` | 翻译模型 |
| `OPENAI_ANALYSIS_MODEL` | `gpt-4o-mini` | 分析模型 |
| `TRANSLATE_TERMS_FILE` | - | 翻译术语文件路径 |
| `ANALYSIS_QUESTIONS_FILE` | - | 分析问题文件路径 |

### PDF 处理配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PDF_PROCESSOR_TEMP_DIR` | `temp/pdf_processing` | PDF 处理临时目录 |
| `OCR_DPI` | `150` | OCR 图片 DPI |
| `PDF_MAX_CONCURRENT_TASKS` | `1` | 最大并发任务数 |

### 线程池配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `BLOG_UPDATE_THREAD_POOL_SIZE` | `8` | 博客 HTML 构建线程池 |
| `ADMIN_THREAD_POOL_SIZE` | `4` | Admin 操作线程池 |
| `ANALYTICS_THREAD_POOL_SIZE` | `6` | 用户访问日志线程池 |

### 日志配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `LOG_DIR` | `log` | 日志目录 |
| `LOG_MAX_BYTES` | `10485760` | 日志文件最大大小（10MB） |
| `LOG_BACKUP_COUNT` | `50` | 日志备份数量 |
| `PYMONGO_LOG_LEVEL` | `INFO` | pymongo 日志级别 |

## Gunicorn 配置

`gunicorn.conf.py` 主要设置：
- **Worker 进程**: 4 个
- **绑定地址**: `0.0.0.0:5000`
- **超时时间**: 30 秒
- **日志文件**: `log/gunicorn_access.log`, `log/gunicorn_error.log`
- **自动加载 `.env`** 文件中的环境变量

## 启动脚本

```bash
./start.sh dev          # 开发环境
./start.sh prod         # 生产环境
./start.sh stop         # 停止应用
./start.sh restart      # 重启应用
./start.sh status       # 查看状态
./start.sh install      # 安装依赖
```

## 生产环境优化

### Nginx 反向代理

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

    location /static {
        alias /path/to/app/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 健康检查

```bash
curl http://localhost:5000/health
```

### 日志查看

```bash
tail -f log/app_$(date +%Y%m%d).log          # 应用日志
tail -f log/TaskManager_$(date +%Y%m%d).log   # 任务管理日志
tail -f log/retrieval_$(date +%Y%m%d).log     # 检索日志
```

## 核心依赖

| 包名 | 用途 |
|------|------|
| `flask` | Web 框架 |
| `pymongo` | MongoDB 驱动 |
| `Flask-JWT-Extended` | JWT 认证 |
| `openai` | OpenAI API 客户端 |
| `openai-agents` | AI Agent 框架（博客生成） |
| `buffalo-workflow` | 工作流引擎（PDF 处理流水线） |
| `llama-index` | 向量索引与检索 |
| `chromadb` | 向量存储 |
| `pdf2image` | PDF 转图片 |
| `markdown` | Markdown 转换 |
| `cachetools` | TTL 缓存 |
