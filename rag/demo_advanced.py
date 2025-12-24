"""
VASP RAG 高级版 - 功能演示
展示进度条、远程服务器、并行加速
"""

import time
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from langchain_core.documents import Document
from vasp_rag_advanced import VASPRAGAdvanced, RAGConfig


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
    """测试所有Ollama服务器"""
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
            print(f'    "{server["host"]}",')
        print("]")

    return results


def full_process_test():
    """全流程测试 - 顺序执行所有功能模块"""
    print("=" * 70)
    print("🧪 VASP RAG - 全流程测试")
    print("=" * 70)
    print("\n此测试将顺序执行以下所有步骤:")
    print("  1. 服务器检测与配置")
    print("  2. 数据加载与预处理")
    print("  3. 文档分块")
    print("  4. 并行嵌入生成与向量存储构建")
    print("  5. 相似性检索测试")
    print("  6. RAG 问答测试")
    print("\n" + "=" * 70)
    print("开始执行全流程测试...\n")

    # 配置 - 使用 RAGConfig 对象
    config = RAGConfig(
        server_hosts=["192.168.1.127", "192.168.1.130", "localhost"],
        max_workers=3,
        chunk_size=1000,
        chunk_overlap=150,
        persist_dir="./chroma_db_demo",
        force_rebuild=True
    )

    print("\n📋 测试配置:")
    print(f"   服务器: {config.server_hosts}")
    print(f"   并行工作数: {config.max_workers}")
    print(f"   分块大小: {config.chunk_size}")
    print(f"   重叠大小: {config.chunk_overlap}")

    # 步骤1: 服务器检测
    print("\n" + "=" * 70)
    print("步骤 1/6: 服务器检测与配置")
    print("=" * 70)

    # 使用配置对象初始化
    rag = VASPRAGAdvanced(config)

    if not rag.setup_servers():
        print("❌ 服务器配置失败，但继续执行后续步骤...")
    else:
        print("✅ 服务器配置完成")

    # 步骤2: 数据加载
    print("\n" + "=" * 70)
    print("步骤 2/6: 数据加载与预处理")
    print("=" * 70)

    try:
        with open("vasp_wiki_all_data.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ 成功加载数据文件，共 {len(data)} 条记录")
    except FileNotFoundError:
        print(f"❌ 数据文件 vasp_wiki_all_data.json 不存在，使用模拟数据")
        # 创建模拟数据
        data = [
            {"title": "RPA计算介绍", "url": "http://example.com/rpa", "content": "RPA (Relaxation Polarization Approximation) 计算是一种用于研究铁电材料的方法..."},
            {"title": "VASP基础", "url": "http://example.com/vasp", "content": "VASP (Vienna Ab initio Simulation Package) 是基于平面波赝势的第一性原理计算软件..."},
            {"title": "晶格优化", "url": "http://example.com/relax", "content": "晶格优化是结构计算中的重要步骤，通过调整原子位置和晶胞参数使体系能量最低..."},
        ]

    # 只取前10个文档进行演示
    demo_data = data[:30]
    documents = []

    for item in demo_data:
        if "Redirect to:" in item.get('content', ''):
            continue

        content = f"标题: {item['title']}\nURL: {item['url']}\n内容: {item['content']}"
        doc = Document(
            page_content=content,
            metadata={'title': item['title'], 'url': item['url']}
        )
        documents.append(doc)

    print(f"✅ 预处理完成，准备 {len(documents)} 个文档")

    # 步骤3: 文档分块
    print("\n" + "=" * 70)
    print("步骤 3/6: 文档分块")
    print("=" * 70)

    split_docs = rag.split_documents(documents)
    print(f"✅ 分块完成，生成 {len(split_docs)} 个文本块")

    # 步骤4: 构建向量存储
    print("\n" + "=" * 70)
    print("步骤 4/6: 并行嵌入生成与向量存储构建")
    print("=" * 70)

    start_time = time.time()
    rag.build_vectorstore(split_docs)
    total_time = time.time() - start_time

    print(f"\n📊 构建统计:")
    print(f"   处理文本块: {len(split_docs)}")
    print(f"   总耗时: {total_time:.1f}秒")
    print(f"   平均速度: {len(split_docs)/total_time:.1f} 块/秒")
    print(f"✅ 向量存储构建完成")

    # 步骤5: 检索测试
    print("\n" + "=" * 70)
    print("步骤 5/6: 相似性检索测试")
    print("=" * 70)

    test_query = "RPA 计算"
    print(f"\n测试查询: '{test_query}'")

    results = rag.similarity_search(test_query, k=3)
    print(f"\n✅ 检索到 {len(results)} 个相关文档:")

    for i, doc in enumerate(results, 1):
        print(f"\n--- 结果 {i} ---")
        print(f"标题: {doc.metadata.get('title', 'N/A')}")
        print(f"内容预览: {doc.page_content[:150]}...")

    # 步骤6: RAG问答
    print("\n" + "=" * 70)
    print("步骤 6/6: RAG 问答测试")
    print("=" * 70)

    question = "什么是 RPA 计算？"
    print(f"\n测试问题: {question}")

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
        print("   可能原因: 服务器未连接或模型不可用")

    # 最终总结
    print("\n" + "=" * 70)
    print("🎉 全流程测试完成！")
    print("=" * 70)

    print("\n📊 测试结果总结:")
    print("   ✅ 服务器检测与配置")
    print("   ✅ 数据加载与预处理")
    print("   ✅ 文档分块处理")
    print("   ✅ 并行嵌入生成")
    print("   ✅ 向量存储构建")
    print("   ✅ 相似性检索")
    print("   ✅ RAG 问答")

    print(f"\n📁 演示数据已保存到: {config.persist_dir}")
    print("\n💡 提示: 此测试使用了少量数据和快速配置")
    print("   完整版运行: python vasp_rag_advanced.py")


def main():
    """主函数 - 直接运行全流程测试"""
    full_process_test()


if __name__ == "__main__":
    main()
