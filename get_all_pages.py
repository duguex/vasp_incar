import json
from vasp_wiki_scraper import VASPWIKIScraper

def save_all_pages_list():
    """
    获取并保存所有页面列表到文件
    """
    scraper = VASPWIKIScraper()
    pages = scraper.get_all_pages()
    
    # 保存页面列表到JSON文件
    with open('vasp_wiki_pages.json', 'w', encoding='utf-8') as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)
    
    print(f"已获取 {len(pages)} 个页面，已保存到 vasp_wiki_pages.json")
    
    # 打印一些统计信息
    print("\n页面统计信息:")
    print(f"总页面数: {len(pages)}")
    
    # 找出包含特定关键词的页面
    incar_pages = [page for page in pages if 'incar' in page.lower()]
    print(f"包含 'INCAR' 的页面数: {len(incar_pages)}")
    print("包含 'INCAR' 的页面:")
    for page in incar_pages:
        print(f"  - {page}")
    
    print("\n前20个页面:")
    for i, page in enumerate(pages[:20]):
        print(f"  {i+1}. {page}")
    
    print("\n后20个页面:")
    for i, page in enumerate(pages[-20:]):
        print(f"  {len(pages)-19+i}. {page}")

if __name__ == "__main__":
    save_all_pages_list()