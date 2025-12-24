"""
测试远程 Ollama 服务器连接
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time


def test_server(host, port=11434, timeout=3):
    """测试单个服务器"""
    try:
        # 测试基础连接
        url = f"http://{host}:{port}/api/version"
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            version = response.json().get('version', '未知')

            # 获取模型列表
            models_url = f"http://{host}:{port}/api/tags"
            models_response = requests.get(models_url, timeout=timeout)
            if models_response.status_code == 200:
                models = models_response.json().get('models', [])
                model_names = [m['name'] for m in models]

                return {
                    'host': host,
                    'port': port,
                    'status': 'online',
                    'version': version,
                    'models': model_names,
                    'model_count': len(models)
                }
    except Exception as e:
        pass

    return {
        'host': host,
        'port': port,
        'status': 'offline',
        'error': str(e) if 'e' in locals() else 'Connection failed'
    }


def main():
    """测试所有服务器"""
    print("=" * 60)
    print("🌐 Ollama 服务器连接测试")
    print("=" * 60)

    servers_to_test = [
        "192.168.1.130",
        "192.168.1.127",
        "localhost"
    ]

    print(f"\n正在测试 {len(servers_to_test)} 个服务器...")

    # 并行测试
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(test_server, host) for host in servers_to_test]

        for future in tqdm(as_completed(futures), total=len(futures), desc="测试进度"):
            results.append(future.result())

    # 显示结果
    print("\n" + "=" * 60)
    print("📊 测试结果")
    print("=" * 60)

    online_count = 0
    for result in results:
        status_icon = "✅" if result['status'] == 'online' else "❌"
        print(f"\n{status_icon} {result['host']}:{result['port']}")
        print(f"   状态: {result['status']}")

        if result['status'] == 'online':
            online_count += 1
            print(f"   版本: {result['version']}")
            print(f"   模型数: {result['model_count']}")
            if result['models']:
                print(f"   可用模型:")
                for model in result['models']:
                    print(f"      - {model}")

    print(f"\n" + "=" * 60)
    print(f"📈 统计: {online_count}/{len(servers_to_test)} 服务器在线")

    # 推荐配置
    online_servers = [r for r in results if r['status'] == 'online']
    if online_servers:
        print("\n💡 推荐配置:")
        print("vasp_rag_advanced.py 中的 server_hosts = [")
        for server in online_servers:
            print(f'    "{server["host"]}",')
        print("]")


if __name__ == "__main__":
    main()