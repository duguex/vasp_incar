#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终版VASP Wiki数据可读性优化
正确处理转义字符和格式化
"""

import json
import re


def process_content(content):
    """处理单个内容"""
    # 1. 将 \\n 替换为换行符
    content = content.replace('\\n', '\n')

    # 2. 将 \\t 替换为制表符
    content = content.replace('\\t', '\t')

    # 3. 将 \\" 替换为 "
    content = content.replace('\\"', '"')

    # 4. 移除 Retrieved from 信息
    content = re.sub(r'Retrieved from ".*?"', '', content, flags=re.DOTALL)

    # 5. 格式化警告和提示
    content = re.sub(r'\nWarning:', '\n⚠️ **Warning:**', content)
    content = re.sub(r'\nTip:', '\n💡 **Tip:**', content)
    content = re.sub(r'\nImportant:', '\n❗ **Important:**', content)
    content = re.sub(r'\nNote:', '\n📝 **Note:**', content)
    content = re.sub(r'\nCaveat:', '\n🚧 **Caveat:**', content)
    content = re.sub(r'\nMind:', '\n🧠 **Mind:**', content)

    # 6. 格式化步骤
    content = re.sub(r'Step (\d+):', r'\n**步骤 \1:**', content)

    # 7. 格式化数学公式
    content = re.sub(r'\[math\](.*?)\[/math\]', r'$$\1$$', content, flags=re.DOTALL)

    # 8. 格式化代码块
    lines = content.split('\n')
    formatted_lines = []
    in_code = False

    for line in lines:
        stripped = line.strip()

        # 判断是否是配置/代码行
        is_config = (
            ('=' in line and not line.startswith('http')) or
            stripped.startswith('!') or
            any(stripped.startswith(tag) for tag in ['ALGO', 'NBANDS', 'NOMEGA', 'EDIFF', 'ISMEAR', 'SIGMA', 'LHFCALC', 'LOPTICS', 'ENCUT', 'PREC', 'LMAX', 'NMAX'])
        )

        if is_config and not in_code:
            formatted_lines.append('```')
            in_code = True
        elif not is_config and in_code:
            formatted_lines.append('```')
            in_code = False

        formatted_lines.append(line)

    if in_code:
        formatted_lines.append('```')

    content = '\n'.join(formatted_lines)

    # 9. 清理多余空行
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    content = re.sub(r'\n```\n```', '\n```\n', content)

    return content.strip()


def main():
    """主函数"""
    print("=== VASP Wiki 数据可读性优化 ===\n")

    # 读取数据
    print("读取原始数据...")
    with open('vasp_wiki_all_data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"共 {len(data)} 个条目\n")

    # 测试几个样本
    print("=== 样本测试 ===")
    test_indices = [0, 2, 10]

    for idx in test_indices:
        item = data[idx]
        original = item['content']
        processed = process_content(original)

        print(f"\n【{item['title']}】")
        print(f"长度: {len(original)} → {len(processed)}")
        print(f"\n处理前:")
        print(repr(original[:150]))
        print(f"\n处理后:")
        print(repr(processed[:150]))
        print(f"\n显示:")
        print(processed[:250] + "..." if len(processed) > 250 else processed)
        print("-" * 60)

    # 处理全部数据
    print("\n\n=== 处理全部数据 ===")
    processed_data = []

    for i, item in enumerate(data):
        processed_data.append({
            'title': item['title'],
            'url': item['url'],
            'content': process_content(item['content'])
        })

        if (i + 1) % 100 == 0:
            print(f"已处理 {i + 1}/{len(data)}")

    # 保存结果
    output_file = "vasp_wiki_all_data_readable.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成！结果保存到: {output_file}")

    # 统计
    orig_chars = sum(len(item['content']) for item in data)
    new_chars = sum(len(item['content']) for item in processed_data)

    print(f"\n📊 统计信息:")
    print(f"原始总字符: {orig_chars:,}")
    print(f"优化后总字符: {new_chars:,}")
    print(f"压缩率: {((orig_chars - new_chars) / orig_chars * 100):.1f}%")

    # 显示一些改进示例
    print(f"\n=== 改进效果示例 ===")
    for idx in [2]:  # 选一个长内容的
        if idx < len(data):
            orig = data[idx]['content']
            proc = processed_data[idx]['content']

            print(f"\n【{data[idx]['title']}】")
            print(f"\n原始内容前300字符:")
            print(orig[:300])
            print(f"\n优化后内容前300字符:")
            print(proc[:300])


if __name__ == "__main__":
    main()