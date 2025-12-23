import json

def fix_batch_files():
    # 读取最终的完整数据文件
    with open('vasp_wiki_all_data.json', 'r', encoding='utf-8') as f:
        all_data = json.load(f)
    
    # 计算每个批次应有的起始索引
    batch_size = 50
    num_batches = (len(all_data) + batch_size - 1) // batch_size  # 向上取整
    
    for i in range(num_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, len(all_data))
        batch_data = all_data[start_idx:end_idx]
        
        # 保存修正后的批次数据
        filename = f'vasp_wiki_data_fixed_batch_{i + 1}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(batch_data, f, ensure_ascii=False, indent=2)
        
        print(f"已保存批次 {i + 1} ({start_idx} - {end_idx - 1}) 到 {filename}，包含 {len(batch_data)} 个页面")
    
    print(f"总共 {len(all_data)} 个页面，分为 {num_batches} 个批次")

if __name__ == "__main__":
    fix_batch_files()