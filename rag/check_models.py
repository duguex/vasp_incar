"""
检查本地 Ollama 模型并提供选择
"""

import requests
import json


def get_local_models():
    """获取本地已安装的模型列表"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return [model['name'].split(':')[0] for model in models]  # 只返回模型名，不带标签
    except:
        pass
    return []


def check_ollama_running():
    """检查 Ollama 服务是否运行"""
    try:
        response = requests.get("http://localhost:11434/api/version", timeout=5)
        return response.status_code == 200
    except:
        return False


def main():
    print("=" * 60)
    print("VASP RAG - 本地模型检查")
    print("=" * 60)

    if not check_ollama_running():
        print("❌ Ollama 服务未运行")
        print("请先启动 Ollama: ollama serve")
        return

    models = get_local_models()

    if not models:
        print("❌ 未找到本地模型")
        print("\n建议的操作:")
        print("1. 使用已有模型: ollama list")
        print("2. 如果没有模型，可以使用以下轻量级模型:")
        print("   - nomic-embed-text (专门用于嵌入)")
        print("   - qwen2.5:7b (通用对话)")
        return

    print(f"📋 找到 {len(models)} 个本地模型:")
    for i, model in enumerate(models, 1):
        print(f"   {i}. {model}")

    print("\n💡 建议:")
    print("- 嵌入模型: 选择支持嵌入的模型 (如 qwen2.5, nomic-embed-text 等)")
    print("- 对话模型: 选择对话能力强的模型 (如 qwen2.5, llama2 等)")
    print("\n当前推荐配置:")
    print("embedding_model = 'qwen2.5:7b'  # 如果本地有")
    print("embedding_model = 'nomic-embed-text'  # 如果只有这个")


if __name__ == "__main__":
    main()