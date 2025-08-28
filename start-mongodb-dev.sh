#!/bin/bash

# MongoDB 开发环境启动脚本 V2 - 优化版本

echo "启动 MongoDB 开发服务..."

# 检查是否已经有MongoDB进程在运行
if pgrep -f "mongod.*mongodb-dev.conf" > /dev/null; then
    echo "MongoDB 开发服务已经在运行中"
    exit 0
fi

# 创建必要的目录
mkdir -p logs data/db

# 启动MongoDB开发服务
mongod --config mongodb-dev.conf &

# 等待服务启动
sleep 3

# 检查服务状态
if pgrep -f "mongod.*mongodb-dev.conf" > /dev/null; then
    echo "✅ MongoDB 开发服务启动成功！"
    echo "连接地址: mongodb://localhost:27017"
    echo "日志文件: ./logs/mongodb.log"
    echo "数据目录: ./data/db"
    
    # 等待MongoDB完全启动
    echo "等待MongoDB服务完全启动..."
    sleep 5
    
    # 检查并创建RunJPLib数据库
    echo "检查RunJPLib数据库..."
    
    # 先检查数据库是否存在
    DB_EXISTS=$(mongosh --eval "show dbs" --quiet 2>/dev/null | grep "RunJPLib" | wc -l)
    
    if [ "$DB_EXISTS" -gt 0 ]; then
        echo "✅ RunJPLib数据库已存在"
    else
        echo "📝 创建RunJPLib数据库..."
        
        # 使用单个mongosh会话执行所有操作，提高效率
        mongosh --eval "
            use RunJPLib;
            db.createCollection('system');
            db.temp_collection.insertOne({
                _temp: true, 
                created_at: new Date(), 
                purpose: 'ensure_database_visibility'
            });
            print('数据库创建完成');
        " --quiet
        
        if [ $? -eq 0 ]; then
            echo "✅ 数据库创建成功！"
            
            # 等待数据库可见
            echo "等待数据库可见..."
            sleep 3
            
            # 清理临时数据
            echo "🧹 清理临时数据..."
            mongosh --eval "use RunJPLib; db.temp_collection.drop()" --quiet > /dev/null 2>&1
            
            # 验证清理结果
            COLLECTION_COUNT=$(mongosh --eval "use RunJPLib; db.getCollectionNames().length" --quiet 2>/dev/null | tr -d '[:space:]')
            if [ "$COLLECTION_COUNT" = "1" ]; then
                echo "✅ 临时数据清理完成，保留system集合"
            else
                echo "⚠️  临时数据清理可能不完整，但数据库已创建"
            fi
        else
            echo "⚠️  数据库创建可能失败，但服务已启动"
        fi
    fi
    
    # 显示数据库状态
    echo ""
    echo "📊 数据库状态:"
    mongosh --eval "show dbs" --quiet 2>/dev/null | grep -E "(RunJPLib|admin|local|config)" || echo "无法获取数据库列表"
    
    # 显示RunJPLib数据库的集合信息
    if [ "$DB_EXISTS" -gt 0 ]; then
        echo ""
        echo "📋 RunJPLib数据库集合:"
        mongosh --eval "use RunJPLib; db.getCollectionNames()" --quiet 2>/dev/null || echo "无法获取集合列表"
    fi
    
else
    echo "❌ MongoDB 开发服务启动失败"
    exit 1
fi
