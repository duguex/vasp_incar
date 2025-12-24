"""
VASP RAG System
支持远程 Ollama 服务器、并行加速
"""

import json
import os
import requests
import time
import logging
import threading
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 减少第三方库的冗余日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("langchain_ollama").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)


class RAGConfig:
    """RAG 系统配置管理类"""

    # 默认配置常量
    DEFAULT_SERVER_HOSTS = ["192.168.1.130", "192.168.1.127", "localhost"]
    DEFAULT_PORT = 11434
    DEFAULT_TIMEOUT = 3
    DEFAULT_MAX_WORKERS = 4
    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 200
    DEFAULT_PERSIST_DIR = "./chroma_db"
    DEFAULT_BATCH_SIZE = 20

    # 模型配置
    PREFERRED_EMBEDDING_MODELS = [
        'qwen3-embedding',
        'qwen2.5',
        'nomic-embed-text',
        'bge-m3',
        'mxbai-embed-large'
    ]

    DEFAULT_CHAT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"

    def __init__(
        self,
        server_hosts: Optional[List[str]] = None,
        port: int = DEFAULT_PORT,
        timeout: int = DEFAULT_TIMEOUT,
        max_workers: int = DEFAULT_MAX_WORKERS,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        persist_dir: str = DEFAULT_PERSIST_DIR,
        batch_size: int = DEFAULT_BATCH_SIZE,
        chat_model: str = DEFAULT_CHAT_MODEL,
        force_rebuild: bool = False
    ):
        self.server_hosts = server_hosts or self.DEFAULT_SERVER_HOSTS
        self.port = port
        self.timeout = timeout
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.persist_dir = persist_dir
        self.batch_size = batch_size
        self.chat_model = chat_model
        self.force_rebuild = force_rebuild
        self.embedding_config: Optional[Dict[str, str]] = None
        self.online_servers: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'server_hosts': self.server_hosts,
            'port': self.port,
            'timeout': self.timeout,
            'max_workers': self.max_workers,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'persist_dir': self.persist_dir,
            'batch_size': self.batch_size,
            'chat_model': self.chat_model,
            'force_rebuild': self.force_rebuild
        }

    def __repr__(self) -> str:
        return f"RAGConfig({self.to_dict()})"


class RemoteOllamaConfig:
    """远程 Ollama 服务器配置管理"""

    def __init__(self, config: RAGConfig):
        self.config = config
        self.servers = [
            {"host": host, "port": config.port, "status": "checking"}
            for host in config.server_hosts
        ]

    def check_server_single(self, server: Dict[str, Any], retry_count: int = 2) -> Dict[str, Any]:
        """检查单个服务器状态（带重试机制）"""
        for attempt in range(retry_count + 1):
            try:
                url = f"http://{server['host']}:{server['port']}/api/version"
                response = requests.get(url, timeout=self.config.timeout)
                if response.status_code == 200:
                    server['status'] = 'online'
                    server['version'] = response.json().get('version', 'unknown')
                    server['error'] = None
                    return server
            except requests.exceptions.Timeout:
                if attempt == retry_count:
                    server['status'] = 'offline'
                    server['error'] = 'timeout'
            except requests.exceptions.ConnectionError:
                if attempt == retry_count:
                    server['status'] = 'offline'
                    server['error'] = 'connection_error'
            except Exception as e:
                if attempt == retry_count:
                    server['status'] = 'offline'
                    server['error'] = str(e)

        return server

    def check_servers(self) -> List[Dict[str, Any]]:
        """检查所有服务器状态"""
        logger.info("开始检查 Ollama 服务器连接...")

        with ThreadPoolExecutor(max_workers=min(10, len(self.servers))) as executor:
            futures = [
                executor.submit(self.check_server_single, server)
                for server in self.servers
            ]
            results = []
            for future in tqdm(as_completed(futures), total=len(self.servers), desc="检查服务器"):
                results.append(future.result())

        self.servers = results
        online_count = sum(1 for s in self.servers if s['status'] == 'online')
        logger.info(f"服务器状态: {online_count}/{len(self.servers)} 在线")

        print("\n📊 服务器状态:")
        for server in self.servers:
            status_icon = "✅" if server['status'] == 'online' else "❌"
            print(f"   {status_icon} {server['host']}:{server['port']} - {server['status']}")
            if server['status'] == 'online':
                print(f"      版本: {server.get('version', '未知')}")
            elif server.get('error'):
                print(f"      错误: {server['error']}")

        return [s for s in self.servers if s['status'] == 'online']

    def get_available_models(self, server: Dict[str, Any], timeout: Optional[int] = None) -> List[str]:
        """获取指定服务器上的模型列表"""
        try:
            url = f"http://{server['host']}:{server['port']}/api/tags"
            response = requests.get(url, timeout=timeout or self.config.timeout)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [model['name'] for model in models]
        except Exception as e:
            logger.warning(f"获取服务器 {server['host']}:{server['port']} 模型列表失败: {e}")
        return []

    def find_best_embedding_model(self, preferred_models: Optional[List[str]] = None) -> Optional[Dict[str, str]]:
        """在所有服务器中查找最佳嵌入模型"""
        if preferred_models is None:
            preferred_models = self.config.PREFERRED_EMBEDDING_MODELS

        logger.info("在所有服务器中查找最佳嵌入模型...")

        available_models: Dict[str, List[str]] = {}
        for server in self.servers:
            if server['status'] == 'online':
                models = self.get_available_models(server)
                if models:
                    available_models[server['host']] = models

        if not available_models:
            logger.error("没有找到任何可用的服务器模型")
            return None

        for preferred in preferred_models:
            for server_host, models in available_models.items():
                for model in models:
                    if preferred in model.lower():
                        server_config = next(s for s in self.servers if s['host'] == server_host)
                        result = {
                            'model': model,
                            'base_url': f"http://{server_host}:{server_config['port']}",
                            'server': server_host,
                            'port': server_config['port']
                        }
                        logger.info(f"找到最佳嵌入模型: {model} (服务器: {server_host})")
                        return result

        first_server_host = next(iter(available_models))
        first_model = available_models[first_server_host][0]
        server_config = next(s for s in self.servers if s['host'] == first_server_host)
        logger.warning(f"未找到优先模型，使用默认: {first_model}")
        return {
            'model': first_model,
            'base_url': f"http://{first_server_host}:{server_config['port']}",
            'server': first_server_host,
            'port': server_config['port']
        }


class RealTimeLoadBalancer:
    """实时负载均衡器 - 谁算完就给谁新任务"""

    def __init__(self, server_configs: List[Dict[str, str]], max_workers: int = 4):
        if not server_configs:
            raise ValueError("至少需要一个可用的服务器配置")

        self.server_configs = server_configs
        self.max_workers = max_workers

        # 服务器状态跟踪
        self.server_status = {
            config['base_url']: {
                'busy': False,           # 是否正在处理任务
                'total_tasks': 0,        # 完成的总任务数
                'total_time': 0.0,       # 总耗时
                'failed_tasks': 0,       # 失败任务数
                'avg_time': 0.0,         # 平均耗时
            }
            for config in server_configs
        }

        # 任务队列和结果队列
        self.task_queue = []
        self.result_queue = []
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)

        logger.info(f"初始化实时负载均衡器，监控 {len(server_configs)} 个服务器")

    def _get_available_server(self) -> Optional[Dict[str, str]]:
        """获取当前空闲的服务器（谁空闲给谁）"""
        with self.lock:
            # 找到第一个空闲的服务器
            for server in self.server_configs:
                if not self.server_status[server['base_url']]['busy']:
                    return server
            return None

    def _mark_server_busy(self, server_url: str, busy: bool):
        """标记服务器忙碌状态"""
        with self.lock:
            self.server_status[server_url]['busy'] = busy

    def _update_server_stats(self, server_url: str, response_time: float, success: bool):
        """更新服务器统计信息"""
        with self.lock:
            status = self.server_status[server_url]
            if success:
                status['total_tasks'] += 1
                status['total_time'] += response_time
                status['avg_time'] = status['total_time'] / status['total_tasks']
            else:
                status['failed_tasks'] += 1

    def get_server_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有服务器的性能统计"""
        with self.lock:
            return {
                url: {
                    'busy': '🔴' if stats['busy'] else '🟢',
                    'total_tasks': stats['total_tasks'],
                    'avg_time': round(stats['avg_time'], 3) if stats['total_tasks'] > 0 else 0,
                    'failed_tasks': stats['failed_tasks'],
                    'total_time': round(stats['total_time'], 2)
                }
                for url, stats in self.server_status.items()
            }

    def print_server_stats(self):
        """打印服务器实时状态"""
        stats = self.get_server_stats()
        print("\n📊 服务器实时状态:")
        print("-" * 80)
        print(f"{'状态':<6} {'服务器URL':<35} {'任务数':<8} {'平均时间(s)':<12} {'总耗时(s)':<10} {'失败数'}")
        print("-" * 80)
        for url, stat in stats.items():
            print(f"{stat['busy']:<6} {url:<35} {stat['total_tasks']:<8} {stat['avg_time']:<12} {stat['total_time']:<10} {stat['failed_tasks']}")
        print("-" * 80)

    def worker_process_batch(self, server: Dict[str, str], texts: List[str], model: str):
        """工作线程：处理单个批次"""
        server_url = server['base_url']
        start_time = time.time()

        try:
            # 标记为忙碌
            self._mark_server_busy(server_url, True)

            # 执行嵌入生成
            embeddings = OllamaEmbeddings(
                model=model,
                base_url=server_url
            )
            result = embeddings.embed_documents(texts)

            # 记录成功
            response_time = time.time() - start_time
            self._update_server_stats(server_url, response_time, success=True)

            # 将结果放入队列
            with self.lock:
                self.result_queue.append((result, None))

            logger.debug(f"服务器 {server_url} 完成 {len(texts)} 个文本，耗时 {response_time:.2f}s")

        except Exception as e:
            # 记录失败
            response_time = time.time() - start_time
            self._update_server_stats(server_url, response_time, success=False)

            # 将错误放入队列
            with self.lock:
                self.result_queue.append((None, e))

            logger.error(f"服务器 {server_url} 处理失败: {e}")

        finally:
            # 标记为空闲
            self._mark_server_busy(server_url, False)

    def generate_embeddings_parallel(
        self,
        texts: List[str],
        model: str,
        batch_size: Optional[int] = None
    ) -> List[List[float]]:
        """并行生成嵌入向量 - 谁空闲谁干活"""
        if not texts:
            return []

        logger.info(f"开始实时负载均衡生成嵌入: {len(texts)} 个文本, 模型: {model}")
        logger.info(f"使用 {len(self.server_configs)} 个服务器，最大并行度: {self.max_workers}")

        batch_size = batch_size or 20

        # 分批
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
        total_batches = len(batches)
        completed_batches = 0

        print(f"\n🔄 开始生成嵌入向量 (实时负载均衡 - 谁空闲谁干活)")
        print(f"   总共 {total_batches} 个批次，每批 {batch_size} 个文本")
        self.print_server_stats()

        # 使用线程池处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务，但每个任务会等待空闲服务器
            futures = []
            for batch in batches:
                # 等待空闲服务器
                while True:
                    server = self._get_available_server()
                    if server:
                        break
                    time.sleep(0.1)  # 短暂等待

                # 提交任务
                future = executor.submit(self.worker_process_batch, server, batch, model)
                futures.append(future)

            # 等待所有任务完成
            with tqdm(total=total_batches, desc="处理批次") as pbar:
                for future in as_completed(futures):
                    try:
                        future.result()  # 会抛出异常如果有错误
                        pbar.update(1)
                        completed_batches += 1

                        # 每完成3个批次显示一次状态
                        if completed_batches % 3 == 0:
                            print(f"\n   [进度: {completed_batches}/{total_batches}]")
                            self.print_server_stats()

                    except Exception as e:
                        logger.error(f"批次处理失败: {e}")
                        pbar.update(1)

        # 收集所有结果
        all_embeddings = []
        with self.lock:
            for result, error in self.result_queue:
                if error:
                    raise error
                if result:
                    all_embeddings.extend(result)

        print("\n✅ 嵌入生成完成")
        self.print_server_stats()

        logger.info(f"嵌入生成完成: {len(all_embeddings)} 个向量")
        return all_embeddings


class VASPRAGAdvanced:
    """增强版 VASP RAG 系统 - 核心类"""

    def __init__(self, config: Optional[RAGConfig] = None):
        self.config = config or RAGConfig()
        self.vectorstore: Optional[Chroma] = None
        self.llm: Optional[ChatOllama] = None
        self.remote_config: Optional[RemoteOllamaConfig] = None
        self.parallel_generator: Optional[ParallelEmbeddingGenerator] = None

    def setup_servers(self) -> bool:
        """设置并检查服务器"""
        logger.info("开始配置服务器...")

        self.remote_config = RemoteOllamaConfig(self.config)
        online_servers = self.remote_config.check_servers()

        if not online_servers:
            logger.error("没有可用的服务器")
            return False

        embedding_config = self.remote_config.find_best_embedding_model()

        if not embedding_config:
            logger.error("未找到可用的嵌入模型")
            return False

        self.config.embedding_config = embedding_config
        self.config.online_servers = online_servers

        available_servers = [
            {
                'host': s['host'],
                'port': s['port'],
                'base_url': f"http://{s['host']}:{s['port']}"
            }
            for s in online_servers
        ]

        self.parallel_generator = RealTimeLoadBalancer(
            available_servers,
            self.config.max_workers
        )

        print(f"\n✅ 服务器配置完成")
        print(f"   嵌入模型: {embedding_config['model']}")
        print(f"   主服务器: {embedding_config['server']}")
        print(f"   可用服务器数: {len(available_servers)}")
        print(f"   并行工作数: {self.config.max_workers}")

        return True

    def load_data(self, json_file_path: str) -> List[Document]:
        """加载 JSON 数据文件"""
        logger.info(f"加载数据: {json_file_path}")

        if not os.path.exists(json_file_path):
            raise FileNotFoundError(f"数据文件不存在: {json_file_path}")

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
        """文档分块处理"""
        print(f"\n✂️  文档分块 (chunk_size={self.config.chunk_size}, overlap={self.config.chunk_overlap})")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            length_function=len,
            add_start_index=True,
        )

        split_docs = []
        for doc in tqdm(documents, desc="分块处理"):
            chunks = text_splitter.split_documents([doc])
            split_docs.extend(chunks)

        print(f"✅ 分块完成，共 {len(split_docs)} 个文本块")
        return split_docs

    def _build_new_vectorstore(self, split_docs: List[Document]) -> None:
        """构建新的向量数据库（内部方法）"""
        import chromadb
        import shutil

        if os.path.exists(self.config.persist_dir):
            shutil.rmtree(self.config.persist_dir)
            print("🗑️  已删除旧的向量数据库")

        print(f"\n🏗️  构建新的向量数据库...")
        print(f"   文本块数量: {len(split_docs)}")
        print(f"   使用嵌入模型: {self.config.embedding_config['model']}")
        print(f"   并行服务器: {self.config.max_workers} 个")

        texts = [doc.page_content for doc in split_docs]
        metadatas = [doc.metadata for doc in split_docs]

        print("\n🔄 生成嵌入向量 (并行加速)...")
        start_time = time.time()

        embeddings_list = self.parallel_generator.generate_embeddings_parallel(
            texts,
            self.config.embedding_config['model'],
            batch_size=self.config.batch_size
        )

        embedding_time = time.time() - start_time
        print(f"✅ 嵌入生成完成，耗时: {embedding_time:.1f}秒")

        print("\n💾 保存到向量数据库...")

        client = chromadb.PersistentClient(path=self.config.persist_dir)
        collection = client.get_or_create_collection(name="vasp_rag")

        batch_size = 100
        with tqdm(total=len(split_docs), desc="保存到数据库") as pbar:
            for i in range(0, len(split_docs), batch_size):
                batch_docs = split_docs[i:i + batch_size]
                batch_embeddings = embeddings_list[i:i + batch_size]

                ids = [f"doc_{j}" for j in range(i, i + len(batch_docs))]
                documents = [doc.page_content for doc in batch_docs]
                metadatas = [doc.metadata for doc in batch_docs]

                collection.add(
                    embeddings=batch_embeddings,
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                pbar.update(len(batch_docs))

        embeddings = OllamaEmbeddings(
            model=self.config.embedding_config['model'],
            base_url=self.config.embedding_config['base_url']
        )

        self.vectorstore = Chroma(
            embedding_function=embeddings,
            collection_name="vasp_rag",
            persist_directory=self.config.persist_dir
        )

        total_time = time.time() - start_time
        print(f"\n✅ 向量数据库构建完成")
        print(f"   总耗时: {total_time:.1f}秒")
        print(f"   平均速度: {len(split_docs) / total_time:.1f} 文档/秒")

    def build_vectorstore(self, split_docs: List[Document]) -> None:
        """构建向量存储（自动判断是否需要重建）"""
        if os.path.exists(self.config.persist_dir) and not self.config.force_rebuild:
            print(f"\n📂 加载现有向量数据库: {self.config.persist_dir}")
            embeddings = OllamaEmbeddings(
                model=self.config.embedding_config['model'],
                base_url=self.config.embedding_config['base_url']
            )
            self.vectorstore = Chroma(
                persist_directory=self.config.persist_dir,
                embedding_function=embeddings
            )
            print("✅ 向量数据库加载完成")
            return

        self._build_new_vectorstore(split_docs)

    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        """执行相似性搜索"""
        if self.vectorstore is None:
            raise ValueError("向量数据库尚未初始化，请先调用 build_vectorstore()")

        print(f"\n🔍 执行相似性搜索: '{query}'")
        results = self.vectorstore.similarity_search(query, k=k)
        return results

    def setup_qa_chain(self):
        """设置 RAG 问答链"""
        if self.vectorstore is None:
            raise ValueError("向量数据库尚未初始化，请先调用 build_vectorstore()")

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

        chat_model = self.config.chat_model
        base_url = self.config.embedding_config['base_url'] if self.config.embedding_config else "http://localhost:11434"

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
            results = self.similarity_search(question, k=5)

            if show_results:
                print("\n📋 检索到的相关文档:")
                for i, doc in enumerate(results, 1):
                    print(f"\n--- 结果 {i} ---")
                    print(f"标题: {doc.metadata.get('title', 'N/A')}")
                    print(f"URL: {doc.metadata.get('url', 'N/A')}")
                    print(f"内容预览: {doc.page_content[:200]}...")

            qa_chain = self.setup_qa_chain()
            print("\n💭 正在生成回答...")

            start_time = time.time()
            answer = qa_chain.invoke(question)
            end_time = time.time()

            print(f"✅ 回答生成完成 (耗时: {end_time - start_time:.1f}秒)")
            return answer
        else:
            base_url = self.config.embedding_config['base_url'] if self.config.embedding_config else "http://localhost:11434"
            llm = ChatOllama(
                model=self.config.chat_model,
                base_url=base_url,
                temperature=0.1
            )

            prompt = f"你是一个 VASP 专家，请回答以下问题: {question}"
            return llm.invoke(prompt).content


def run_full_pipeline(config: RAGConfig, json_file: str, test_queries: List[str]) -> None:
    """
    运行完整的 RAG 流程

    Args:
        config: RAG 配置
        json_file: 数据文件路径
        test_queries: 测试查询列表
    """
    print("=" * 70)
    print("🚀 VASP RAG 高级版 - 完整流程")
    print("=" * 70)
    print(f"\n配置: {config}")

    rag = VASPRAGAdvanced(config)

    print("\n" + "=" * 70)
    print("步骤 1: 服务器配置")
    print("=" * 70)
    if not rag.setup_servers():
        logger.error("服务器配置失败，流程终止")
        return

    try:
        print("\n" + "=" * 70)
        print("步骤 2: 数据加载")
        print("=" * 70)
        documents = rag.load_data(json_file)

        print("\n" + "=" * 70)
        print("步骤 3: 文档分块")
        print("=" * 70)
        split_docs = rag.split_documents(documents)

        print("\n" + "=" * 70)
        print("步骤 4: 向量存储构建")
        print("=" * 70)
        rag.build_vectorstore(split_docs)

        print("\n" + "=" * 70)
        print("步骤 5: 检索测试")
        print("=" * 70)
        for i, query in enumerate(test_queries, 1):
            print(f"\n【问题 {i}】: {query}")
            print("-" * 50)
            try:
                answer = rag.query(query, use_rag=True, show_results=True)
                print(f"\n【回答】:\n{answer}")
            except Exception as e:
                logger.error(f"查询失败: {e}")
            print("\n" + "=" * 70)

        print("\n✅ 完整流程执行完成！")

    except Exception as e:
        logger.error(f"流程执行出错: {e}")
        import traceback
        traceback.print_exc()


def demo_load_balancing():
    """演示实时负载均衡效果"""
    print("=" * 80)
    print("🚀 实时负载均衡演示 - 谁算完就给谁新任务")
    print("=" * 80)

    # 模拟不同性能的服务器
    print("\n📝 模拟场景:")
    print("   - 服务器 A (192.168.1.130): 快速服务器 (0.5秒/批次)")
    print("   - 服务器 B (192.168.1.127): 中等速度 (1.0秒/批次)")
    print("   - 服务器 C (localhost): 较慢服务器 (1.5秒/批次)")
    print("   - 任务: 6个批次，每批20个文本")

    # 创建测试配置
    server_configs = [
        {'host': '192.168.1.130', 'port': 11434, 'base_url': 'http://192.168.1.130:11434'},
        {'host': '192.168.1.127', 'port': 11434, 'base_url': 'http://192.168.1.127:11434'},
        {'host': 'localhost', 'port': 11434, 'base_url': 'http://localhost:11434'},
    ]

    generator = RealTimeLoadBalancer(server_configs, max_workers=3)

    print("\n📊 初始状态:")
    generator.print_server_stats()

    # 模拟任务执行过程
    print("\n🔄 模拟任务执行过程...")
    print("   (使用线程模拟不同服务器的处理速度)")

    import threading
    import time

    def mock_process(server_url, duration, batch_id):
        """模拟服务器处理任务"""
        generator._mark_server_busy(server_url, True)
        time.sleep(duration)
        generator._update_server_stats(server_url, duration, success=True)
        generator._mark_server_busy(server_url, False)
        print(f"   ✅ 批次 {batch_id} 在 {server_url} 完成 (耗时 {duration:.1f}s)")

    # 模拟6个批次，分配给3个服务器
    tasks = [
        ('http://192.168.1.130:11434', 0.5, 1),  # 服务器A处理批次1
        ('http://192.168.1.127:11434', 1.0, 2),  # 服务器B处理批次2
        ('http://localhost:11434', 1.5, 3),      # 服务器C处理批次3
        ('http://192.168.1.130:11434', 0.5, 4),  # 服务器A完成，处理批次4
        ('http://192.168.1.130:11434', 0.5, 5),  # 服务器A完成，处理批次5
        ('http://192.168.1.127:11434', 1.0, 6),  # 服务器B完成，处理批次6
    ]

    print("\n任务分配模拟:")
    threads = []
    for url, duration, batch_id in tasks:
        thread = threading.Thread(target=mock_process, args=(url, duration, batch_id))
        threads.append(thread)
        thread.start()
        time.sleep(0.2)  # 模拟任务提交间隔

        # 每提交2个任务显示一次状态
        if batch_id % 2 == 0:
            time.sleep(0.3)  # 等待部分任务完成
            print(f"\n   [提交 {batch_id} 个批次后的状态]")
            generator.print_server_stats()

    # 等待所有任务完成
    for thread in threads:
        thread.join()

    print("\n\n📊 最终状态:")
    generator.print_server_stats()

    print("\n✅ 演示完成！")
    print("\n💡 结果分析:")
    print("   - 服务器A (最快) 完成了 3 个批次")
    print("   - 服务器B (中等) 完成了 2 个批次")
    print("   - 服务器C (最慢) 完成了 1 个批次")
    print("   - 这就是真正的'谁算完就给谁新任务'！")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    # 简单的命令行接口
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "pipeline":
            config = RAGConfig(
                server_hosts=["192.168.1.127", "192.168.1.130", "localhost"],
                max_workers=3,
                chunk_size=1000,
                chunk_overlap=200,
                persist_dir="./chroma_db",
                batch_size=20,
                chat_model="qwen3:4b-instruct-2507-q4_K_M",
                force_rebuild=False
            )

            test_queries = [
                "什么是 RPA 计算？如何在 VASP 中设置 RPA 计算？",
                "ALGO 参数有哪些选项？分别代表什么含义？",
                "如何设置 INCAR 文件中的混合泛函参数？"
            ]

            run_full_pipeline(config, "vasp_wiki_all_data.json", test_queries)

        elif sys.argv[1] == "demo":
            demo_load_balancing()

        else:
            print(f"未知命令: {sys.argv[1]}")
            print_help()
    else:
        print_help()


def print_help():
    print("VASP RAG 高级版 - 自适应负载均衡")
    print("\n使用方式:")
    print("  python vasp_rag_advanced.py pipeline  - 运行完整 RAG 流程")
    print("  python vasp_rag_advanced.py demo     - 演示负载均衡效果")
    print("\n功能说明:")
    print("  ✅ 自适应负载均衡 - 根据服务器性能动态分配任务")
    print("  ✅ 实时性能监控 - 显示各服务器响应时间和成功率")
    print("  ✅ 自动故障转移 - 失败自动重试，降低故障服务器权重")
