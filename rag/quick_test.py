"""
快速测试 VASP RAG 系统
"""

import json
import os
import time
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser


def test_rag():
    """快速测试 RAG 功能"""
    print("=" * 60)
    print("VASP RAG - 快速测试")
    print("=" * 60)

    # 配置
    embedding_model = "qwen3-embedding:8b"
    chat_model = "qwen3:4b-instruct-2507-q4_K_M"
    json_file = "vasp_wiki_all_data.json"
    persist_dir = "./chroma_db"

    # 1. 检查数据文件
    if not os.path.exists(json_file):
        print(f"❌ 数据文件不存在: {json_file}")
        return

    print(f"✅ 数据文件存在: {json_file}")

    # 2. 加载少量数据进行测试
    print("\n📊 加载测试数据...")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 只取前10个文档进行快速测试
    test_data = data[:10]
    documents = []

    for item in test_data:
        if "Redirect to:" in item.get('content', ''):
            continue

        content = f"标题: {item['title']}\nURL: {item['url']}\n内容: {item['content']}"
        doc = Document(
            page_content=content,
            metadata={'title': item['title'], 'url': item['url']}
        )
        documents.append(doc)

    print(f"✅ 加载了 {len(documents)} 个测试文档")

    # 3. 文档分块
    print("\n✂️  文档分块...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
    )
    split_docs = text_splitter.split_documents(documents)
    print(f"✅ 分块完成，共 {len(split_docs)} 个文本块")

    # 4. 创建嵌入和向量存储
    print(f"\n🧠 创建嵌入向量 (模型: {embedding_model})...")
    embeddings = OllamaEmbeddings(
        model=embedding_model,
        base_url="http://localhost:11434"
    )

    # 测试嵌入
    try:
        test_emb = embeddings.embed_query("VASP test")
        print(f"✅ 嵌入测试成功，维度: {len(test_emb)}")
    except Exception as e:
        print(f"❌ 嵌入测试失败: {e}")
        return

    # 创建向量存储
    print("\n💾 构建向量数据库...")
    if os.path.exists(persist_dir):
        import shutil
        shutil.rmtree(persist_dir)

    vectorstore = Chroma.from_documents(
        documents=split_docs,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    print("✅ 向量数据库构建完成")

    # 5. 测试检索
    print("\n🔍 测试检索功能...")
    test_query = "RPA 计算"
    results = vectorstore.similarity_search(test_query, k=3)

    print(f"查询: '{test_query}'")
    print(f"检索到 {len(results)} 个相关文档:")

    for i, doc in enumerate(results, 1):
        print(f"\n--- 结果 {i} ---")
        print(f"标题: {doc.metadata.get('title', 'N/A')}")
        print(f"内容预览: {doc.page_content[:200]}...")

    # 6. 测试问答链
    print("\n🤖 测试问答链...")

    # 创建检索器
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    # 提示模板
    prompt_template = """
    你是一个 VASP (Vienna Ab initio Simulation Package) 专家助手。

    请基于以下上下文信息，回答用户的问题。如果上下文中没有相关信息，请说明你不知道，不要编造答案。

    上下文:
    {context}

    问题: {question}

    请用中文详细回答，并尽可能提供相关的技术细节。
    """

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    # LLM
    llm = ChatOllama(
        model=chat_model,
        base_url="http://localhost:11434",
        temperature=0.1
    )

    # RAG 链
    def format_docs(docs):
        return "\n\n".join([doc.page_content for doc in docs])

    rag_chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough()
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    # 测试问题
    test_questions = [
        "什么是 RPA 计算？",
        "ALGO 参数有哪些选项？"
    ]

    for question in test_questions:
        print(f"\n【问题】: {question}")
        print("【回答】: ", end="", flush=True)

        try:
            start_time = time.time()
            answer = rag_chain.invoke(question)
            end_time = time.time()
            print(f"\n{answer}")
            print(f"(耗时: {end_time - start_time:.1f}秒)")
        except Exception as e:
            print(f"错误: {e}")

    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    print("\n💡 系统已就绪，可以运行完整版: python vasp_rag.py")


if __name__ == "__main__":
    test_rag()