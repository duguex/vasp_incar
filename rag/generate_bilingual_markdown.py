#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
将Markdown格式的科研论文分块、翻译, 然后生成上下对照的Markdown文件
上方为原文，下方为译文
支持断点续行和多个Ollama服务器
"""

import os
import sys
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from md_chunker import process_markdown_file
from tqdm import tqdm
from langchain_ollama import ChatOllama
import re

translate_system_prompt = (
    "你是一位严谨的专业学术翻译专家,精通物理、计算机科学领域的中英双语翻译.你的任务是将我提供的科研论文Markdown章节,翻译为流畅、准确、符合中文科研写作习惯的文本.\n\n"
    "核心要求:\n"
    "术语准确统一: 确保专业术语翻译准确且在全文范围内保持一致. 对于没有通用译法的术语,可在首次出现时在括号内保留英文原文.\n"
    "学术风格: 译文语言必须正式、严谨,符合学术论文的写作规范.\n"
    "输出要求: 仅返回译文, 不要输出与译文无关的内容."
)

translate_human_prompt = (
    "非文本元素处理:\n"
    "图片: 保留原始的Markdown图片链接和标签,不翻译图片内容,也不描述图片.仅翻译图片说明文字(caption).\n"
    "公式: 保留所有公式代码块 $$ 或行内公式 $ 的原始内容不变, 不要翻译或修改公式中的任何符号.\n"
    "表格: 翻译表格内的文字内容,但保留表格的Markdown结构. 在表格之前加额外的换行符.\n"
    "代码块: 保留代码块及其语言标识符不变,不翻译代码中的注释、变量名和任何内容.\n"
    "URL链接: 保留所有链接地址不变,只翻译其显示文本.\n\n原文:\n{text}\n\n译文:"
)

# 配置多个Ollama服务器
OLLAMA_SERVERS = [
    {"base_url": "http://192.168.1.130:11434", "enabled": True},
    {"base_url": "http://192.168.1.127:11434", "enabled": True},
    # 可以添加更多服务器
    # {"base_url": "http://192.168.1.128:11434", "enabled": True},
]

# 全局配置
MODEL_NAME = "qwen3:30b-a3b-instruct-2507-q4_K_M"
MAX_WORKERS = len([s for s in OLLAMA_SERVERS if s["enabled"]])  # 根据启用的服务器数量设置线程数
PROGRESS_FILE = "translation_progress.json"  # 进度保存文件

class OllamaClientManager:
    """管理多个Ollama客户端"""
    
    def __init__(self, servers, model_name, num_ctx=40000, temperature=0.3):
        self.servers = servers
        self.model_name = model_name
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.clients = []
        self.lock = threading.Lock()
        self.current_index = 0
        
        # 初始化客户端
        for server in servers:
            if server["enabled"]:
                try:
                    client = ChatOllama(
                        model=model_name,
                        validate_model_on_init=True,
                        base_url=server["base_url"],
                        num_ctx=num_ctx,
                        temperature=temperature
                    )
                    self.clients.append(client)
                    print(f"成功连接到服务器: {server['base_url']}")
                except Exception as e:
                    print(f"连接服务器 {server['base_url']} 失败: {e}")
    
    def get_client(self):
        """轮询获取客户端"""
        with self.lock:
            if not self.clients:
                raise Exception("没有可用的Ollama客户端")
            
            client = self.clients[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.clients)
            return client

# 创建客户端管理器
client_manager = OllamaClientManager(OLLAMA_SERVERS, MODEL_NAME)

def translate(text):
    client = client_manager.get_client()
    translate_prompt = [
        ("system", translate_system_prompt),
        ("human", translate_human_prompt.format(text=text))
    ]
    
    llm_result = client.invoke(translate_prompt)
    context = llm_result.content
    return context

def load_progress(progress_file):
    """加载进度文件"""
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载进度文件失败: {e}")
    return {}

def save_progress(progress_data, progress_file):
    """保存进度文件"""
    try:
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存进度文件失败: {e}")

def translate_chunk(chunk_info):
    """翻译单个分块"""
    chunk_id, chunk_data = chunk_info
    try:
        original_content = chunk_data['content']
        translated_content = translate(original_content)
        return {
            'chunk_id': chunk_id,
            'original': original_content,
            'translated': translated_content,
            'metadata': chunk_data['metadata'],
            'status': 'completed'
        }
    except Exception as e:
        return {
            'chunk_id': chunk_id,
            'original': chunk_data['content'],
            'translated': f"翻译失败: {e}",
            'metadata': chunk_data['metadata'],
            'status': 'failed'
        }

def generate_markdown_content(translated_chunks):
    """生成Markdown内容"""
    markdown_content = ""
    
    for chunk in translated_chunks:
        # 添加分块标题
        metadata_str = "; ".join([f"{k}: {v}" for k, v in chunk['metadata'].items()])
        if not metadata_str:
            metadata_str = f"Chunk {chunk['chunk_id']}"
            
        markdown_content += f"## {metadata_str}\n\n"
        
        # 添加原文
        markdown_content += "### 原文 (English)\n\n"
        markdown_content += chunk["original"].strip() + "\n\n"
        
        # 添加译文
        markdown_content += "### 译文 (Chinese)\n\n"
        markdown_content += chunk["translated"].strip() + "\n\n"
        
        # 添加分隔线
        markdown_content += "---\n\n"
    
    return markdown_content

def batch_translate_chunks(source_path, output_dir=None, resume=True):
    """
    批量处理多个Markdown文件，分块、翻译并生成对照文档
    
    Args:
        source_path (str): 源文件目录路径
        output_dir (str): 输出目录路径，默认为None，表示输出到原目录
        resume (bool): 是否断点续行，默认为True
    """
    # 如果指定了输出目录，则确保该目录存在
    if output_dir is not None:
        os.makedirs(output_dir, exist_ok=True)
    
    # 加载进度
    progress_data = load_progress(PROGRESS_FILE) if resume else {}
    print(f"加载进度: {len(progress_data)} 个分块已保存")
    
    # 查找所有Markdown文件
    md_files = []
    for root, dirs, files in os.walk(source_path):
        for file in files:
            if file.endswith(".md") and not file.endswith("_bilingual.md"):
                md_files.append(os.path.join(root, file))
    
    if not md_files:
        print(f"在目录 {source_path} 中未找到Markdown文件")
        return
    
    print(f"找到 {len(md_files)} 个Markdown文件")
    print(f"使用 {len(client_manager.clients)} 个Ollama服务器，最大并发数: {MAX_WORKERS}")
    
    # 收集所有需要翻译的分块
    all_chunks_to_translate = []
    file_chunks_map = {}
    
    for md_path in md_files:
        try:
            # 检查是否已经完成翻译
            output_filename = os.path.splitext(os.path.basename(md_path))[0] + "_bilingual.md"
            if output_dir is not None:
                output_path = os.path.join(output_dir, output_filename)
            else:
                output_path = os.path.join(os.path.dirname(md_path), output_filename)
            
            # 如果最终文件已存在且不续行，则跳过
            if os.path.exists(output_path) and not resume:
                print(f"跳过已存在的文件: {output_filename}")
                continue
            
            with open(md_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            # 处理Markdown文件分块
            chunks = process_markdown_file(
                markdown_content
            )
            
            file_chunks_map[md_path] = []
            
            for i, chunk in enumerate(chunks):
                chunk_id = f"{os.path.basename(md_path)}_chunk_{i}"
                
                # 检查是否已经翻译过
                if resume and chunk_id in progress_data:
                    saved_chunk = progress_data[chunk_id]
                    if saved_chunk.get('status') == 'completed':
                        # 已经完成，使用保存的结果
                        file_chunks_map[md_path].append(saved_chunk)
                        print(f"跳过已完成的分块: {chunk_id}")
                        continue
                
                # 需要翻译的分块
                all_chunks_to_translate.append((chunk_id, chunk))
                file_chunks_map[md_path].append({
                    'chunk_id': chunk_id,
                    'status': 'pending'
                })
            
            print(f"文件 {os.path.basename(md_path)}: {len(chunks)} 个分块，{len([c for c in file_chunks_map[md_path] if c.get('status') == 'pending'])} 个待翻译")
            
        except Exception as e:
            print(f"处理文件 {md_path} 时出错: {e}")
            continue
    
    if not all_chunks_to_translate:
        print("没有需要翻译的分块，所有分块已完成或已保存")
        # 直接生成最终文件
        generate_final_files(file_chunks_map, progress_data, output_dir)
        return
    
    print(f"总共 {len(all_chunks_to_translate)} 个分块需要翻译")
    
    # 使用线程池并发翻译
    completed_chunks = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有翻译任务
        future_to_chunk = {
            executor.submit(translate_chunk, chunk_info): chunk_info 
            for chunk_info in all_chunks_to_translate
        }
        
        # 创建进度条
        pbar = tqdm(total=len(all_chunks_to_translate), desc="翻译进度", unit="chunk")
        
        # 处理完成的任务
        for future in as_completed(future_to_chunk):
            chunk_info = future_to_chunk[future]
            chunk_id, _ = chunk_info
            
            try:
                result = future.result()
                completed_chunks.append(result)
                
                # 更新进度文件
                progress_data[chunk_id] = result
                save_progress(progress_data, PROGRESS_FILE)
                
                # 更新文件映射中的状态
                for md_path, chunks in file_chunks_map.items():
                    for chunk in chunks:
                        if chunk.get('chunk_id') == chunk_id:
                            chunk.update(result)
                            break
                
                pbar.update(1)
                pbar.set_postfix_str(f"已完成: {len(completed_chunks)}/{len(all_chunks_to_translate)}")
                
            except Exception as e:
                print(f"处理分块 {chunk_id} 时出错: {e}")
                # 保存失败状态
                failed_result = {
                    'chunk_id': chunk_id,
                    'original': chunk_info[1]['content'],
                    'translated': f"翻译失败: {e}",
                    'metadata': chunk_info[1]['metadata'],
                    'status': 'failed'
                }
                progress_data[chunk_id] = failed_result
                save_progress(progress_data, PROGRESS_FILE)
        
        pbar.close()
    
    # 生成最终文档
    generate_final_files(file_chunks_map, progress_data, output_dir)
    
    print("所有文件翻译完成！")

def generate_final_files(file_chunks_map, progress_data, output_dir):
    """生成最终的双语文件"""
    for md_path, chunks_info in file_chunks_map.items():
        # 收集该文件的所有分块（包括之前完成的和新翻译的）
        file_translated_chunks = []
        
        for chunk_info in chunks_info:
            chunk_id = chunk_info['chunk_id']
            if chunk_info.get('status') == 'completed' and 'translated' in chunk_info:
                # 已经是翻译完成的状态
                file_translated_chunks.append(chunk_info)
            elif chunk_id in progress_data and progress_data[chunk_id].get('status') == 'completed':
                # 从进度数据中查找
                file_translated_chunks.append(progress_data[chunk_id])
        
        # 按原始顺序排序
        file_translated_chunks.sort(key=lambda x: int(re.search(r'chunk_(\d+)', x['chunk_id']).group(1)))
        
        # 生成最终文档
        if file_translated_chunks:
            file_translated_content = generate_markdown_content(file_translated_chunks)
            output_filename = os.path.splitext(os.path.basename(md_path))[0] + "_bilingual.md"
            
            if output_dir is not None:
                output_path = os.path.join(output_dir, output_filename)
            else:
                output_path = os.path.join(os.path.dirname(md_path), output_filename)
            
            # 写入文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(file_translated_content)
            
            print(f"已生成: {output_filename} ({len(file_translated_chunks)} 个分块)")

if __name__ == "__main__":
    # 使用paper_1120目录进行测试
    source_path = "yitiaolong"
    # 默认输出到原目录
    output_dir = None
    
    batch_translate_chunks(source_path, output_dir, resume=True)
