#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangChain + Ollama 多节点负载均衡调用
1. Embeddings 负载均衡
2. Chat 模型负载均衡
"""

import threading
import time
from typing import List, Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_ollama import OllamaEmbeddings, ChatOllama


class LoadBalancer:
    """通用负载均衡器 - 谁空闲谁干活"""

    def __init__(self, clients: List[Dict[str, Any]]):
        """
        clients = [
            {'client': OllamaEmbeddings(...), 'base_url': 'http://host:11434'},
            {'client': ChatOllama(...), 'base_url': 'http://host:11434'},
        ]
        """
        self.clients = []
        for client in clients:
            self.clients.append({
                'client': client['client'],
                'base_url': client['base_url'],
                'lock': threading.Lock(),
                'busy': False,
            })
            print(f"✅ 客户端: {client['base_url']}")

    def _find_available(self) -> Optional[Dict]:
        """查找空闲服务器"""
        for c in self.clients:
            if not c['busy']:
                return c
        return None

    def _mark_busy(self, client: Dict, busy: bool):
        """标记状态"""
        with client['lock']:
            client['busy'] = busy

    def _process_single(self, task: Any, func: Callable, client: Dict) -> Any:
        """处理单个任务"""
        self._mark_busy(client, True)
        try:
            result = func(client['client'], task)
            print(f"   {client['base_url']} 完成")
            return result
        finally:
            self._mark_busy(client, False)

    def execute_parallel(self, tasks: List[Any], func: Callable) -> List[Any]:
        """
        并行执行任务

        Args:
            tasks: 任务列表
            func: 执行函数，格式: func(client, task) -> result
        """
        if not tasks:
            return []

        print(f"\n🔄 开始: {len(tasks)} 个任务, {len(self.clients)} 服务器")

        def worker(task):
            # 等待空闲服务器
            while True:
                client = self._find_available()
                if client:
                    break
                time.sleep(0.3)
            return self._process_single(task, func, client)

        with ThreadPoolExecutor(max_workers=len(self.clients)) as executor:
            futures = [executor.submit(worker, task) for task in tasks]
            results = [future.result() for future in as_completed(futures)]

        print(f"✅ 完成: {len(results)} 个结果")
        return results


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("LangChain + Ollama 多节点负载均衡")
    print("=" * 60)

    # 服务器配置
    servers = [
        {"host": "localhost", "port": 11434},
        {"host": "192.168.1.130", "port": 11434},
        {"host": "192.168.1.127", "port": 11434},
    ]

    # 1. Embeddings 负载均衡
    print("\n【1. Embeddings 负载均衡】")

    # 创建 Embeddings 客户端列表（所有服务器）
    embed_clients = [
        {
            'client': OllamaEmbeddings(
                model='nomic-embed-text-v2-moe',
                base_url=f"http://{s['host']}:{s['port']}"
            ),
            'base_url': f"http://{s['host']}:{s['port']}"
        }
        for s in servers
    ]

    embed_balancer = LoadBalancer(embed_clients)

    # 定义 Embeddings 执行函数
    def embed_func(client, texts):
        return client.embed_documents(texts)

    # 执行
    texts = ["文本"] * 100
    embeddings = embed_balancer.execute_parallel(texts, embed_func)
    print(f"生成 {len(embeddings)} 个向量，维度: {len(embeddings[0])}")

    # 2. Chat 模型负载均衡（排除 localhost）
    print("\n【2. Chat 模型负载均衡】")

    # 只使用远程服务器（排除 localhost）
    chat_servers = [s for s in servers if s['host'] != 'localhost']

    chat_clients = [
        {
            'client': ChatOllama(
                model='qwen3:30b-a3b-instruct-2507-q4_K_M',
                base_url=f"http://{s['host']}:{s['port']}",
                temperature=0.1
            ),
            'base_url': f"http://{s['host']}:{s['port']}"
        }
        for s in chat_servers
    ]

    chat_balancer = LoadBalancer(chat_clients)

    # 定义 Chat 执行函数
    def chat_func(client, prompt):
        result = client.invoke(prompt)
        return result.content if hasattr(result, 'content') else str(result)

    # 执行
    prompts = [
        "你好，请介绍一下自己",
        "什么是机器学习？",
        "解释量子计算的基本原理",
        "Python 的优势是什么？"
    ] * 3

    answers = chat_balancer.execute_parallel(prompts, chat_func)

    # 显示结果
    print("\n" + "=" * 60)
    print("结果汇总")
    print("=" * 60)
    for i, (p, a) in enumerate(zip(prompts, answers), 1):
        print(f"\n【问题 {i}】{p}")
        print(f"【回答 {i}】\n{a}")

    print("\n✅ 完成")
