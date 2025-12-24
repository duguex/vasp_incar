# VASP RAG 系统

基于 LangChain 构建的 VASP (Vienna Ab initio Simulation Package) 文档检索增强生成系统。

## 功能特性

- 📚 **智能文档检索**: 基于语义相似度的 VASP 文档检索
- 🤖 **本地模型支持**: 优先使用本地 Ollama 模型，无需 API
- 🔍 **分块处理**: 智能文本分块，优化检索效果
- 💾 **向量存储**: 使用 ChromaDB 持久化存储
- 🎯 **中文支持**: 完整的中文问答支持

## 环境要求

- Python 3.8+
- Ollama (本地运行)
- 已安装的 Ollama 模型

## 安装依赖

```bash
# 已安装的依赖
pip install langchain langchain-community langchain-ollama chromadb
```

## 快速开始

### 1. 检查本地模型

```bash
python test_setup.py
```

这会检查:
- Ollama 服务是否运行
- 本地有哪些模型可用
- 模型是否支持嵌入功能

### 2. 运行 RAG 系统

```bash
python vasp_rag.py
```

系统会:
1. 自动检测本地模型
2. 选择合适的嵌入模型
3. 加载并处理 VASP 文档
4. 构建向量索引
5. 提供交互式问答

## 模型选择建议

### 推荐的嵌入模型 (按优先级)

1. **nomic-embed-text** - 轻量级，专门用于嵌入
2. **qwen2.5:7b** - 通用能力强，支持中文
3. **bge-m3** - 多语言嵌入
4. **mxbai-embed-large** - 高质量嵌入

### 如果本地没有模型

```bash
# 安装轻量级嵌入模型
ollama pull nomic-embed-text

# 或者安装通用模型 (同时用于嵌入和对话)
ollama pull qwen2.5:7b
```

## 文件说明

- `vasp_rag.py` - 主程序，完整的 RAG 系统
- `test_setup.py` - 环境测试脚本
- `check_models.py` - 模型检查工具
- `vasp_wiki_all_data.json` - VASP 文档数据源

## 使用示例

### 自动模式
```
🔍 检查本地模型...
📋 找到 2 个本地模型:
   1. qwen2.5:7b
   2. nomic-embed-text

✅ 自动选择嵌入模型: nomic-embed-text
```

### 交互式问答
```
请输入你的问题: 什么是 RPA 计算？
```

### 检索结果展示
```
【问题】: 什么是 RPA 计算？如何在 VASP 中设置 RPA 计算？

检索到的相关文档:
--- 结果 1 ---
标题: ACFDT/RPA calculations
内容预览: The adiabatic-connection-fluctuation-dissipation theorem (ACFDT) can be used to derive the random-phase approximation (RPA)...

【回答】:
RPA (随机相位近似) 计算是...
```

## 配置选项

在 `vasp_rag.py` 中可以调整:

```python
config = {
    "json_file": "vasp_wiki_all_data.json",  # 数据文件
    "embedding_model": "auto",               # 自动选择或手动指定
    "persist_dir": "./chroma_db",            # 向量数据库位置
    "chunk_size": 1000,                      # 文本块大小
    "chunk_overlap": 200,                    # 文本块重叠
    "force_rebuild": False                   # 是否强制重建索引
}
```

## 性能优化建议

1. **首次运行**: 会生成向量数据库，可能需要几分钟
2. **后续运行**: 直接加载已有数据库，速度很快
3. **内存使用**: 根据文档大小和模型大小而定
4. **模型选择**: 小模型更快，大模型更准确

## 故障排除

### Ollama 未运行
```bash
# 启动 Ollama
ollama serve
```

### 模型不存在
```bash
# 查看可用模型
ollama list

# 下载模型
ollama pull <model_name>
```

### 内存不足
- 使用更小的模型 (如 nomic-embed-text)
- 减小 chunk_size
- 增加 chunk_overlap

## 扩展功能

可以轻松扩展的功能:
- 添加更多 VASP 文档源
- 支持多轮对话历史
- 集成 VASP 输入文件生成
- 添加计算结果解析

## 许可证

MIT License