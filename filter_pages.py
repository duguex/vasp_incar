import json

def filter_pages():
    # 读取原始页面列表
    with open('vasp_wiki_pages.json', 'r', encoding='utf-8') as f:
        all_pages = json.load(f)
    
    # 过滤掉Special:AllPages相关的分页链接
    real_pages = [p for p in all_pages if not p.startswith('index.php?title=Special:AllPages') and p != 'Special:AllPages']
    
    # 保存过滤后的页面列表
    with open('vasp_wiki_real_pages.json', 'w', encoding='utf-8') as f:
        json.dump(real_pages, f, ensure_ascii=False, indent=2)
    
    print(f"原始页面数: {len(all_pages)}")
    print(f"真实页面数: {len(real_pages)}")
    print(f"过滤掉的页面数: {len(all_pages) - len(real_pages)}")
    
    # 显示包含INCAR的真实页面
    incar_pages = [p for p in real_pages if 'INCAR' in p.upper()]
    print(f"\n包含'INCAR'的真实页面 ({len(incar_pages)} 个):")
    for page in incar_pages:
        print(f"  - {page}")

if __name__ == "__main__":
    filter_pages()