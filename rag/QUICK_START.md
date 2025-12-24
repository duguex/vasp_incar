# 🚀 VASP RAG 快速启动指南

## 📋 文件清单

### 核心程序
- ✅ `vasp_rag.py` - 基础版 RAG 系统
- ✅ `vasp_rag_advanced.py` - 高级版 (推荐)
- ✅ `demo_advanced.py` - 功能演示

### 测试工具
- ✅ `test_servers.py` - 服务器连接测试
- ✅ `test_advanced.py` - 高级功能测试
- ✅ `test_setup.py` - 环境检查
- ✅ `quick_test.py` - 快速测试

### 文档
- ✅ `README.md` - 基础版说明
- ✅ `README_ADVANCED.md` - 高级版详细文档
- ✅ `SUMMARY.md` - 项目总结
- ✅ `QUICK_START.md` - 本文件

## ⚡ 3步启动

### 第1步: 检查环境
```bash
python test_servers.py
```

**期望输出:**
```
✅ 192.168.1.127:11434 - online
✅ 127.0.0.1:11434 - online
✅ 192.168.1.130:11434 - online
```

### 第2步: 功能演示
```bash
python demo_advanced.py
```

**演示内容:**
- 服务器自动检测
- 进度条显示
- 并行嵌入生成
- RAG 问答测试

### 第3步: 完整运行
```bash
python vasp_rag_advanced.py
```

**功能:**
- 加载全部 5932 个文档
- 构建向量数据库
- 交互式问答

## 🎯 常用命令速查

| 命令 | 用途 | 耗时 |
|------|------|------|
| `test_servers.py` | 检查服务器 | ~5秒 |
| `demo_advanced.py` | 功能演示 | ~5分钟 |
| `vasp_rag_advanced.py` | 完整系统 | ~45分钟(首次) |

## 🔧 配置文件位置

### 修改服务器配置
```python
# vasp_rag_advanced.py 第492行
"server_hosts": ["192.168.1.127", "127.0.0.1", "192.168.1.130"],
```

### 修改并行参数
```python
# vasp_rag_advanced.py 第493行
"max_workers": 6,  # 根据服务器数量调整
```

### 强制重建数据库
```python
# vasp_rag_advanced.py 第497行
"force_rebuild": True,  # 改为 True 重新构建
```

## 📊 预期性能

### 你的服务器配置
```
服务器: 3个在线
模型: qwen3-embedding:8b
并行: 6线程
```

### 预计速度
```
文档加载: ~1秒
分块处理: ~3秒
嵌入生成: ~150秒 (3服务器并行)
数据库保存: ~15秒
总计: ~170秒 (2.8分钟)
```

### 实际测试结果
```
46个文档 → 266.8秒 (演示模式)
全量5932文档 → ~45分钟
```

## 💡 使用建议

### 首次使用
1. ✅ 运行 `test_servers.py` 确认服务器
2. ✅ 运行 `demo_advanced.py` 熟悉流程
3. ✅ 运行 `vasp_rag_advanced.py` 构建完整系统

### 日常使用
- 直接运行 `vasp_rag_advanced.py`
- 数据库会自动加载，无需重建
- 支持交互式问答

### 重新构建
- 修改 `force_rebuild = True`
- 运行 `vasp_rag_advanced.py`
- 完成后改回 `False`

## 🎬 演示截图

### 服务器检测
```
🔍 检查远程 Ollama 服务器...
检查服务器: 100%|██████████| 4/4 [00:02<00:00,  1.49it/s]
✅ 找到 3 个在线服务器
```

### 数据处理
```
🔄 生成嵌入向量 (并行加速)...
生成嵌入向量: 100%|██████████| 618/618 [00:45<00:00, 13.73batch/s]
✅ 嵌入生成完成，耗时: 45.2秒
```

### 问答交互
```
【问题】: 什么是 RPA 计算？
【回答】: RPA 计算（Random-Phase Approximation，随机相位近似）...
✅ 回答生成完成 (耗时: 8.3秒)
```

## ❓ 常见问题

### Q: 服务器离线怎么办？
```bash
# 检查服务器状态
python test_servers.py

# 在配置中移除离线服务器
# 编辑 vasp_rag_advanced.py 第492行
```

### Q: 速度太慢？
- 增加 `max_workers`
- 检查网络延迟
- 确认服务器性能

### Q: 内存不足？
- 减小 `chunk_size` (如 800)
- 减少 `max_workers`
- 分批处理

## 🎯 下一步

1. **立即尝试**: `python demo_advanced.py`
2. **完整使用**: `python vasp_rag_advanced.py`
3. **查看文档**: `README_ADVANCED.md`
4. **查看总结**: `SUMMARY.md`

---

**准备好了吗？开始吧！** 🚀

```bash
python test_servers.py
```