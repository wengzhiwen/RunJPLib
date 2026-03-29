#!/bin/bash
# MongoDB 完整备份脚本
# 备份整个数据库到 backup/ 目录，保留最近 2 个备份

set -e

# 加载环境变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置
BACKUP_DIR="$SCRIPT_DIR/backup"
KEEP_COUNT=2
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 从 MONGODB_URI 解析连接参数
# 支持格式: mongodb://host:port/dbname 或 mongodb://user:pass@host:port/dbname
parse_mongodb_uri() {
    local uri="${MONGODB_URI:-mongodb://localhost:27017/RunJPLib}"

    # 提取数据库名（URI 最后一段路径）
    local path="${uri#*/}"
    path="${path%%\?*}"  # 去掉查询参数
    DB_NAME="${path##*/}"
    [ -z "$DB_NAME" ] && DB_NAME="RunJPLib"

    # 提取 host:port
    local host_part="${uri#mongodb://}"
    host_part="${host_part%%/*}"        # 去掉路径部分
    host_part="${host_part%%\?*}"       # 去掉查询参数

    # 检查是否有认证信息 user:pass@
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
    [ -z "$MONGO_PORT" ] && MONGO_PORT="27017"
}

parse_mongodb_uri

# 检查 mongodump 是否可用
if ! command -v mongodump &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} mongodump 未找到，请先安装 MongoDB Database Tools"
    exit 1
fi

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 构建备份目标目录
BACKUP_PATH="$BACKUP_DIR/${TIMESTAMP}_${DB_NAME}"

# 构建 mongodump 命令参数
DUMP_ARGS=("--host" "$MONGO_HOST" "--port" "$MONGO_PORT" "--db" "$DB_NAME" "--out" "$BACKUP_PATH")

if [ -n "$MONGO_USER" ] && [ -n "$MONGO_PASS" ]; then
    DUMP_ARGS+=("--username" "$MONGO_USER" "--password" "$MONGO_PASS" "--authenticationDatabase" "admin")
fi

# 执行备份
echo -e "${GREEN}[INFO]${NC} 开始备份数据库: ${DB_NAME}"
echo -e "${GREEN}[INFO]${NC} 目标: ${MONGO_HOST}:${MONGO_PORT}"
echo -e "${GREEN}[INFO]${NC} 备份路径: ${BACKUP_PATH}"

if mongodump "${DUMP_ARGS[@]}"; then
    # 打包为压缩归档
    ARCHIVE_NAME="${BACKUP_PATH}.tar.gz"
    tar -czf "$ARCHIVE_NAME" -C "$BACKUP_DIR" "$(basename "$BACKUP_PATH")"
    rm -rf "$BACKUP_PATH"
    echo -e "${GREEN}[INFO]${NC} 备份完成: ${ARCHIVE_NAME}"
else
    echo -e "${RED}[ERROR]${NC} 备份失败"
    rm -rf "$BACKUP_PATH"
    exit 1
fi

# 清理旧备份，只保留最近 KEEP_COUNT 个
echo -e "${YELLOW}[INFO]${NC} 清理旧备份，保留最近 ${KEEP_COUNT} 个..."
ls -1dt "${BACKUP_DIR}/"*_"${DB_NAME}".tar.gz 2>/dev/null | tail -n +"$((KEEP_COUNT + 1))" | while read -r old_backup; do
    rm -f "$old_backup"
    echo -e "${YELLOW}[INFO]${NC} 已删除旧备份: $(basename "$old_backup")"
done

echo -e "${GREEN}[INFO]${NC} 当前备份列表:"
ls -1dt "${BACKUP_DIR}/"*_"${DB_NAME}".tar.gz 2>/dev/null | while read -r f; do
    size=$(du -h "$f" | cut -f1)
    echo -e "  $(basename "$f")  (${size})"
done
