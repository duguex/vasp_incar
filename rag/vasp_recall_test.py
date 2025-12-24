"""
VASP RAG 召回率测试 - 精简版
"""

import json
import os
import requests
from typing import List, Dict, Optional
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document


def find_embedding_model():
    """查找可用的嵌入模型（优先 nomic）"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=3)
        models = response.json().get('models', [])
        model_names = [m['name'] for m in models]

        # 优先 nomic，然后其他 embedding 模型
        for model in model_names:
            if 'nomic-embed-text-v2-moe' in model:
                return model

        for model in model_names:
            if 'embedding' in model.lower():
                return model

        return model_names[0] if model_names else None
    except:
        return None


def load_algo_queries():
    """加载 ALGO 测试查询"""
    # return [
    #     {"query": "ALGO 参数有哪些选项？分别代表什么含义？", "description": "ALGO 参数选项查询"},
    #     {"query": "什么是共轭梯度算法？如何设置？", "description": "共轭梯度算法查询"},
    #     {"query": "如何进行电子步优化？有哪些算法可选？", "description": "电子步优化查询"},
    #     {"query": "BFGS 算法是什么？如何使用？", "description": "BFGS 算法查询"},
    #     {"query": "damped 算法的使用场景和参数设置", "description": "阻尼算法查询"},
    # ]

    return [
        {"query": "In electronic structure calculations, how to keep the given wavefunction unchanged while computing specific occupied electronic states?", "description": "Fixed wavefunction constraint query"},
        {"query": "How to implement calculations of specific occupied electronic states within the frozen Kohn-Sham orbital framework?", "description": "Frozen Kohn-Sham orbitals implementation"},
        {"query": "In electronic structure theory, what is the methodology or constraint to compute properties of specific occupied electron states while preventing the relaxation or change of the overall many-body wavefunction?", "description": "Methodology for fixed wavefunction calculations"},
        {"query": "What are the specific algorithms or steps to perform calculations for individual occupied states using a fixed orbital approach based on the Kohn-Sham Hamiltonian?", "description": "Fixed orbital algorithm steps"},
        {"query": "How to enforce a fixed wavefunction constraint when calculating specific occupied electronic states in DFT or Hartree-Fock calculations?", "description": "Fixed wavefunction enforcement methods"}
    ]


def test_retrieval(vectorstore, queries: List[Dict], k: int = 10):
    """执行检索测试"""
    print(f"\n{'='*80}")
    print(f"ALGO 检索测试 (k={k})")
    print(f"{'='*80}")

    results = []
    for i, q in enumerate(queries, 1):
        print(f"\n 测试 {i}: {q['description']}")
        print(f"查询: {q['query']}")

        docs = vectorstore.similarity_search(q['query'], k=k)
        print(f"检索到 {len(docs)} 个文档")

        if docs:
            for j, doc in enumerate(docs, 1):
                title = doc.metadata.get('title', 'N/A')
                content = doc.page_content.replace('\n', ' ')
                print(f"  {j}. [{title}] {content}...")

        results.append({
            'query': q['query'],
            'description': q['description'],
            'retrieved_count': len(docs),
            'top_docs': [{
                'title': d.metadata.get('title', 'N/A'),
                'content': d.page_content
            } for d in docs]
        })

    return results


def main():
    """主流程"""
    print("="*80)
    print("🚀 VASP ALGO 检索召回率测试")
    print("="*80)

    # 检查服务器
    print("\n🔍 检查 Ollama 服务器...")
    model = find_embedding_model()
    if not model:
        print("❌ 无法连接服务器或未找到嵌入模型")
        return

    print(f"✅ 使用模型: {model}")

    # 加载向量数据库
    print("\n📂 加载向量数据库...")
    embedder = OllamaEmbeddings(model=model, base_url="http://localhost:11434")

    db_path = "./chroma_db"
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        return

    vectorstore = Chroma(
        embedding_function=embedder,
        collection_name="vasp_rag",
        persist_directory=db_path
    )

    # 检查数据库
    import chromadb
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_collection("vasp_rag")
    print(f"✅ 数据库加载成功，包含 {collection.count()} 个文档")

    # 加载测试查询
    queries = load_algo_queries()
    print(f"\n📋 创建 {len(queries)} 个测试查询")
    for i, q in enumerate(queries, 1):
        print(f"  {i}. {q['description']}")

    results = test_retrieval(vectorstore, queries)
    # 保存结果
    with open("algo_recall_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 结果已保存到 algo_recall_test_results.json")

    print("\n✅ 测试完成！")


if __name__ == "__main__":
    main()