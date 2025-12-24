"""
快速测试增强版功能
"""

import time
from vasp_rag_advanced import VASPRAGAdvanced, RemoteOllamaConfig


def test_server_discovery():
    """测试服务器发现"""
    print("=" * 60)
    print("测试 1: 服务器发现")
    print("=" * 60)

    config = RemoteOllamaConfig()
    config.servers = [
        {"host": "192.168.1.130", "port": 11434, "status": "checking"},
        {"host": "192.168.1.127", "port": 11434, "status": "checking"},
        {"host": "localhost", "port": 11434, "status": "checking"}
    ]

    online_servers = config.check_servers()
    print(f"\n在线服务器: {len(online_servers)}")

    if online_servers:
        best = config.find_best_embedding_model()
        if best:
            print(f"\n✅ 找到最佳配置: {best}")
            return True

    print("\n❌ 未找到可用配置")
    return False


def test_progress_bars():
    """测试进度条"""
    print("\n" + "=" * 60)
    print("测试 2: 进度条演示")
    print("=" * 60)

    from tqdm import tqdm
    import time

    # 模拟数据处理
    print("\n模拟文档加载:")
    for i in tqdm(range(10), desc="加载文档"):
        time.sleep(0.1)

    print("\n模拟嵌入生成:")
    for i in tqdm(range(20), desc="生成嵌入"):
        time.sleep(0.05)

    print("\n✅ 进度条测试完成")
    return True


def test_parallel_concept():
    """演示并行概念"""
    print("\n" + "=" * 60)
    print("测试 3: 并行处理概念")
    print("=" * 60)

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tqdm import tqdm

    def mock_embedding_task(task_id, delay):
        time.sleep(delay)
        return f"任务 {task_id} 完成"

    tasks = [(i, 0.2) for i in range(8)]

    print(f"\n模拟 {len(tasks)} 个并行嵌入任务...")

    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(mock_embedding_task, task_id, delay)
                  for task_id, delay in tasks]

        for future in tqdm(as_completed(futures), total=len(futures), desc="处理进度"):
            result = future.result()
            results.append(result)

    print(f"\n✅ 并行处理完成: {len(results)} 个结果")
    return True


def main():
    """运行所有测试"""
    print("🚀 VASP RAG 高级版 - 功能测试")
    print("=" * 60)

    tests = [
        ("服务器发现", test_server_discovery),
        ("进度条", test_progress_bars),
        ("并行概念", test_parallel_concept),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 测试失败: {e}")
            results.append((name, False))

    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} {name}")

    passed = sum(1 for _, r in results if r)
    print(f"\n总计: {passed}/{len(results)} 通过")

    if passed == len(results):
        print("\n🎉 所有测试通过！可以运行完整版: python vasp_rag_advanced.py")
    else:
        print("\n⚠️  部分测试失败，请检查环境")


if __name__ == "__main__":
    main()