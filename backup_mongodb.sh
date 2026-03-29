#!/bin/bash
# MongoDB 完整备份脚本
# 备份整个数据库到 backup/ 目录，保留最近 2 个备份

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 加载 .env 中的 MONGODB_URI（安全解析，处理特殊字符）
load_env_var() {
    local env_file="$SCRIPT_DIR/.env"
    if [ ! -f "$env_file" ]; then
        echo -e "${YELLOW}[WARN]${NC} .env 文件不存在，使用默认连接"
        return
    fi
    while IFS= read -r line || [ -n "$line" ]; do
        # 跳过注释和空行
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        # 匹配 MONGODB_URI= 开头的行
        if [[ "$line" =~ ^MONGODB_URI= ]]; then
            # 去掉 key，保留 = 后面的全部内容（含特殊字符）
            local value="${line#MONGODB_URI=}"
            # 去除首尾引号（单引号或双引号）
            value="${value#\"}"
            value="${value%\"}"
            value="${value#\'}"
            value="${value%\'}"
            export MONGODB_URI="$value"
            return
        fi
    done < "$env_file"
}

load_env_var

# 从 MONGODB_URI 解析连接参数
parse_mongodb_uri() {
    local uri="${MONGODB_URI:-mongodb://localhost:27017/RunJPLib}"

    # 去掉 mongodb:// 前缀
    local stripped="${uri#mongodb://}"

    # 提取数据库名（最后一个路径段）
    local path_part="${stripped#*/}"
    path_part="${path_part%%\?*}"
    DB_NAME="${path_part##*/}"
    [ -z "$DB_NAME" ] && DB_NAME="RunJPLib"

    # 提取 host:port 段（/ 之前的部分）
    local host_part="${stripped%%/*}"
    host_part="${host_part%%\?*}"

    # 检查是否有 user:pass@
    if [[ "$host_part" == *@* ]]; then
        local creds="${host_part%%@*}"
        host_port="${host_part#*@}"
        MONGO_USER="${creds%%:*}"
        MONGO_PASS="${creds#*:}"
    else
        host_port="$host_part"
        MONGO_USER=""
        MONGO_PASS=""
    fi

    MONGO_HOST="${host_port%%:*}"
    MONGO_PORT="${host_port##*:}"
    [ "$MONGO_PORT" = "$MONGO_HOST" ] && MONGO_PORT="27017"

    # URL 解码用户名和密码（处理 %23 %24 等编码字符）
    if [ -n "$MONGO_USER" ]; then
        MONGO_USER=$(python3 -c "import urllib.parse, sys; print(urllib.parse.unquote(sys.argv[1]))" "$MONGO_USER")
    fi
    if [ -n "$MONGO_PASS" ]; then
        MONGO_PASS=$(python3 -c "import urllib.parse, sys; print(urllib.parse.unquote(sys.argv[1]))" "$MONGO_PASS")
    fi
}

parse_mongodb_uri

echo -e "${GREEN}[INFO]${NC} 数据库: ${DB_NAME} @ ${MONGO_HOST}:${MONGO_PORT}"

# 检查 mongodump 是否可用
if ! command -v mongodump &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} mongodump 未找到，请先安装 MongoDB Database Tools"
    exit 1
fi

# 配置
BACKUP_DIR="$SCRIPT_DIR/backup"
KEEP_COUNT=2
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

BACKUP_PATH="$BACKUP_DIR/${TIMESTAMP}_${DB_NAME}"

# 构建 mongodump 命令参数（直接使用原始 URI 避免特殊字符问题）
ORIGINAL_URI="${MONGODB_URI:-mongodb://localhost:27017/RunJPLib}"
DUMP_ARGS=("--uri" "$ORIGINAL_URI" "--db" "$DB_NAME" "--out" "$BACKUP_PATH")

# 执行备份
echo -e "${GREEN}[INFO]${NC} 开始备份..."

if mongodump "${DUMP_ARGS[@]}"; then
    ARCHIVE_NAME="${BACKUP_PATH}.tar.gz"
    tar -czf "$ARCHIVE_NAME" -C "$BACKUP_DIR" "$(basename "$BACKUP_PATH")"
    rm -rf "$BACKUP_PATH"
    echo -e "${GREEN}[INFO]${NC} 备份完成: $(basename "$ARCHIVE_NAME")"
else
    echo -e "${RED}[ERROR]${NC} 备份失败"
    rm -rf "$BACKUP_PATH"
    exit 1
fi

# 清理旧备份，只保留最近 KEEP_COUNT 个
ls -1dt "${BACKUP_DIR}/"*_"${DB_NAME}".tar.gz 2>/dev/null | tail -n +"$((KEEP_COUNT + 1))" | while read -r old_backup; do
    rm -f "$old_backup"
    echo -e "${YELLOW}[INFO]${NC} 已删除旧备份: $(basename "$old_backup")"
done

echo -e "${GREEN}[INFO]${NC} 当前备份列表:"
ls -1dt "${BACKUP_DIR}/"*_"${DB_NAME}".tar.gz 2>/dev/null | while read -r f; do
    size=$(du -h "$f" | cut -f1)
    echo -e "  $(basename "$f")  (${size})"
done
