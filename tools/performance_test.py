import argparse
from collections import defaultdict
from datetime import datetime
import json
import statistics
import threading
import time
from typing import Dict, List

import psutil
import requests


class SystemMonitor:

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.running = False
        self.metrics = defaultdict(list)
        self.timeline_metrics = []  # 用于存储时间序列数据
        self.start_time = None
        self.monitor_thread: threading.Thread | None = None

    def collect_metrics(self):
        current_time = time.time()
        elapsed_time = current_time - self.start_time if self.start_time else 0

        cpu_percent = psutil.cpu_percent(interval=0)
        memory = psutil.virtual_memory()

        # 记录时间序列数据
        self.timeline_metrics.append({"时间点": f"{elapsed_time:.1f}秒", "CPU使用率": cpu_percent, "内存使用率": memory.percent})

        # 累积统计数据
        self.metrics['cpu'].append(cpu_percent)
        self.metrics['memory'].append(memory.percent)

    def monitor(self):
        while self.running:
            self.collect_metrics()
            time.sleep(self.interval)

    def start(self):
        self.running = True
        self.start_time = time.time()
        self.monitor_thread = threading.Thread(target=self.monitor)
        self.monitor_thread.start()

    def stop(self):
        self.running = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join()

    def get_stats(self):
        stats = {}
        # 基础统计
        for metric, values in self.metrics.items():
            if values:
                stats[metric] = {
                    "最小值": f"{min(values):.2f}%",
                    "最大值": f"{max(values):.2f}%",
                    "平均值": f"{statistics.mean(values):.2f}%",
                    "标准差": f"{statistics.stdev(values):.2f}%" if len(values) > 1 else "N/A"
                }

        # 分析压力趋势
        if len(self.timeline_metrics) > 1:
            # 计算CPU和内存使用率的趋势
            cpu_trend = self._calculate_trend([m["CPU使用率"] for m in self.timeline_metrics])
            mem_trend = self._calculate_trend([m["内存使用率"] for m in self.timeline_metrics])

            stats["压力趋势分析"] = {"CPU趋势": cpu_trend, "内存趋势": mem_trend}

            # 添加时间序列数据
            stats["时间序列数据"] = self.timeline_metrics

        return stats

    def _calculate_trend(self, values: List[float]) -> str:
        if len(values) < 2:
            return "数据点不足以分析趋势"

        # 计算前半段和后半段的平均值来判断趋势
        mid_point = len(values) // 2
        first_half_avg = statistics.mean(values[:mid_point])
        second_half_avg = statistics.mean(values[mid_point:])

        diff = second_half_avg - first_half_avg
        if abs(diff) < 1:  # 如果变化小于1%，认为是稳定的
            return "保持稳定"
        elif diff > 0:
            return f"呈上升趋势 (增加了 {diff:.1f}%)"
        else:
            return f"呈下降趋势 (减少了 {abs(diff):.1f}%)"


class PerformanceTest:

    def __init__(self, url: str, num_requests: int = 100):
        self.url = url
        self.num_requests = num_requests
        self.response_times: List[float] = []
        self.errors: List[Dict] = []
        self.system_monitor = SystemMonitor(interval=0.5)  # 每0.5秒收集一次系统指标

    def run_test(self):
        print(f"开始测试 {self.url}")
        print(f"将发送 {self.num_requests} 个请求...\n")
        print("开始监控系统资源...")

        self.system_monitor.start()

        for i in range(self.num_requests):
            try:
                start_time = time.time()
                _ = requests.get(self.url, timeout=10)
                end_time = time.time()

                response_time = (end_time - start_time) * 1000  # 转换为毫秒
                self.response_times.append(response_time)

                if (i + 1) % 10 == 0:
                    print(f"已完成 {i + 1} 个请求")

            except Exception as e:
                error_info = {"request_num": i + 1, "error": str(e)}
                self.errors.append(error_info)

        self.system_monitor.stop()

    def generate_report(self):
        if not self.response_times:
            print("没有成功的请求记录！")
            return

        stats = {
            "测试时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "目标URL": self.url,
            "请求总数": self.num_requests,
            "成功请求数": len(self.response_times),
            "失败请求数": len(self.errors),
            "响应时间统计": {
                "最小响应时间": f"{min(self.response_times):.2f}ms",
                "最大响应时间": f"{max(self.response_times):.2f}ms",
                "平均响应时间": f"{statistics.mean(self.response_times):.2f}ms",
                "中位数响应时间": f"{statistics.median(self.response_times):.2f}ms",
                "标准差": f"{statistics.stdev(self.response_times):.2f}ms" if len(self.response_times) > 1 else "N/A",
                "90%分位数": f"{sorted(self.response_times)[int(len(self.response_times) * 0.9)]:.2f}ms",
                "95%分位数": f"{sorted(self.response_times)[int(len(self.response_times) * 0.95)]:.2f}ms",
                "99%分位数": f"{sorted(self.response_times)[int(len(self.response_times) * 0.99)]:.2f}ms"
            },
            "系统资源统计": self.system_monitor.get_stats()
        }

        print("\n性能测试报告:")
        print("=" * 50)

        # 打印请求统计
        print("\n1. 请求统计:")
        print("-" * 30)
        print(f"测试时间: {stats['测试时间']}")
        print(f"目标URL: {stats['目标URL']}")
        print(f"请求总数: {stats['请求总数']}")
        print(f"成功请求数: {stats['成功请求数']}")
        print(f"失败请求数: {stats['失败请求数']}")

        # 打印响应时间统计
        print("\n2. 响应时间统计:")
        print("-" * 30)
        for key, value in stats['响应时间统计'].items():
            print(f"{key}: {value}")

        # 打印系统资源统计
        print("\n3. 系统资源使用统计:")
        print("-" * 30)
        for resource, metrics in stats['系统资源统计'].items():
            if resource in ['cpu', 'memory']:
                print(f"\n{resource.upper()} 使用率:")
                for metric_name, value in metrics.items():
                    print(f"{metric_name}: {value}")

        # 打印压力趋势分析
        if "压力趋势分析" in stats['系统资源统计']:
            print("\n4. 压力趋势分析:")
            print("-" * 30)
            trends = stats['系统资源统计']['压力趋势分析']
            print(f"CPU压力趋势: {trends['CPU趋势']}")
            print(f"内存压力趋势: {trends['内存趋势']}")

        if self.errors:
            print("\n5. 错误记录:")
            print("-" * 30)
            for error in self.errors:
                print(f"请求 #{error['request_num']}: {error['error']}")

        # 保存报告到文件
        report_filename = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"\n详细报告已保存到: {report_filename}")


def main():
    parser = argparse.ArgumentParser(description='API性能测试工具')
    parser.add_argument('--url', default='http://localhost:5000', help='要测试的URL')
    parser.add_argument('--requests', type=int, default=100, help='请求次数')
    args = parser.parse_args()

    tester = PerformanceTest(args.url, args.requests)
    tester.run_test()
    tester.generate_report()


if __name__ == "__main__":
    main()
