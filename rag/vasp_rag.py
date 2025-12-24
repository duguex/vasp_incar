"""
VASP RAG System
基于 LangChain 的 VASP 文档检索增强生成系统
"""

import json
import os
import requests
from typing import List, Dict
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser


class VASPRAG:
    def __init__(self,
                 embedding_model: str = "qwen2.5:7b",
                 persist_dir: str = "./chroma_db",
                 chunk_size: int = 1000,
                 chunk_overlap: int = 200):
        """
        初始化 VASP RAG 系统

        Args:
            embedding_model: Ollama 嵌入模型名称
            persist_dir: 向量数据库持久化目录
            chunk_size: 文本分块大小
            chunk_overlap: 文本分块重叠大小
        """
        self.embedding_model = embedding_model
        self.persist_dir = persist_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.vectorstore = None
        self.llm = None

    def load_data(self, json_file_path: str) -> List[Document]:
        """
        从 JSON 文件加载数据并转换为 Document 对象

        Args:
            json_file_path: JSON 文件路径

        Returns:
            Document 对象列表
        """
        print(f"正在加载数据: {json_file_path}")

        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        documents = []
        for item in data:
            # 跳过重定向内容
            if "Redirect to:" in item.get('content', ''):
                continue

            # 创建文档内容
            content = f"标题: {item['title']}\n"
            content += f"URL: {item['url']}\n"
            content += f"内容: {item['content']}"

            doc = Document(
                page_content=content,
                metadata={
                    'title': item['title'],
                    'url': item['url']
                }
            )
            documents.append(doc)

        print(f"成功加载 {len(documents)} 个文档")
        return documents

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        对文档进行分块处理

        Args:
            documents: 原始文档列表

        Returns:
            分块后的文档列表
        """
        print(f"正在对文档进行分块 (chunk_size={self.chunk_size}, chunk_overlap={self.chunk_overlap})")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            add_start_index=True,
        )

        split_docs = text_splitter.split_documents(documents)
        print(f"分块完成，共生成 {len(split_docs)} 个文本块")

        return split_docs

    def create_embeddings(self) -> OllamaEmbeddings:
        """
        创建 Ollama 嵌入模型

        Returns:
            OllamaEmbeddings 实例
        """
        print(f"正在初始化嵌入模型: {self.embedding_model}")

        embeddings = OllamaEmbeddings(
            model=self.embedding_model,
            base_url="http://localhost:11434"
        )

        return embeddings

    def build_vectorstore(self, split_docs: List[Document], force_rebuild: bool = False):
        """
        构建向量存储

        Args:
            split_docs: 分块后的文档列表
            force_rebuild: 是否强制重新构建
        """
        # 检查是否已存在持久化存储
        if os.path.exists(self.persist_dir) and not force_rebuild:
            print(f"发现现有向量数据库，正在加载: {self.persist_dir}")
            embeddings = self.create_embeddings()
            self.vectorstore = Chroma(
                persist_directory=self.persist_dir,
                embedding_function=embeddings
            )
            print("向量数据库加载完成")
        else:
            print("正在构建新的向量数据库...")
            if force_rebuild and os.path.exists(self.persist_dir):
                import shutil
                shutil.rmtree(self.persist_dir)
                print("已删除旧的向量数据库")

            embeddings = self.create_embeddings()

            print(f"正在为 {len(split_docs)} 个文本块生成嵌入向量...")
            self.vectorstore = Chroma.from_documents(
                documents=split_docs,
                embedding=embeddings,
                persist_directory=self.persist_dir
            )
            print("向量数据库构建完成并已持久化")

    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        """
        执行相似性搜索

        Args:
            query: 查询文本
            k: 返回结果数量

        Returns:
            相似文档列表
        """
        if self.vectorstore is None:
            raise ValueError("向量数据库尚未初始化，请先调用 build_vectorstore")

        print(f"\n执行相似性搜索: {query}")
        results = self.vectorstore.similarity_search(query, k=k)

        return results

    def setup_qa_chain(self):
        """
        设置问答链
        """
        if self.vectorstore is None:
            raise ValueError("向量数据库尚未初始化")

        # 创建检索器
        retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}
        )

        # 定义提示模板
        prompt_template = """
        你是一个 VASP (Vienna Ab initio Simulation Package) 专家助手。

        请基于以下上下文信息，回答用户的问题。如果上下文中没有相关信息，请说明你不知道，不要编造答案。

        上下文:
        {context}

        问题: {question}

        请用中文详细回答，并尽可能提供相关的技术细节和参数说明。
        """

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )

        # 使用 Ollama 创建 LLM
        # 注意：这里使用与嵌入模型不同的对话模型
        # 选择本地可用的对话模型
        self.llm = ChatOllama(
            model="qwen3:4b-instruct-2507-q4_K_M",  # 使用本地的对话模型
            base_url="http://localhost:11434",
            temperature=0.1
        )

        # 构建 RAG 链
        def format_docs(docs):
            return "\n\n".join([doc.page_content for doc in docs])

        rag_chain = (
            {
                "context": retriever | format_docs,
                "question": RunnablePassthrough()
            }
            | prompt
            | self.llm
            | StrOutputParser()
        )

        return rag_chain

    def query(self, question: str, use_rag: bool = True) -> str:
        """
        执行查询

        Args:
            question: 问题
            use_rag: 是否使用 RAG 检索

        Returns:
            回答文本
        """
        if use_rag:
            if self.vectorstore is None:
                raise ValueError("向量数据库尚未初始化")

            # 首先进行检索
            results = self.similarity_search(question, k=5)

            print("\n检索到的相关文档:")
            for i, doc in enumerate(results, 1):
                print(f"\n--- 结果 {i} ---")
                print(f"标题: {doc.metadata.get('title', 'N/A')}")
                print(f"URL: {doc.metadata.get('url', 'N/A')}")
                print(f"内容预览: {doc.page_content[:300]}...")

            # 使用问答链生成回答
            qa_chain = self.setup_qa_chain()
            print("\n正在生成回答...")
            answer = qa_chain.invoke(question)
            return answer
        else:
            # 直接使用 LLM (不使用 RAG)
            llm = ChatOllama(
                model="qwen3:4b-instruct-2507-q4_K_M",
                base_url="http://localhost:11434",
                temperature=0.1
            )

            prompt = f"你是一个 VASP 专家，请回答以下问题: {question}"
            return llm.invoke(prompt).content


def check_local_models():
    """检查本地可用的模型"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return [model['name'] for model in models]
    except:
        pass
    return []


def select_embedding_model():
    """选择嵌入模型"""
    print("\n🔍 检查本地模型...")

    local_models = check_local_models()

    if not local_models:
        print("❌ 未找到本地模型")
        print("\n请先安装至少一个模型，例如:")
        print("  ollama pull qwen2.5:7b")
        print("  ollama pull nomic-embed-text")
        return None

    print(f"\n📋 找到 {len(local_models)} 个本地模型:")
    for i, model in enumerate(local_models, 1):
        print(f"   {i}. {model}")

    # 自动选择支持嵌入的模型 (优先级排序)
    preferred_models = ['qwen3-embedding', 'qwen2.5', 'nomic-embed-text', 'bge-m3', 'mxbai-embed-large']

    for preferred in preferred_models:
        for model in local_models:
            if preferred in model.lower():
                print(f"\n✅ 自动选择嵌入模型: {model}")
                return model

    # 如果没有找到首选模型，但有模型，尝试第一个
    if local_models:
        print(f"\n⚠️  未找到推荐的嵌入模型，尝试使用: {local_models[0]}")
        return local_models[0]

    return None


def main():
    """主函数 - 演示 VASP RAG 系统的使用"""

    # 检查 Ollama 服务
    try:
        response = requests.get("http://localhost:11434/api/version", timeout=5)
        if response.status_code != 200:
            print("❌ Ollama 服务未运行")
            print("请先启动: ollama serve")
            return
    except:
        print("❌ 无法连接到 Ollama 服务")
        print("请确保 Ollama 正在运行: ollama serve")
        return

    # 选择嵌入模型
    embedding_model = select_embedding_model()
    if not embedding_model:
        return

    # 配置参数
    config = {
        "json_file": "vasp_wiki_all_data.json",
        "embedding_model": embedding_model,
        "persist_dir": "./chroma_db",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "force_rebuild": False  # 是否强制重新构建向量数据库
    }

    # 初始化 RAG 系统
    rag = VASPRAG(
        embedding_model=config["embedding_model"],
        persist_dir=config["persist_dir"],
        chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"]
    )

    try:
        # 1. 加载数据
        documents = rag.load_data(config["json_file"])

        # 2. 文档分块
        split_docs = rag.split_documents(documents)

        # 3. 构建向量存储
        rag.build_vectorstore(split_docs, force_rebuild=config["force_rebuild"])

        # 4. 测试检索功能
        print("\n" + "="*60)
        print("测试检索功能")
        print("="*60)

        test_queries = [
            "什么是 RPA 计算？如何在 VASP 中设置 RPA 计算？",
            "ALGO 参数有哪些选项？分别代表什么含义？",
            "如何设置 INCAR 文件中的混合泛函参数？"
        ]

        for i, query in enumerate(test_queries, 1):
            print(f"\n【问题 {i}】: {query}")
            print("-" * 50)

            try:
                answer = rag.query(query, use_rag=True)
                print(f"\n【回答】:\n{answer}")
            except Exception as e:
                print(f"查询出错: {e}")

            print("\n" + "="*60)

        # 5. 交互式查询
        print("\n进入交互式查询模式 (输入 'quit' 退出)")
        while True:
            user_query = input("\n请输入你的问题: ").strip()
            if user_query.lower() in ['quit', 'exit', '退出']:
                break

            if not user_query:
                continue

            try:
                answer = rag.query(user_query, use_rag=True)
                print(f"\n【回答】:\n{answer}")
            except Exception as e:
                print(f"查询出错: {e}")

    except Exception as e:
        print(f"程序执行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()