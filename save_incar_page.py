from vasp_wiki_scraper import VASPWIKIScraper
import json

def save_incar_page():
    scraper = VASPWIKIScraper()
    page_content = scraper.get_page_content('INCAR')
    
    with open('incar_page_content.json', 'w', encoding='utf-8') as f:
        json.dump(page_content, f, ensure_ascii=False, indent=2)
    
    print(f"已保存页面 '{page_content['title']}' 的内容到 incar_page_content.json")
    print(f"URL: {page_content['url']}")
    print(f"内容长度: {len(page_content['content'])} 字符")

if __name__ == "__main__":
    save_incar_page()