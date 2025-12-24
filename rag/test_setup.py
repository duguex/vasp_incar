"""
快速测试环境和本地模型
"""

import requests
import json


def test_ollama_connection():
    """测试 Ollama 连接"""
    print("🔍 测试 Ollama 连接...")
    try:
        response = requests.get("http://localhost:11434/api/version", timeout=5)
        if response.status_code == 200:
            print(f"✅ Ollama 运行正常 (版本: {response.json().get('version', '未知')})")
            return True
        else:
            print(f"❌ Ollama 返回错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到 Ollama: {e}")
        print("   请确保: 1. Ollama 已安装 2. 运行了 'ollama serve'")
        return False


def list_models():
    """列出本地模型"""
    print("\n📋 本地模型列表:")
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            if models:
                for i, model in enumerate(models, 1):
                    name = model.get('name', '未知')
                    size = model.get('size', 0) / (1024**3)
                    print(f"   {i}. {name} ({size:.2f} GB)")
                return [m['name'] for m in models]
            else:
                print("   未找到模型")
                return []
    except Exception as e:
        print(f"   获取模型列表失败: {e}")
        return []


def test_embedding_capability(model_name):
    """测试模型是否支持嵌入"""
    print(f"\n🧪 测试模型 '{model_name}' 的嵌入能力...")
    try:
        from langchain_ollama import OllamaEmbeddings

        embeddings = OllamaEmbeddings(
            model=model_name,
            base_url="http://localhost:11434"
        )

        # 简单测试
        result = embeddings.embed_query("test")
        print(f"✅ 嵌入测试成功，维度: {len(result)}")
        return True
    except Exception as e:
        print(f"❌ 嵌入测试失败: {e}")
        return False


def main():
    print("=" * 60)
    print("VASP RAG - 环境测试")
    print("=" * 60)

    # 1. 测试 Ollama 连接
    if not test_ollama_connection():
        return

    # 2. 列出模型
    models = list_models()
    if not models:
        print("\n💡 建议:")
        print("   安装一个嵌入模型:")
        print("   - ollama pull nomic-embed-text  (推荐，轻量级)")
        print("   - ollama pull qwen2.5:7b        (如果已有，可直接使用)")
        return

    # 3. 推荐使用
    print("\n💡 使用建议:")

    # 查找推荐的嵌入模型
    preferred = ['nomic-embed-text', 'qwen2.5', 'bge-m3', 'mxbai-embed-large']
    found = []

    for pref in preferred:
        for model in models:
            if pref in model.lower():
                found.append(model)

    if found:
        print("   推荐的嵌入模型:")
        for model in found:
            print(f"   - {model}")
            test_embedding_capability(model)
    else:
        print("   未找到专门的嵌入模型，尝试使用已有模型:")
        for model in models[:2]:  # 测试前2个
            print(f"   - {model}")
            test_embedding_capability(model)

    print("\n" + "=" * 60)
    print("下一步:")
    print("1. 运行: python vasp_rag.py")
    print("2. 系统会自动检测并使用本地模型")
    print("=" * 60)


if __name__ == "__main__":
    main()