"""
VASP RAG System - 高级版
支持进度条、远程 Ollama 服务器、并行加速
"""

import json
import os
import requests
import asyncio
import time
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser


class RemoteOllamaConfig:
    """远程 Ollama 服务器配置"""

    def __init__(self):
        self.servers = [
            {"host": "192.168.1.130", "port": 11434, "status": "checking"},
            {"host": "192.168.1.127", "port": 11434, "status": "checking"},
            {"host": "localhost", "port": 11434, "status": "checking"}  # 本地作为备用
        ]

    def check_servers(self):
        """检查所有服务器状态"""
        print("🔍 检查远程 Ollama 服务器...")

        def check_server(server):
            try:
                url = f"http://{server['host']}:{server['port']}/api/version"
                response = requests.get(url, timeout=3)
                if response.status_code == 200:
                    server['status'] = 'online'
                    server['version'] = response.json().get('version', 'unknown')
                    return server
            except:
                server['status'] = 'offline'
            return server

        # 并行检查服务器
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(check_server, server) for server in self.servers]
            results = []
            for future in tqdm(as_completed(futures), total=len(self.servers), desc="检查服务器"):
                results.append(future.result())

        self.servers = results

        # 显示结果
        print("\n📊 服务器状态:")
        for server in self.servers:
            status_icon = "✅" if server['status'] == 'online' else "❌"
            print(f"   {status_icon} {server['host']}:{server['port']} - {server['status']}")
            if server['status'] == 'online':
                print(f"      版本: {server.get('version', '未知')}")

        return [s for s in self.servers if s['status'] == 'online']

    def get_available_models(self, server):
        """获取指定服务器上的模型列表"""
        try:
            url = f"http://{server['host']}:{server['port']}/api/tags"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [model['name'] for model in models]
        except:
            pass
        return []

    def find_best_embedding_model(self):
        """在所有服务器中查找最佳嵌入模型"""
        print("\n🔍 在所有服务器中查找嵌入模型...")

        preferred_models = ['qwen3-embedding', 'qwen2.5', 'nomic-embed-text', 'bge-m3', 'mxbai-embed-large']
        available_models = {}

        # 收集所有服务器的模型
        for server in self.servers:
            if server['status'] == 'online':
                models = self.get_available_models(server)
                if models:
                    available_models[server['host']] = models

        # 查找最佳匹配
        best_match = None
        best_server = None

        for preferred in preferred_models:
            for server_host, models in available_models.items():
                for model in models:
                    if preferred in model.lower():
                        best_match = model
                        best_server = server_host
                        break
                if best_match:
                    break
            if best_match:
                break

        if best_match:
            # 获取对应服务器配置
            server_config = next(s for s in self.servers if s['host'] == best_server)
            print(f"✅ 找到最佳嵌入模型: {best_match}")
            print(f"   服务器: {best_server}:{server_config['port']}")
            return {
                'model': best_match,
                'base_url': f"http://{best_server}:{server_config['port']}",
                'server': best_server
            }

        return None


class ParallelEmbeddingGenerator:
    """并行嵌入生成器"""

    def __init__(self, server_configs: List[Dict], max_workers: int = 4):
        self.server_configs = server_configs
        self.max_workers = max_workers
        self.current_server_idx = 0

    def get_next_server(self):
        """轮询获取下一个服务器"""
        if not self.server_configs:
            return None
        server = self.server_configs[self.current_server_idx % len(self.server_configs)]
        self.current_server_idx += 1
        return server

    def generate_embeddings_batch(self, texts: List[str], model: str) -> List[List[float]]:
        """为一批文本生成嵌入"""
        server = self.get_next_server()
        if not server:
            raise ValueError("没有可用的服务器")

        embeddings = OllamaEmbeddings(
            model=model,
            base_url=server['base_url']
        )

        # 批量生成嵌入
        return embeddings.embed_documents(texts)

    def generate_embeddings_parallel(self, texts: List[str], model: str, batch_size: int = 10) -> List[List[float]]:
        """并行生成嵌入"""
        if not texts:
            return []

        all_embeddings = []

        # 分批处理
        for i in tqdm(range(0, len(texts), batch_size), desc="生成嵌入向量"):
            batch = texts[i:i+batch_size]

            # 使用多线程处理批次
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(self.server_configs))) as executor:
                # 将批次拆分给不同服务器
                chunk_size = len(batch) // len(self.server_configs) + 1
                chunks = [batch[j:j+chunk_size] for j in range(0, len(batch), chunk_size)]

                futures = []
                for chunk in chunks:
                    if chunk:
                        future = executor.submit(self.generate_embeddings_batch, chunk, model)
                        futures.append(future)

                for future in as_completed(futures):
                    try:
                        embeddings = future.result()
                        all_embeddings.extend(embeddings)
                    except Exception as e:
                        print(f"⚠️  嵌入生成失败: {e}")

        return all_embeddings


class VASPRAGAdvanced:
    """增强版 VASP RAG 系统"""

    def __init__(self,
                 server_hosts: List[str] = None,
                 max_workers: int = 4,
                 chunk_size: int = 1000,
                 chunk_overlap: int = 200,
                 persist_dir: str = "./chroma_db"):
        """
        初始化增强版 RAG 系统

        Args:
            server_hosts: 远程服务器列表
            max_workers: 最大并行工作数
            chunk_size: 文本分块大小
            chunk_overlap: 文本分块重叠
            persist_dir: 向量数据库持久化目录
        """
        self.server_hosts = server_hosts or ["192.168.1.130", "192.168.1.127", "localhost"]
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.persist_dir = persist_dir
        self.vectorstore = None
        self.llm = None
        self.embedding_config = None
        self.parallel_generator = None

        # 初始化远程配置
        self.remote_config = RemoteOllamaConfig()
        self.remote_config.servers = [
            {"host": host, "port": 11434, "status": "checking"}
            for host in self.server_hosts
        ]

    def setup_servers(self):
        """设置并检查服务器"""
        online_servers = self.remote_config.check_servers()

        if not online_servers:
            print("❌ 没有可用的服务器")
            return False

        # 查找最佳嵌入模型
        self.embedding_config = self.remote_config.find_best_embedding_model()

        if not self.embedding_config:
            print("❌ 未找到可用的嵌入模型")
            return False

        # 准备并行生成器
        available_servers = [
            {
                'host': s['host'],
                'port': s['port'],
                'base_url': f"http://{s['host']}:{s['port']}"
            }
            for s in online_servers
        ]

        self.parallel_generator = ParallelEmbeddingGenerator(available_servers, self.max_workers)

        print(f"\n✅ 服务器配置完成")
        print(f"   嵌入模型: {self.embedding_config['model']}")
        print(f"   主服务器: {self.embedding_config['server']}")
        print(f"   可用服务器数: {len(available_servers)}")
        print(f"   并行工作数: {self.max_workers}")

        return True

    def load_data(self, json_file_path: str) -> List[Document]:
        """加载数据（带进度条）"""
        print(f"\n📂 加载数据: {json_file_path}")

        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        documents = []
        for item in tqdm(data, desc="处理文档"):
            if "Redirect to:" in item.get('content', ''):
                continue

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

        print(f"✅ 成功加载 {len(documents)} 个文档")
        return documents

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """文档分块（带进度条）"""
        print(f"\n✂️  文档分块 (chunk_size={self.chunk_size}, overlap={self.chunk_overlap})")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            add_start_index=True,
        )

        # 分块处理
        split_docs = []
        for doc in tqdm(documents, desc="分块处理"):
            chunks = text_splitter.split_documents([doc])
            split_docs.extend(chunks)

        print(f"✅ 分块完成，共 {len(split_docs)} 个文本块")
        return split_docs

    def build_vectorstore(self, split_docs: List[Document], force_rebuild: bool = False):
        """构建向量存储（带进度条和并行加速）"""
        if os.path.exists(self.persist_dir) and not force_rebuild:
            print(f"\n📂 加载现有向量数据库: {self.persist_dir}")
            embeddings = OllamaEmbeddings(
                model=self.embedding_config['model'],
                base_url=self.embedding_config['base_url']
            )
            self.vectorstore = Chroma(
                persist_directory=self.persist_dir,
                embedding_function=embeddings
            )
            print("✅ 向量数据库加载完成")
            return

        if force_rebuild and os.path.exists(self.persist_dir):
            import shutil
            shutil.rmtree(self.persist_dir)
            print("🗑️  已删除旧的向量数据库")

        print(f"\n🏗️  构建新的向量数据库...")
        print(f"   文本块数量: {len(split_docs)}")
        print(f"   使用嵌入模型: {self.embedding_config['model']}")
        print(f"   并行服务器: {self.max_workers} 个")

        # 提取文本内容
        texts = [doc.page_content for doc in split_docs]
        metadatas = [doc.metadata for doc in split_docs]

        # 使用并行生成嵌入
        print("\n🔄 生成嵌入向量 (并行加速)...")
        start_time = time.time()

        embeddings_list = self.parallel_generator.generate_embeddings_parallel(
            texts,
            self.embedding_config['model'],
            batch_size=20
        )

        embedding_time = time.time() - start_time
        print(f"✅ 嵌入生成完成，耗时: {embedding_time:.1f}秒")

        # 创建向量存储
        print("\n💾 保存到向量数据库...")
        embeddings = OllamaEmbeddings(
            model=self.embedding_config['model'],
            base_url=self.embedding_config['base_url']
        )

        # 批量添加到 ChromaDB
        batch_size = 100
        total_batches = (len(split_docs) + batch_size - 1) // batch_size

        with tqdm(total=len(split_docs), desc="保存到数据库") as pbar:
            for i in range(0, len(split_docs), batch_size):
                batch_docs = split_docs[i:i+batch_size]
                batch_embeddings = embeddings_list[i:i+batch_size]

                # 手动创建向量存储
                if i == 0:
                    self.vectorstore = Chroma.from_documents(
                        documents=batch_docs,
                        embedding=embeddings,
                        persist_directory=self.persist_dir
                    )
                else:
                    self.vectorstore.add_documents(batch_docs)

                pbar.update(len(batch_docs))

        print(f"✅ 向量数据库构建完成")
        print(f"   总耗时: {time.time() - start_time:.1f}秒")
        print(f"   平均速度: {len(split_docs)/(time.time() - start_time):.1f} 文档/秒")

    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        """相似性搜索"""
        if self.vectorstore is None:
            raise ValueError("向量数据库尚未初始化")

        print(f"\n🔍 执行相似性搜索: '{query}'")
        results = self.vectorstore.similarity_search(query, k=k)
        return results

    def setup_qa_chain(self):
        """设置问答链"""
        if self.vectorstore is None:
            raise ValueError("向量数据库尚未初始化")

        retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}
        )

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

        # 选择对话模型 (优先使用本地或远程服务器)
        chat_model = "qwen3:4b-instruct-2507-q4_K_M"
        base_url = self.embedding_config['base_url'] if self.embedding_config else "http://localhost:11434"

        print(f"\n🤖 配置对话模型: {chat_model}")
        print(f"   服务器: {base_url}")

        self.llm = ChatOllama(
            model=chat_model,
            base_url=base_url,
            temperature=0.1
        )

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

    def query(self, question: str, use_rag: bool = True, show_results: bool = True) -> str:
        """执行查询"""
        if use_rag:
            # 检索
            results = self.similarity_search(question, k=5)

            if show_results:
                print("\n📋 检索到的相关文档:")
                for i, doc in enumerate(results, 1):
                    print(f"\n--- 结果 {i} ---")
                    print(f"标题: {doc.metadata.get('title', 'N/A')}")
                    print(f"URL: {doc.metadata.get('url', 'N/A')}")
                    print(f"内容预览: {doc.page_content[:200]}...")

            # 生成回答
            qa_chain = self.setup_qa_chain()
            print("\n💭 正在生成回答...")

            start_time = time.time()
            answer = qa_chain.invoke(question)
            end_time = time.time()

            print(f"✅ 回答生成完成 (耗时: {end_time - start_time:.1f}秒)")
            return answer
        else:
            # 直接使用 LLM
            base_url = self.embedding_config['base_url'] if self.embedding_config else "http://localhost:11434"
            llm = ChatOllama(
                model="qwen3:4b-instruct-2507-q4_K_M",
                base_url=base_url,
                temperature=0.1
            )

            prompt = f"你是一个 VASP 专家，请回答以下问题: {question}"
            return llm.invoke(prompt).content


def main():
    """主函数"""
    print("=" * 70)
    print("🚀 VASP RAG 高级版 - 并行加速 + 远程服务器")
    print("=" * 70)

    # 配置 (根据测试结果自动优化)
    config = {
        "json_file": "vasp_wiki_all_data.json",
        # 优先使用在线服务器，按响应速度排序
        "server_hosts": ["192.168.1.127", "127.0.0.1", "192.168.1.130", "localhost"],
        "max_workers": 3,           # 并行工作数 (与服务器数量一致)
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "persist_dir": "./chroma_db",
        "force_rebuild": False
    }

    # 初始化系统
    rag = VASPRAGAdvanced(
        server_hosts=config["server_hosts"],
        max_workers=config["max_workers"],
        chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"],
        persist_dir=config["persist_dir"]
    )

    # 设置服务器
    if not rag.setup_servers():
        return

    try:
        # 1. 加载数据
        documents = rag.load_data(config["json_file"])

        # 2. 文档分块
        split_docs = rag.split_documents(documents)

        # 3. 构建向量存储
        rag.build_vectorstore(split_docs, force_rebuild=config["force_rebuild"])

        # 4. 测试检索
        print("\n" + "=" * 70)
        print("🎯 测试检索功能")
        print("=" * 70)

        test_queries = [
            "什么是 RPA 计算？如何在 VASP 中设置 RPA 计算？",
            "ALGO 参数有哪些选项？分别代表什么含义？",
            "如何设置 INCAR 文件中的混合泛函参数？"
        ]

        for i, query in enumerate(test_queries, 1):
            print(f"\n【问题 {i}】: {query}")
            print("-" * 50)

            try:
                answer = rag.query(query, use_rag=True, show_results=True)
                print(f"\n【回答】:\n{answer}")
            except Exception as e:
                print(f"❌ 查询出错: {e}")

            print("\n" + "=" * 70)

        # 5. 交互式查询
        print("\n💬 进入交互式查询模式 (输入 'quit' 退出)")
        while True:
            try:
                user_query = input("\n请输入你的问题: ").strip()
                if user_query.lower() in ['quit', 'exit', '退出']:
                    break

                if not user_query:
                    continue

                answer = rag.query(user_query, use_rag=True, show_results=True)
                print(f"\n【回答】:\n{answer}")

            except KeyboardInterrupt:
                print("\n\n👋 程序已退出")
                break
            except Exception as e:
                print(f"❌ 错误: {e}")

    except Exception as e:
        print(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()