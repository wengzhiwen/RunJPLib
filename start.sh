#!/bin/bash
# RunJPLib 启动脚本
# 支持开发环境和生产环境

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 函数：打印带颜色的消息
print_message() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Python环境
check_python_env() {
    if [ ! -d "venv" ]; then
        print_error "虚拟环境不存在，请先创建虚拟环境"
        exit 1
    fi
    
    if [ ! -f "venv/bin/activate" ]; then
        print_error "虚拟环境激活脚本不存在"
        exit 1
    fi
}

# 安装依赖
install_dependencies() {
    print_message "检查并安装Python依赖..."
    source venv/bin/activate
    pip install -r requirements.txt
    
    # 检查是否需要安装Gunicorn
    if ! pip show gunicorn > /dev/null 2>&1; then
        print_message "安装Gunicorn..."
        pip install gunicorn
    fi
}

# 创建必要的目录
create_directories() {
    print_message "创建必要的目录..."
    mkdir -p log
    mkdir -p static
}

# 加载环境变量
load_env_file() {
    if [ -f ".env" ]; then
        # 安全地加载 .env 文件
        set -a  # 自动导出变量
        source .env
        set +a  # 关闭自动导出
        print_message "已加载 .env 文件"
    else
        print_error ".env 文件不存在，请复制 env.sample 为 .env 并填入实际值"
        exit 1
    fi
}

# 开发环境启动
start_development() {
    print_message "启动开发环境..."
    source venv/bin/activate
    
    # 加载环境变量
    load_env_file
    
    # 确保开发环境使用 DEBUG 日志级别
    export LOG_LEVEL=DEBUG
    
    python app.py
}

# 检查端口是否可用
check_port() {
    local port=$1
    if lsof -i :$port > /dev/null 2>&1; then
        print_error "端口 $port 已被占用，请检查是否有其他服务在运行"
        print_message "可以使用以下命令查看端口占用情况:"
        echo "  lsof -i :$port"
        return 1
    fi
    return 0
}

# 生产环境启动
start_production() {
    print_message "启动生产环境..."
    source venv/bin/activate
    
    # 加载环境变量
    load_env_file
    
    # 检查Gunicorn配置
    if [ ! -f "gunicorn.conf.py" ]; then
        print_error "Gunicorn配置文件不存在: gunicorn.conf.py"
        exit 1
    fi
    
    # 检查端口是否可用（从配置文件中提取端口）
    local port=$(grep "bind.*:" gunicorn.conf.py | sed 's/.*:\([0-9]*\).*/\1/')
    if [ -n "$port" ]; then
        if ! check_port $port; then
            exit 1
        fi
    fi
    
    # 清理可能存在的PID文件
    if [ -f "gunicorn.pid" ]; then
        local old_pid=$(cat gunicorn.pid)
        if ! ps -p $old_pid > /dev/null 2>&1; then
            print_message "清理残留的PID文件"
            rm -f gunicorn.pid
        fi
    fi
    
    # 启动Gunicorn
    print_message "启动Gunicorn服务器..."
    gunicorn -c gunicorn.conf.py app:app
}

# 停止应用
stop_app() {
    print_message "停止应用..."
    
    # 方法1：通过PID文件停止
    if [ -f "gunicorn.pid" ]; then
        local master_pid=$(cat gunicorn.pid)
        print_message "发现主进程PID: $master_pid"
        
        # 检查主进程是否还在运行
        if ps -p $master_pid > /dev/null 2>&1; then
            print_message "正在停止主进程和所有worker进程..."
            # 使用SIGTERM优雅停止，这会自动停止所有worker进程
            kill -TERM $master_pid
            
            # 等待进程停止
            local count=0
            while ps -p $master_pid > /dev/null 2>&1 && [ $count -lt 10 ]; do
                sleep 1
                count=$((count + 1))
            done
            
            # 如果进程还在运行，强制杀掉
            if ps -p $master_pid > /dev/null 2>&1; then
                print_warning "主进程未响应SIGTERM，强制停止..."
                kill -KILL $master_pid
            fi
        else
            print_warning "PID文件中的进程 $master_pid 已不存在"
        fi
        
        rm -f gunicorn.pid
        print_message "PID文件已清理"
    fi
    
    # 方法2：通过进程名查找并停止所有gunicorn进程
    local gunicorn_pids=$(pgrep -f "gunicorn.*app:app" 2>/dev/null)
    if [ -n "$gunicorn_pids" ]; then
        print_message "发现残留的Gunicorn进程: $gunicorn_pids"
        print_message "正在清理残留进程..."
        echo $gunicorn_pids | xargs kill -TERM 2>/dev/null
        
        # 等待进程停止
        sleep 2
        
        # 检查是否还有进程在运行
        local remaining_pids=$(pgrep -f "gunicorn.*app:app" 2>/dev/null)
        if [ -n "$remaining_pids" ]; then
            print_warning "强制停止残留进程: $remaining_pids"
            echo $remaining_pids | xargs kill -KILL 2>/dev/null
        fi
    fi
    
    # 验证端口是否已释放
    local port=$(grep "bind.*:" gunicorn.conf.py | sed 's/.*:\([0-9]*\).*/\1/')
    if [ -n "$port" ]; then
        if lsof -i :$port > /dev/null 2>&1; then
            print_warning "端口 $port 仍被占用，可能需要手动清理"
        else
            print_message "端口 $port 已释放"
        fi
    fi
    
    print_message "应用停止完成"
}

# 重启应用
restart_app() {
    print_message "重启应用..."
    stop_app
    sleep 2
    start_production
}

# 显示状态
show_status() {
    if [ -f "gunicorn.pid" ]; then
        local pid=$(cat gunicorn.pid)
        if ps -p $pid > /dev/null 2>&1; then
            print_message "应用正在运行 (PID: $pid)"
        else
            print_warning "PID文件存在但进程未运行"
        fi
    else
        print_warning "应用未运行"
    fi
}

# 显示帮助
show_help() {
    echo "RunJPLib 启动脚本"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  dev, development    启动开发环境"
    echo "  prod, production   启动生产环境"
    echo "  stop               停止应用"
    echo "  restart            重启应用"
    echo "  status             显示应用状态"
    echo "  install            安装依赖"
    echo "  help               显示此帮助信息"
    echo ""
    echo "请复制 env.sample 为 .env 并填入实际值"
}

# 主函数
main() {
    case "${1:-help}" in
        "dev"|"development")
            start_development
            ;;
        "prod"|"production")
            start_production
            ;;
        "stop")
            stop_app
            ;;
        "restart")
            restart_app
            ;;
        "status")
            show_status
            ;;
        "install")
            check_python_env
            create_directories
            install_dependencies
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
