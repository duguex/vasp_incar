"""
VASP RAG 高级版 - 功能演示
展示进度条、远程服务器、并行加速
"""

import time
from vasp_rag_advanced import VASPRAGAdvanced


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


if __name__ == "__main__":
    demo()