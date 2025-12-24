"""
纯嵌入版本 - 无交互，只负责构建向量数据库
"""

import json
import os
import time
from tqdm import tqdm
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document


def check_servers():
    """检查服务器状态"""
    import requests
    servers = [
        {"host": "192.168.1.127", "port": 11434},
        {"host": "127.0.0.1", "port": 11434},
        {"host": "192.168.1.130", "port": 11434}
    ]

    print("🔍 检查服务器...")
    online = []
    for server in servers:
        try:
            url = f"http://{server['host']}:{server['port']}/api/version"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                online.append(server)
                print(f"✅ {server['host']}:{server['port']} 在线")
        except:
            print(f"❌ {server['host']}:{server['port']} 离线")

    return online


def load_documents(json_file):
    """加载文档"""
    print(f"\n📂 加载数据: {json_file}")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    documents = []
    for item in tqdm(data, desc="处理文档"):
        if "Redirect to:" in item.get('content', ''):
            continue

        content = f"标题: {item['title']}\nURL: {item['url']}\n内容: {item['content']}"
        doc = Document(
            page_content=content,
            metadata={'title': item['title'], 'url': item['url']}
        )
        documents.append(doc)

    print(f"✅ 加载了 {len(documents)} 个文档")
    return documents


def split_documents(documents, chunk_size=1000, chunk_overlap=200):
    """文档分块"""
    print(f"\n✂️  文档分块 (size={chunk_size}, overlap={chunk_overlap})")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        add_start_index=True,
    )

    split_docs = []
    for doc in tqdm(documents, desc="分块处理"):
        chunks = splitter.split_documents([doc])
        split_docs.extend(chunks)

    print(f"✅ 分块完成，共 {len(split_docs)} 个文本块")
    return split_docs


def build_vectorstore(split_docs, persist_dir, server_config):
    """构建向量存储"""
    print(f"\n🏗️  构建向量数据库...")
    print(f"   模型: {server_config['model']}")
    print(f"   服务器: {server_config['base_url']}")
    print(f"   文本块: {len(split_docs)}")

    # 删除旧数据库
    if os.path.exists(persist_dir):
        import shutil
        shutil.rmtree(persist_dir)
        print("🗑️  已删除旧数据库")

    # 创建嵌入
    embeddings = OllamaEmbeddings(
        model=server_config['model'],
        base_url=server_config['base_url']
    )

    # 测试嵌入
    print("\n🧪 测试嵌入...")
    try:
        test_emb = embeddings.embed_query("VASP test")
        print(f"✅ 嵌入正常，维度: {len(test_emb)}")
    except Exception as e:
        print(f"❌ 嵌入测试失败: {e}")
        return False

    # 构建向量存储
    print("\n💾 保存到数据库...")
    start_time = time.time()

    try:
        vectorstore = Chroma.from_documents(
            documents=split_docs,
            embedding=embeddings,
            persist_directory=persist_dir
        )

        elapsed = time.time() - start_time
        speed = len(split_docs) / elapsed if elapsed > 0 else 0

        print(f"\n✅ 向量数据库构建完成!")
        print(f"   总耗时: {elapsed:.1f}秒")
        print(f"   平均速度: {speed:.1f} 文档/秒")
        print(f"   保存位置: {persist_dir}")

        return True

    except Exception as e:
        print(f"\n❌ 构建失败: {e}")
        return False


def test_retrieval(persist_dir, server_config):
    """测试检索"""
    print("\n" + "="*60)
    print("🎯 测试检索功能")
    print("="*60)

    # 加载向量存储
    embeddings = OllamaEmbeddings(
        model=server_config['model'],
        base_url=server_config['base_url']
    )

    vectorstore = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings
    )

    # 测试查询
    test_queries = [
        "什么是 RPA 计算？",
        "ALGO 参数有哪些选项？",
        "如何设置 INCAR 文件？"
    ]

    for query in test_queries:
        print(f"\n🔍 查询: '{query}'")
        results = vectorstore.similarity_search(query, k=3)

        print(f"检索到 {len(results)} 个相关文档:")
        for i, doc in enumerate(results, 1):
            print(f"  {i}. {doc.metadata.get('title', 'N/A')}")
            print(f"     预览: {doc.page_content[:100]}...")


def main():
    """主函数"""
    print("="*70)
    print("🚀 VASP RAG - 纯嵌入构建版本")
    print("="*70)

    # 配置
    config = {
        "json_file": "vasp_wiki_all_data.json",
        "persist_dir": "./chroma_db",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "model": "qwen3-embedding:8b"
    }

    # 1. 检查服务器
    servers = check_servers()
    if not servers:
        print("\n❌ 没有可用服务器")
        return

    # 选择主服务器 (使用第一个在线的)
    server_config = {
        'model': config['model'],
        'base_url': f"http://{servers[0]['host']}:{servers[0]['port']}"
    }

    print(f"\n✅ 使用服务器: {servers[0]['host']}:{servers[0]['port']}")

    # 2. 加载文档
    documents = load_documents(config['json_file'])

    # 3. 文档分块
    split_docs = split_documents(
        documents,
        chunk_size=config['chunk_size'],
        chunk_overlap=config['chunk_overlap']
    )

    # 4. 构建向量存储
    success = build_vectorstore(
        split_docs,
        config['persist_dir'],
        server_config
    )

    if success:
        # 5. 测试检索
        test_retrieval(config['persist_dir'], server_config)

        print("\n" + "="*70)
        print("🎉 嵌入完成！")
        print("="*70)
        print("\n💡 下一步:")
        print("   可以使用原始的 vasp_rag.py 或 vasp_rag_advanced.py")
        print("   它们会自动加载已构建的向量数据库")
    else:
        print("\n❌ 嵌入失败，请检查服务器连接")


if __name__ == "__main__":
    main()