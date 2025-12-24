"""
VASP RAG 高级版 - 功能演示
展示进度条、远程服务器、并行加速
"""

import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from vasp_rag_advanced import VASPRAGAdvanced


def test_server(host, port=11434, timeout=3):
    """测试单个Ollama服务器"""
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


def test_servers(server_hosts=None):
    """测试所有Ollama服务器

    Args:
        server_hosts: 服务器列表，如果为None则使用默认配置

    Returns:
        list: 服务器测试结果列表
    """
    if server_hosts is None:
        server_hosts = ["192.168.1.130", "192.168.1.127", "localhost"]

    print("=" * 60)
    print("🌐 Ollama 服务器连接测试")
    print("=" * 60)

    print(f"\n正在测试 {len(server_hosts)} 个服务器...")

    # 并行测试
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(test_server, host) for host in server_hosts]

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
    print(f"📈 统计: {online_count}/{len(server_hosts)} 服务器在线")

    # 推荐配置
    online_servers = [r for r in results if r['status'] == 'online']
    if online_servers:
        print("\n💡 推荐配置:")
        print("vasp_rag_advanced.py 中的 server_hosts = [")
        for server in online_servers:
            print(f'    \"{server["host"]}\",')
        print("]")

    return results


def demo():
    """演示增强版功能"""
    print("=" * 70)
    print("🎉 VASP RAG 高级版 - 功能演示")
    print("=" * 70)

    # 配置
    config = {
        "json_file": "vasp_wiki_all_data.json",
        "server_hosts": ["192.168.1.127", "192.168.1.130", "localhost"],
        "max_workers": 3,
        "chunk_size": 1000,  # 优化为800以提高速度
        "chunk_overlap": 150,
        "persist_dir": "./chroma_db_demo",
        "force_rebuild": True  # 演示用，强制重建
    }

    print("\n📋 演示配置:")
    print(f"   服务器: {config['server_hosts']}")
    print(f"   并行工作数: {config['max_workers']}")
    print(f"   分块大小: {config['chunk_size']}")
    print(f"   重叠大小: {config['chunk_overlap']}")

    # 初始化
    rag = VASPRAGAdvanced(
        server_hosts=config["server_hosts"],
        max_workers=config["max_workers"],
        chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"],
        persist_dir=config["persist_dir"]
    )

    # 1. 服务器检测
    print("\n" + "=" * 70)
    print("步骤 1: 服务器检测与配置")
    print("=" * 70)

    if not rag.setup_servers():
        print("❌ 服务器配置失败")
        return

    # 2. 加载少量数据演示
    print("\n" + "=" * 70)
    print("步骤 2: 数据加载 (演示模式 - 仅前50个文档)")
    print("=" * 70)

    import json
    with open(config["json_file"], 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 只取前50个文档进行演示
    demo_data = data[:10]
    documents = []

    for item in demo_data:
        if "Redirect to:" in item.get('content', ''):
            continue

        content = f"标题: {item['title']}\nURL: {item['url']}\n内容: {item['content']}"
        from langchain_core.documents import Document
        doc = Document(
            page_content=content,
            metadata={'title': item['title'], 'url': item['url']}
        )
        documents.append(doc)

    print(f"✅ 加载了 {len(documents)} 个演示文档")

    # 3. 文档分块
    print("\n" + "=" * 70)
    print("步骤 3: 文档分块 (带进度条)")
    print("=" * 70)

    split_docs = rag.split_documents(documents)

    # 4. 构建向量存储 (并行加速)
    print("\n" + "=" * 70)
    print("步骤 4: 并行嵌入生成与向量存储构建")
    print("=" * 70)

    start_time = time.time()
    rag.build_vectorstore(split_docs, force_rebuild=True)
    total_time = time.time() - start_time

    print(f"\n📊 性能统计:")
    print(f"   处理文档数: {len(split_docs)}")
    print(f"   总耗时: {total_time:.1f}秒")
    print(f"   平均速度: {len(split_docs)/total_time:.1f} 文档/秒")

    # 5. 检索测试
    print("\n" + "=" * 70)
    print("步骤 5: 相似性检索测试")
    print("=" * 70)

    test_query = "RPA 计算"
    results = rag.similarity_search(test_query, k=3)

    print(f"\n查询: '{test_query}'")
    print(f"检索到 {len(results)} 个相关文档:")

    for i, doc in enumerate(results, 1):
        print(f"\n--- 结果 {i} ---")
        print(f"标题: {doc.metadata.get('title', 'N/A')}")
        print(f"内容预览: {doc.page_content[:150]}...")

    # 6. 问答测试
    print("\n" + "=" * 70)
    print("步骤 6: RAG 问答测试")
    print("=" * 70)

    question = "什么是 RPA 计算？"
    print(f"\n问题: {question}")

    try:
        qa_chain = rag.setup_qa_chain()
        print("\n💭 正在生成回答...")

        start_time = time.time()
        answer = qa_chain.invoke(question)
        end_time = time.time()

        print(f"\n✅ 回答生成完成 (耗时: {end_time - start_time:.1f}秒)")
        print(f"\n回答:\n{answer}")

    except Exception as e:
        print(f"❌ 问答失败: {e}")

    # 总结
    print("\n" + "=" * 70)
    print("🎉 演示完成！")
    print("=" * 70)

    print("\n💡 关键特性展示:")
    print("   ✅ 多服务器自动检测")
    print("   ✅ 智能嵌入模型选择")
    print("   ✅ 实时进度条显示")
    print("   ✅ 并行嵌入生成加速")
    print("   ✅ 完整 RAG 检索问答")

    print(f"\n📁 演示数据已保存到: {config['persist_dir']}")
    print("\n🚀 完整版运行: python vasp_rag_advanced.py")


def main():
    """主函数 - 支持多种运行模式"""
    import sys

    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "test_servers":
            # 服务器测试模式
            test_servers()
        elif mode == "demo":
            # 完整演示模式
            demo()
        else:
            print(f"未知模式: {mode}")
            print("\n可用模式:")
            print("  python demo_advanced.py test_servers  - 测试Ollama服务器连接")
            print("  python demo_advanced.py demo          - 运行完整功能演示")
    else:
        # 默认模式 - 交互式选择
        print("=" * 70)
        print("🎉 VASP RAG 高级版 - 演示程序")
        print("=" * 70)
        print("\n请选择运行模式:")
        print("  [1] 测试Ollama服务器连接")
        print("  [2] 运行完整功能演示")
        print("  [3] 服务器测试 + 完整演示")

        choice = input("\n请输入选项 (1/2/3): ").strip()

        if choice == "1":
            test_servers()
        elif choice == "2":
            demo()
        elif choice == "3":
            # 先测试服务器，再运行演示
            results = test_servers()
            online_servers = [r for r in results if r['status'] == 'online']
            if online_servers:
                print("\n" + "=" * 70)
                print("服务器测试完成，开始完整演示...")
                print("=" * 70)
                demo()
            else:
                print("\n⚠️  没有在线服务器，跳过演示")
        else:
            print("无效选项，程序退出")


if __name__ == "__main__":
    main()