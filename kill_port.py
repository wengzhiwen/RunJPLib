#!/usr/bin/env python3
"""
端口占用清理脚本
查找并杀掉占用 FLASK_APP_PORT 端口的程序
"""

import os
import signal
import subprocess
import sys

from dotenv import load_dotenv


def main():
    """主函数"""
    print("=== 端口占用清理脚本 ===")

    # 加载 .env 文件
    load_dotenv()

    # 获取端口号
    port = os.getenv('FLASK_APP_PORT')
    if not port:
        print("错误: 在 .env 文件中找不到 FLASK_APP_PORT")
        sys.exit(1)

    try:
        port = int(port)
    except ValueError:
        print(f"错误: FLASK_APP_PORT 的值 '{port}' 不是有效的端口号")
        sys.exit(1)

    print(f"查找占用端口 {port} 的进程...")

    # 查找占用端口的进程
    try:
        result = subprocess.run(f"lsof -ti :{port}", shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"端口 {port} 没有被占用")
            return

        pids = result.stdout.strip().split('\n')
        pids = [pid for pid in pids if pid]

        if not pids:
            print(f"端口 {port} 没有被占用")
            return

        print(f"找到 {len(pids)} 个占用端口 {port} 的进程:")

        # 显示进程信息
        for i, pid in enumerate(pids, 1):
            ps_result = subprocess.run(f"ps -p {pid} -o pid,ppid,command --no-headers", shell=True, capture_output=True, text=True)
            if ps_result.returncode == 0:
                print(f"  {i}. {ps_result.stdout.strip()}")

        # 询问用户是否要杀掉这些进程
        while True:
            choice = input(f"\n是否要杀掉这些进程? (y/n/f - f表示强制杀掉): ").lower().strip()

            if choice in ['y', 'yes']:
                killed = 0
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        print(f"终止进程 {pid}")
                        killed += 1
                    except Exception as e:
                        print(f"终止进程 {pid} 失败: {e}")
                print(f"\n成功终止了 {killed} 个进程")
                break
            elif choice in ['f', 'force']:
                killed = 0
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        print(f"强制杀掉进程 {pid}")
                        killed += 1
                    except Exception as e:
                        print(f"强制杀掉进程 {pid} 失败: {e}")
                print(f"\n成功强制杀掉了 {killed} 个进程")
                break
            elif choice in ['n', 'no']:
                print("操作已取消")
                break
            else:
                print("请输入 y (是), n (否), 或 f (强制杀掉)")

    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
