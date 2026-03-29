#!/bin/bash
# MongoDB 备份恢复脚本
# 将指定备份恢复到新数据库（runjplib-时间戳），避免覆盖生产数据

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 加载环境变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

usage() {
    echo "用法: $0 <备份文件.tar.gz>"
    echo ""
    echo "示例:"
    echo "  $0 backup/20260329_153000_RunJPLib.tar.gz"
    echo ""
    echo "可用备份:"
    ls -1ht "$SCRIPT_DIR/backup/"*.tar.gz 2>/dev/null | while read -r f; do
        size=$(du -h "$f" | cut -f1)
        echo "  $(basename "$f")  (${size})"
    done
    exit 1
}

# 检查参数
if [ $# -lt 1 ]; then
    usage
fi

ARCHIVE_FILE="$1"

# 支持相对路径和文件名简写
if [ ! -f "$ARCHIVE_FILE" ]; then
    # 尝试在 backup/ 目录下查找
    if [ -f "$SCRIPT_DIR/backup/$ARCHIVE_FILE" ]; then
        ARCHIVE_FILE="$SCRIPT_DIR/backup/$ARCHIVE_FILE"
    else
        echo -e "${RED}[ERROR]${NC} 文件不存在: $1"
        exit 1
    fi
fi

# 检查 mongorestore 是否可用
if ! command -v mongorestore &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} mongorestore 未找到，请先安装 MongoDB Database Tools"
    exit 1
fi

# 从 MONGODB_URI 解析连接参数
parse_mongodb_uri() {
    local uri="${MONGODB_URI:-mongodb://localhost:27017/RunJPLib}"

    local host_part="${uri#mongodb://}"
    host_part="${host_part%%/*}"
    host_part="${host_part%%\?*}"

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

    # 提取原始数据库名（从备份文件或 URI）
    local path="${uri#*/}"
    path="${path%%\?*}"
    ORIG_DB_NAME="${path##*/}"
    [ -z "$ORIG_DB_NAME" ] && ORIG_DB_NAME="RunJPLib"
}

parse_mongodb_uri

# 生成目标数据库名
RESTORE_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
NEW_DB_NAME="runjplib-${RESTORE_TIMESTAMP}"

# 解压到临时目录
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

echo -e "${CYAN}[INFO]${NC} 解压备份文件: $(basename "$ARCHIVE_FILE")"
tar -xzf "$ARCHIVE_FILE" -C "$TEMP_DIR"

# 查找备份数据目录（tar 包内可能有一层目录）
BACKUP_DATA_DIR="$TEMP_DIR"
inner_dir=$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)
if [ -n "$inner_dir" ]; then
    BACKUP_DATA_DIR="$inner_dir"
fi

# 构建 mongorestore 命令参数
RESTORE_ARGS=("--host" "$MONGO_HOST" "--port" "$MONGO_PORT" "--nsInclude" "${ORIG_DB_NAME}.*")

if [ -n "$MONGO_USER" ] && [ -n "$MONGO_PASS" ]; then
    RESTORE_ARGS+=("--username" "$MONGO_USER" "--password" "$MONGO_PASS" "--authenticationDatabase" "admin")
fi

# 执行恢复
echo -e "${GREEN}[INFO]${NC} 恢复到新数据库: ${NEW_DB_NAME}"
echo -e "${GREEN}[INFO]${NC} 目标服务器: ${MONGO_HOST}:${MONGO_PORT}"
echo ""

RESTORE_ARGS+=("--dir" "$BACKUP_DATA_DIR" "--nsFrom" "${ORIG_DB_NAME}.*" "--nsTo" "${NEW_DB_NAME}.*")

if mongorestore "${RESTORE_ARGS[@]}" 2>&1 | tee /tmp/restore_output.log; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  恢复完成${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "  备份文件:   ${CYAN}$(basename "$ARCHIVE_FILE")${NC}"
    echo -e "  目标服务器: ${CYAN}${MONGO_HOST}:${MONGO_PORT}${NC}"
    echo -e "  新数据库:   ${CYAN}${NEW_DB_NAME}${NC}"
    echo -e "  原数据库:   ${CYAN}${ORIG_DB_NAME}${NC}"
    echo ""

    # 显示集合统计
    MONGO_CMD="mongo"
    if [ -n "$MONGO_USER" ]; then
        MONGO_CMD="mongo -u $MONGO_USER -p $MONGO_PASS --authenticationDatabase admin"
    fi

    STATS=$($MONGO_CMD --host "$MONGO_HOST" --port "$MONGO_PORT" --quiet --eval "
        var db = db.getSiblingDB('${NEW_DB_NAME}');
        var collections = db.getCollectionNames();
        print('');
        collections.forEach(function(c) {
            var count = db[c].count();
            var size = Math.round(db[c].stats().size / 1024);
            print('  ' + c + ': ' + count + ' 条记录, ' + size + ' KB');
        });
        print('');
        print('总集合数: ' + collections.length);
    " 2>/dev/null || echo "  (统计信息获取失败，请手动检查)")

    echo -e "${YELLOW}  集合统计:${NC}"
    echo "$STATS"
    echo ""
    echo -e "  连接字符串: ${CYAN}mongodb://${MONGO_HOST}:${MONGO_PORT}/${NEW_DB_NAME}${NC}"
    echo ""
else
    echo -e "${RED}[ERROR]${NC} 恢复失败"
    exit 1
fi
