"""
测试负载均衡器的实际行为
"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from vasp_rag_advanced import RealTimeLoadBalancer

def test_load_balancer():
    """详细追踪负载均衡器的行为"""

    # 创建3个模拟服务器，不同速度
    server_configs = [
        {'host': 'server_fast', 'port': 11434, 'base_url': 'http://server_fast:11434'},
        {'host': 'server_medium', 'port': 11434, 'base_url': 'http://server_medium:11434'},
        {'host': 'server_slow', 'port': 11434, 'base_url': 'http://server_slow:11434'},
    ]

    balancer = RealTimeLoadBalancer(server_configs, max_workers=3)

    # 模拟任务执行
    def mock_worker(server, batch_id, duration):
        """模拟服务器处理任务"""
        print(f"  📋 开始任务 {batch_id} -> {server['host']} (预计{duration}s)")

        # 标记忙碌
        balancer._mark_server_busy(server['base_url'], True)

        # 模拟工作
        time.sleep(duration)

        # 更新统计
        balancer._update_server_stats(server['base_url'], duration, success=True)

        # 标记空闲
        balancer._mark_server_busy(server['base_url'], False)

        print(f"  ✅ 完成任务 {batch_id} -> {server['host']}")
        return batch_id

    # 模拟6个任务，不同处理时间
    tasks = [
        (0, 0.5),  # 任务0，0.5秒
        (1, 1.0),  # 任务1，1.0秒
        (2, 1.5),  # 任务2，1.5秒
        (3, 0.5),  # 任务3，0.5秒
        (4, 1.0),  # 任务4，1.0秒
        (5, 0.5),  # 任务5，0.5秒
    ]

    print("=" * 60)
    print("🧪 负载均衡器行为追踪")
    print("=" * 60)
    print(f"\n服务器配置顺序:")
    for i, s in enumerate(server_configs):
        print(f"  {i+1}. {s['host']}")

    print(f"\n任务列表:")
    for batch_id, duration in tasks:
        print(f"  批次 {batch_id}: {duration}s")

    print("\n🔄 开始执行...\n")

    # 使用线程池执行
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = []

        # 提交所有任务
        for batch_id, duration in tasks:
            # 等待空闲服务器
            while True:
                server = balancer._get_available_server()
                if server:
                    print(f"🔍 批次 {batch_id} 选择服务器: {server['host']}")
                    break
                time.sleep(0.05)

            # 提交任务
            future = executor.submit(mock_worker, server, batch_id, duration)
            futures.append(future)

        # 等待完成
        for future in as_completed(futures):
            future.result()

    print("\n📊 最终统计:")
    balancer.print_server_stats()

    # 分析
    stats = balancer.get_server_stats()
    print("\n💡 分析:")
    for url, stat in stats.items():
        host = url.split('//')[1].split(':')[0]
        print(f"   {host}: {stat['total_tasks']} 个任务")

if __name__ == "__main__":
    test_load_balancer()