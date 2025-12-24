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
    """RAG 系统配置管理类 - 支持环境变量和配置文件"""

    # 默认配置常量
    DEFAULT_SERVER_HOSTS = ["localhost", "192.168.1.130", "192.168.1.127"]
    DEFAULT_PORT = 11434
    DEFAULT_TIMEOUT = 3
    DEFAULT_MAX_WORKERS = 3
    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 200
    DEFAULT_PERSIST_DIR = "./chroma_db"
    DEFAULT_BATCH_SIZE = 20

    # 模型配置
    PREFERRED_EMBEDDING_MODELS = [
        'qwen3-embedding',
    ]

    DEFAULT_CHAT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"

    def __init__(
        self,
        server_hosts: Optional[List[str]] = None,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
        max_workers: Optional[int] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        persist_dir: Optional[str] = None,
        batch_size: Optional[int] = None,
        chat_model: Optional[str] = None,
        force_rebuild: bool = False
    ):
        # 优先级：参数 > 环境变量 > 默认值
        self.server_hosts = server_hosts or self._get_env_list('VASP_SERVER_HOSTS', self.DEFAULT_SERVER_HOSTS)
        self.port = port or self._get_env_int('VASP_SERVER_PORT', self.DEFAULT_PORT)
        self.timeout = timeout or self._get_env_int('VASP_SERVER_TIMEOUT', self.DEFAULT_TIMEOUT)
        self.max_workers = max_workers or self._get_env_int('VASP_MAX_WORKERS', self.DEFAULT_MAX_WORKERS)
        self.chunk_size = chunk_size or self._get_env_int('VASP_CHUNK_SIZE', self.DEFAULT_CHUNK_SIZE)
        self.chunk_overlap = chunk_overlap or self._get_env_int('VASP_CHUNK_OVERLAP', self.DEFAULT_CHUNK_OVERLAP)
        self.persist_dir = persist_dir or os.getenv('VASP_PERSIST_DIR', self.DEFAULT_PERSIST_DIR)
        self.batch_size = batch_size or self._get_env_int('VASP_BATCH_SIZE', self.DEFAULT_BATCH_SIZE)
        self.chat_model = chat_model or os.getenv('VASP_CHAT_MODEL', self.DEFAULT_CHAT_MODEL)
        self.force_rebuild = force_rebuild

        self.embedding_config: Optional[Dict[str, str]] = None
        self.online_servers: List[Dict[str, Any]] = []

    @staticmethod
    def _get_env_int(key: str, default: int) -> int:
        """从环境变量获取整数值"""
        value = os.getenv(key)
        if value:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"环境变量 {key} 值无效: {value}，使用默认值 {default}")
        return default

    @staticmethod
    def _get_env_list(key: str, default: List[str]) -> List[str]:
        """从环境变量获取列表值（支持 JSON 数组或逗号分隔）"""
        value = os.getenv(key)
        if not value:
            return default

        # 尝试解析 JSON 数组
        if value.strip().startswith('['):
            try:
                import json
                return json.loads(value)
            except:
                pass

        # 逗号分隔
        return [v.strip() for v in value.split(',') if v.strip()]

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


def check_ollama_server(host: str, port: int = 11434, timeout: int = 3, retry_count: int = 2) -> Dict[str, Any]:
    """
    检查单个 Ollama 服务器状态（带重试机制）

    Args:
        host: 服务器地址
        port: 端口号
        timeout: 超时时间（秒）
        retry_count: 重试次数

    Returns:
        服务器状态字典
    """
    server_info = {"host": host, "port": port, "status": "checking"}

    for attempt in range(retry_count + 1):
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
                        'model_count': len(models),
                        'error': None
                    }
                else:
                    # 只有版本接口成功，但模型接口失败
                    return {
                        'host': host,
                        'port': port,
                        'status': 'online',
                        'version': version,
                        'models': [],
                        'model_count': 0,
                        'error': None
                    }

        except requests.exceptions.Timeout:
            if attempt == retry_count:
                server_info['status'] = 'offline'
                server_info['error'] = 'timeout'
        except requests.exceptions.ConnectionError:
            if attempt == retry_count:
                server_info['status'] = 'offline'
                server_info['error'] = 'connection_error'
        except Exception as e:
            if attempt == retry_count:
                server_info['status'] = 'offline'
                server_info['error'] = str(e)

    return server_info


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
        return check_ollama_server(
            host=server['host'],
            port=server['port'],
            timeout=self.config.timeout,
            retry_count=retry_count
        )

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
    """实时负载均衡器 - 谁空闲谁干活，快服务器多干活"""

    def __init__(self, server_configs: List[Dict[str, str]], max_workers: int = 4):
        if not server_configs:
            raise ValueError("至少需要一个可用的服务器配置")

        self.server_configs = server_configs
        self.max_workers = max_workers

        # 预先创建所有嵌入客户端
        self.embedders = []
        for config in server_configs:
            try:
                embedder = OllamaEmbeddings(
                    model=config.get('model', 'placeholder'),
                    base_url=config['base_url']
                )
                self.embedders.append({
                    'client': embedder,
                    'base_url': config['base_url'],
                    'host': config.get('host', 'unknown'),
                    'lock': threading.Lock(),  # 每个服务器一把锁
                    'busy': False,             # 是否忙碌
                })
                logger.info(f"✅ 创建客户端: {config['base_url']}")
            except Exception as e:
                logger.error(f"❌ 创建客户端失败 {config['base_url']}: {e}")

        if not self.embedders:
            raise ValueError("没有可用的嵌入客户端")

        # 全局统计
        self.global_lock = threading.Lock()
        self.server_stats = {
            config['base_url']: {
                'total_tasks': 0,
                'total_time': 0.0,
                'failed_tasks': 0,
                'avg_time': 0.0,
            }
            for config in server_configs
        }

        logger.info(f"初始化实时负载均衡器，创建 {len(self.embedders)} 个嵌入客户端")

    def _find_available_server(self) -> Optional[Dict]:
        """查找第一个空闲的服务器（谁空闲给谁）"""
        for embedder in self.embedders:
            if not embedder['busy']:
                return embedder
        return None

    def _mark_server_busy(self, embedder: Dict, busy: bool):
        """标记服务器状态"""
        with embedder['lock']:
            embedder['busy'] = busy

    def _update_stats(self, server_url: str, response_time: float, success: bool):
        """更新全局统计"""
        with self.global_lock:
            stats = self.server_stats[server_url]
            if success:
                stats['total_tasks'] += 1
                stats['total_time'] += response_time
                stats['avg_time'] = stats['total_time'] / stats['total_tasks']
            else:
                stats['failed_tasks'] += 1

    def get_server_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有服务器的性能统计"""
        with self.global_lock:
            return {
                url: {
                    'total_tasks': stats['total_tasks'],
                    'avg_time': round(stats['avg_time'], 3) if stats['total_tasks'] > 0 else 0,
                    'failed_tasks': stats['failed_tasks'],
                    'total_time': round(stats['total_time'], 2)
                }
                for url, stats in self.server_stats.items()
            }

    def print_server_stats(self):
        """打印服务器性能统计"""
        stats = self.get_server_stats()
        print("\n📊 服务器性能统计:")
        print("-" * 70)
        print(f"{'服务器URL':<35} {'任务数':<8} {'平均时间(s)':<12} {'总耗时(s)':<10} {'失败数'}")
        print("-" * 70)
        for url, stat in stats.items():
            print(f"{url:<35} {stat['total_tasks']:<8} {stat['avg_time']:<12} {stat['total_time']:<10} {stat['failed_tasks']}")
        print("-" * 70)

    def process_single_batch(self, texts: List[str], model: str) -> List[List[float]]:
        """处理单个批次 - 等待空闲服务器"""
        # 等待空闲服务器
        while True:
            embedder = self._find_available_server()
            if embedder:
                break
            time.sleep(0.5)  # 500ms检查一次

        # 标记为忙碌
        self._mark_server_busy(embedder, True)

        base_url = embedder['base_url']
        client = embedder['client']
        client.model = model  # 设置模型

        start_time = time.time()

        try:
            # 执行嵌入生成
            result = client.embed_documents(texts)

            # 记录成功
            response_time = time.time() - start_time
            self._update_stats(base_url, response_time, success=True)

            logger.debug(f"服务器 {base_url} 完成 {len(texts)} 个文本，耗时 {response_time:.2f}s")
            return result

        except Exception as e:
            # 记录失败
            response_time = time.time() - start_time
            self._update_stats(base_url, response_time, success=False)
            logger.error(f"服务器 {base_url} 处理失败: {e}")
            raise

        finally:
            # 标记为空闲
            self._mark_server_busy(embedder, False)

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
        logger.info(f"使用 {len(self.embedders)} 个服务器，最大并行度: {self.max_workers}")

        batch_size = batch_size or 20

        # 分批
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
        total_batches = len(batches)

        print(f"\n🔄 开始生成嵌入向量 (实时负载均衡 - 谁空闲谁干活)")
        print(f"   总共 {total_batches} 个批次，每批 {batch_size} 个文本")
        self.print_server_stats()

        all_embeddings = []

        # 使用线程池
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            futures = [
                executor.submit(self.process_single_batch, batch, model)
                for batch in batches
            ]

            # 等待完成
            with tqdm(total=total_batches, desc="处理批次") as pbar:
                for future in as_completed(futures):
                    try:
                        embeddings = future.result()
                        all_embeddings.extend(embeddings)
                        pbar.update(1)

                        # 每完成3个批次显示一次状态
                        if len(all_embeddings) // batch_size % 10 == 0:
                            print(f"\n   [进度: {len(all_embeddings) // batch_size}/{total_batches}]")
                            self.print_server_stats()

                    except Exception as e:
                        logger.error(f"批次处理失败: {e}")
                        pbar.update(1)

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
        self.parallel_generator: Optional[RealTimeLoadBalancer] = None

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


def _run_pipeline_core(
    rag: "VASPRAGAdvanced",
    documents: List[Document],
    test_queries: List[str],
    pipeline_name: str = "完整流程",
    skip_server_check: bool = False
) -> None:
    """
    RAG 流程的核心执行逻辑（内部函数）

    Args:
        rag: VASPRAGAdvanced 实例
        documents: 文档列表
        test_queries: 测试查询列表
        pipeline_name: 流程名称（用于显示）
        skip_server_check: 是否跳过服务器检查（用于演示模式）
    """
    try:
        # 步骤1: 服务器配置
        print("\n" + "=" * 70)
        print("步骤 1: 服务器配置")
        print("=" * 70)
        if not skip_server_check:
            if not rag.setup_servers():
                if pipeline_name == "演示流程":
                    print("❌ 服务器配置失败，但继续执行后续步骤...")
                else:
                    logger.error("服务器配置失败，流程终止")
                    return
        else:
            print("⏭️  跳过服务器检查（演示模式）")

        # 步骤2: 数据加载
        print("\n" + "=" * 70)
        print("步骤 2: 数据加载")
        print("=" * 70)
        print(f"✅ 已加载 {len(documents)} 个文档")

        # 步骤3: 文档分块
        print("\n" + "=" * 70)
        print("步骤 3: 文档分块")
        print("=" * 70)
        split_docs = rag.split_documents(documents)

        # 步骤4: 向量存储构建
        print("\n" + "=" * 70)
        print("步骤 4: 向量存储构建")
        print("=" * 70)
        rag.build_vectorstore(split_docs)

        # 步骤5: 检索测试
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

        print(f"\n✅ {pipeline_name}执行完成！")

    except Exception as e:
        logger.error(f"流程执行出错: {e}")
        import traceback
        traceback.print_exc()


def run_pipeline():
    """运行完整的 RAG 流程（使用真实数据）"""
    print("=" * 70)
    print("🚀 VASP RAG 完整流程")
    print("=" * 70)

    # 配置
    config = RAGConfig(
        max_workers=3,
        chunk_size=1000,
        chunk_overlap=200,
        persist_dir="./chroma_db",
        batch_size=100,
        chat_model="qwen3:4b-instruct-2507-q4_K_M",
        force_rebuild=False
    )

    # 测试查询
    test_queries = RAGConfig._get_env_list('VASP_TEST_QUERIES', [
        "什么是 RPA 计算？如何在 VASP 中设置 RPA 计算？",
        "ALGO 参数有哪些选项？分别代表什么含义？",
        "如何设置 INCAR 文件中的混合泛函参数？"
    ])

    # 数据文件
    data_file = os.getenv('VASP_DATA_FILE', 'vasp_wiki_all_data_readable.json')

    print(f"\n配置: {config}")
    print(f"数据文件: {data_file}")
    print(f"测试查询数: {len(test_queries)}")
    print("\n执行步骤:")
    print("  1. 服务器检测与配置")
    print("  2. 数据加载与预处理")
    print("  3. 文档分块")
    print("  4. 并行嵌入生成与向量存储构建")
    print("  5. 相似性检索测试")
    print("  6. RAG 问答测试")
    print("\n" + "=" * 70)
    print("开始执行...\n")

    # 步骤1: 服务器配置
    rag = VASPRAGAdvanced(config)
    print("\n" + "=" * 70)
    print("步骤 1: 服务器配置")
    print("=" * 70)
    if not rag.setup_servers():
        print("❌ 服务器配置失败")
        return

    # 步骤2: 数据加载
    print("\n" + "=" * 70)
    print("步骤 2: 数据加载")
    print("=" * 70)

    try:
        documents = rag.load_data(data_file)
    except FileNotFoundError:
        print(f"❌ 数据文件 {data_file} 不存在，请检查路径")
        return

    # 步骤3-6: 使用核心流程
    _run_pipeline_core(rag, documents, test_queries, "完整流程", skip_server_check=False)

    print(f"\n📁 数据已保存到: {config.persist_dir}")
    print("\n✅ 完整流程执行完成！")

if __name__ == "__main__":
    # 运行完整 RAG 流程
    run_pipeline()
