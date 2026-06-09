#!/usr/bin/env python3

import json
import argparse
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter
import os
import math

def load_incar_data(json_file: str) -> List[Dict[str, Any]]:
    """加载INCAR数据从JSON文件"""
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {json_file}")
        return []
    except json.JSONDecodeError:
        print(f"错误: {json_file} 不是有效的JSON文件")
        return []

def parse_key_value_pairs(kv_pairs: List[str]) -> List[Tuple[str, Any]]:
    """解析键值对参数"""
    parsed_pairs = []
    
    for pair in kv_pairs:
        if '=' in pair:
            key, value = pair.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            # 尝试转换值的类型
            try:
                # 尝试转换为浮点数
                if '.' in value:
                    value = float(value)
                else:
                    # 尝试转换为整数
                    value = int(value)
            except ValueError:
                # 如果是字符串 'true'/'false'，转换为布尔值
                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                # 否则保持为字符串
            
            parsed_pairs.append((key, value))
        else:
            print(f"警告: 忽略无效的键值对格式 '{pair}'，应使用 key=value 格式")
    
    return parsed_pairs

def find_incar_by_key_value(data: List[Dict[str, Any]], kv_pairs: List[Tuple[str, Any]], 
                           match_all: bool = True) -> List[Dict[str, Any]]:
    """
    根据键值对查找INCAR配置
    
    Args:
        data: INCAR数据列表
        kv_pairs: 键值对列表
        match_all: 是否匹配所有键值对 (True) 或任意一个 (False)
    """
    if not kv_pairs:
        return data  # 如果没有查询条件，返回所有数据
    
    matches = []
    
    for item in data:
        incar = item["incar"]
        match_count = 0
        
        for key, expected_value in kv_pairs:
            if key in incar:
                actual_value = incar[key]
                
                # 特殊处理列表类型的值（如MAGMOM）
                if isinstance(actual_value, list) and isinstance(expected_value, (int, float)):
                    # 如果是数值，检查列表中是否有匹配的数值
                    found = False
                    for sublist in actual_value:
                        if isinstance(sublist, list):
                            if expected_value in sublist:
                                found = True
                                break
                        elif sublist == expected_value:
                            found = True
                            break
                    if found:
                        match_count += 1
                # 常规值比较
                elif actual_value == expected_value:
                    match_count += 1
        
        # 根据匹配模式决定是否包含
        if match_all and match_count == len(kv_pairs):
            matches.append(item)
        elif not match_all and match_count > 0:
            matches.append(item)
    
    return matches

def analyze_parameter_values(matches: List[Dict[str, Any]]) -> Dict[str, Dict]:
    """分析每个参数的值频率，包括参数未出现的情况"""
    param_analysis = {}
    total_configs = len(matches)
    
    # 首先收集所有可能的参数名
    all_params = set()
    for item in matches:
        all_params.update(item["incar"].keys())
    
    # 分析每个参数
    for param in all_params:
        param_analysis[param] = {
            'values': Counter(),
            'total_occurrences': 0,
            'not_present_count': 0
        }
        
        for item in matches:
            incar = item["incar"]
            if param in incar:
                value = incar[param]
                param_analysis[param]['total_occurrences'] += 1
                
                # 处理特殊类型的值
                if isinstance(value, list):
                    # 对于列表，检查是否是嵌套列表（如MAGMOM）
                    if value and isinstance(value[0], list):
                        # 嵌套列表，提取所有数值
                        for sublist in value:
                            for item_val in sublist:
                                if isinstance(item_val, (int, float)):
                                    param_analysis[param]['values'][str(item_val)] += 1
                        # 如果没有数值，添加列表的字符串表示
                        if not any(isinstance(item_val, (int, float)) for sublist in value for item_val in sublist):
                            param_analysis[param]['values'][str(value)] += 1
                    else:
                        # 普通列表，直接添加所有值
                        for v in value:
                            param_analysis[param]['values'][str(v)] += 1
                else:
                    param_analysis[param]['values'][str(value)] += 1
            else:
                param_analysis[param]['not_present_count'] += 1
    
    # 将"没有"作为一个特殊值加入统计
    for param, analysis in param_analysis.items():
        if analysis['not_present_count'] > 0:
            analysis['values']['nan'] = analysis['not_present_count']
    
    return param_analysis

def format_value(value: str) -> str:
    """格式化单个值"""
    # if value == 'nan':
    #     return 'nan'
    
    # # 尝试转换为数值
    # try:
    #     if '.' in value:
    #         return str(float(value))
    #     else:
    #         return str(int(value))
    # except ValueError:
    #     # 如果是布尔值字符串，转换为VASP格式
    #     if value.lower() == 'true':
    #         return '.TRUE.'
    #     elif value.lower() == 'false':
    #         return '.FALSE.'
    #     # 否则保持原样
    return value

def generate_incar_with_frequent_values(param_analysis: Dict[str, Dict], 
                                       query_conditions: List[Tuple[str, Any]] = None,
                                       min_frequency: int = 1,
                                       for_file: bool = False) -> str:
    """生成INCAR文件，每个键使用频率最高的值，其他值用注释显示"""
    normal_lines = []  # 正常参数行
    commented_lines = []  # 注释掉的参数行
    
    # 如果输出到文件，不添加任何抬头注释
    if not for_file:
        header_lines = []
        if query_conditions:
            header_lines.append(f"# 查询条件: {', '.join([f'{k}={v}' for k, v in query_conditions])}")
        header_lines.append(f"# 包含 {len(param_analysis)} 个参数")
        header_lines.append("")
    else:
        header_lines = []
    
    # 计算最大键长度用于对齐
    if param_analysis:
        max_key_length = max(len(key) for key in param_analysis.keys())
    else:
        max_key_length = 0
    
    # 创建一个列表，包含参数名和它们的出现频次（不包括nan的情况）
    param_frequency = []
    for key, analysis in param_analysis.items():
        values = analysis['values']
        
        # 过滤掉频率太低的参数
        if sum(values.values()) < min_frequency:
            continue
            
        # 获取最常用的值
        if values:
            most_common_value, most_common_count = values.most_common(1)[0]
            
            # 计算实际出现次数（不包括nan）
            actual_occurrences = analysis['total_occurrences']
            
            # 如果最常用的值是"nan"，则在注释中显示该参数
            if most_common_value == 'nan':
                # 获取非nan的值（按频率降序排列）
                non_nan_values = []
                for value, count in values.most_common():
                    if value != 'nan' and count >= min_frequency:
                        formatted_value = format_value(value)
                        non_nan_values.append(formatted_value)
                
                # 如果有非nan的值，使用第二常用的值作为主要值
                if non_nan_values:
                    primary_value = non_nan_values[0]
                    other_values = non_nan_values[1:] if len(non_nan_values) > 1 else []
                    
                    # 构建注释行，确保对齐
                    padding = ' ' * (max_key_length - len(key))
                    if other_values:
                        line = f"#{key}{padding} = {primary_value}   # {', '.join(other_values)}"
                    else:
                        line = f"#{key}{padding} = {primary_value}"
                else:
                    # 只有nan值
                    padding = ' ' * (max_key_length - len(key))
                    line = f"#{key}{padding} = nan"
                
                # 对于注释行，使用实际出现次数进行排序
                commented_lines.append((actual_occurrences, key, line))
            else:
                # 正常情况：参数有值
                most_common_value = format_value(most_common_value)
                
                # 获取其他值（按频率降序排列），包括nan
                other_values = []
                for value, count in values.most_common():
                    if value != most_common_value and count >= min_frequency:
                        formatted_value = format_value(value)
                        other_values.append(formatted_value)
                
                # 构建输出行，确保对齐
                padding = ' ' * (max_key_length - len(key))
                if other_values:
                    line = f"{key}{padding} = {most_common_value}   # {', '.join(other_values)}"
                else:
                    line = f"{key}{padding} = {most_common_value}"
                
                normal_lines.append((actual_occurrences, key, line))
    
    # 按实际出现频次降序排序正常行和注释行
    print(f"normal_lines: {normal_lines}")
    normal_lines.sort(key=lambda x: x[0], reverse=True)
    commented_lines.sort(key=lambda x: x[0], reverse=True)
    
    # 组合所有行：首先是正常行，然后是注释行
    all_lines = [line for _, _, line in normal_lines]
    
    # 如果有注释行，添加一个空行分隔
    if commented_lines:
        all_lines.append("")
        all_lines.extend([line for _, _, line in commented_lines])
    
    # 添加文件头
    return "\n".join(header_lines + all_lines) + "\n"

def main():
    parser = argparse.ArgumentParser(
        description="根据键值对查询INCAR配置并生成参考INCAR文件，显示最常用值",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s ALGO=All AEXX=0.25
  %(prog)s -a GGA=Pe LSORBIT=true
  %(prog)s ENCUT=400
  %(prog)s --min-frequency 2  # 只显示出现至少2次的参数
        """
    )
    parser.add_argument("key_values", nargs="*", help="键值对，格式: KEY=VALUE")
    parser.add_argument("-f", "--file", default="incar_data.json", 
                       help="INCAR数据JSON文件 (默认: incar_data.json)")
    parser.add_argument("-o", "--output", default="INCAR_ref",
                       help="输出文件名 (默认: INCAR_ref)")
    parser.add_argument("-a", "--any-match", action="store_true",
                       help="匹配任意一个键值对（默认匹配所有）")
    parser.add_argument("--min-frequency", type=int, default=1,
                       help="只显示出现至少N次的参数 (默认: 1)")
    parser.add_argument("--no-file", action="store_true",
                       help="不输出到文件，只显示在屏幕上")
    
    args = parser.parse_args()
    
    # 加载数据
    data = load_incar_data(args.file)
    if not data:
        return 1
    
    print(f"已加载 {len(data)} 个INCAR配置")
    
    # 解析键值对
    kv_pairs = parse_key_value_pairs(args.key_values)
    
    # 查找匹配的配置
    matches = find_incar_by_key_value(data, kv_pairs, not args.any_match)
    
    if not matches:
        print(f"未找到包含指定键值对的配置: {args.key_values}")
        
        # 显示可用的标签和常见值
        all_tags = set()
        for item in data:
            all_tags.update(item["incar"].keys())
        
        print(f"\n可用的标签有: {', '.join(sorted(all_tags)[:20])}")
        if len(all_tags) > 20:
            print(f"  ... 还有 {len(all_tags) - 20} 个标签")
        
        return 1
    
    print(f"找到 {len(matches)} 个匹配的配置")
    if kv_pairs:
        print(f"查询条件: {', '.join([f'{k}={v}' for k, v in kv_pairs])}")
        print(f"匹配模式: {'所有条件' if not args.any_match else '任意条件'}")
    
    # 分析参数值频率
    param_analysis = analyze_parameter_values(matches)
    
    # 生成INCAR文件内容（屏幕显示版本，包含注释）
    incar_content_screen = generate_incar_with_frequent_values(param_analysis, kv_pairs, args.min_frequency, False)
    
    # 生成INCAR文件内容（文件版本，不包含抬头注释）
    incar_content_file = generate_incar_with_frequent_values(param_analysis, kv_pairs, args.min_frequency, True)
    
    # 输出到屏幕（包含注释）
    print("\n" + "="*80)
    print("生成的INCAR参考文件:")
    print("="*80)
    print(incar_content_screen)
    
    # 输出到文件（除非指定不输出）
    if not args.no_file:
        output_file = args.output
        with open(output_file, 'w') as f:
            f.write(incar_content_file)
        print(f"\nINCAR参考文件已保存到: {output_file}")
        print("注意: 文件输出已去除抬头注释，只保留参数设置")
    
    # 显示统计信息
    total_params = len(param_analysis)
    params_with_multiple_values = sum(1 for analysis in param_analysis.values() 
                                    if len(analysis['values']) > 1)
    params_usually_nan = sum(1 for analysis in param_analysis.values() 
                           if analysis['values'] and analysis['values'].most_common(1)[0][0] == 'nan')
    
    print(f"\n统计信息:")
    print(f"  匹配配置数: {len(matches)}")
    print(f"  总参数数量: {total_params}")
    print(f"  有多个值的参数: {params_with_multiple_values}")
    print(f"  通常为nan的参数: {params_usually_nan}")
    
    return 0

if __name__ == "__main__":
    exit(main())