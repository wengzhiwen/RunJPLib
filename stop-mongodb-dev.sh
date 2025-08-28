#!/bin/bash

# MongoDB 开发环境停止脚本

echo "停止 MongoDB 开发服务..."

# 查找并停止MongoDB开发服务进程
PIDS=$(pgrep -f "mongod.*mongodb-dev.conf")

if [ -z "$PIDS" ]; then
    echo "MongoDB 开发服务未在运行"
    exit 0
fi

echo "找到进程: $PIDS"

# 优雅地停止进程
for PID in $PIDS; do
    echo "停止进程 $PID..."
    kill $PID
    
    # 等待进程结束
    for i in {1..10}; do
        if ! kill -0 $PID 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # 如果进程仍然存在，强制终止
    if kill -0 $PID 2>/dev/null; then
        echo "强制终止进程 $PID..."
        kill -9 $PID
    fi
done

echo "✅ MongoDB 开发服务已停止"
