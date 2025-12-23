import json
import time
from vasp_wiki_scraper import VASPWIKIScraper
from tqdm import tqdm

def scrape_all_real_pages():
    # 读取真实页面列表
    with open('vasp_wiki_real_pages.json', 'r', encoding='utf-8') as f:
        pages = json.load(f)
    
    print(f"开始爬取 {len(pages)} 个真实页面")
    
    scraper = VASPWIKIScraper()
    all_data = []
    
    batch_data = []  # 用于存储当前批次的数据

    # 使用tqdm显示进度
    for i, page_name in enumerate(tqdm(pages, desc="爬取进度", unit="page")):
        try:
            page_data = scraper.get_page_content(page_name)
            all_data.append(page_data)
            batch_data.append(page_data)  # 同时添加到当前批次

            # 每爬取50个页面保存一次，以防程序中断导致数据丢失
            if (i + 1) % 50 == 0:
                batch_num = (i // 50) + 1
                filename = f'vasp_wiki_data_batch_{batch_num}.json'
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(batch_data, f, ensure_ascii=False, indent=2)
                print(f"\n已保存批次 {batch_num} 到 {filename}")

                # 清空当前批次数据，准备下一组
                batch_data = []

            # 时间间隔2秒
            time.sleep(2)

        except Exception as e:
            print(f"\n爬取页面 {page_name} 时出错: {e}")
            continue

    # 保存最后一批数据（如果不足50个）
    if batch_data:
        batch_num = (len(pages) // 50) + 1
        filename = f'vasp_wiki_data_batch_{batch_num}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(batch_data, f, ensure_ascii=False, indent=2)
        print(f"\n已保存最后一批数据到 {filename}")
    
    # 保存所有数据
    with open('vasp_wiki_all_data.json', 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n已完成爬取 {len(all_data)} 个页面，数据已保存到 vasp_wiki_all_data.json")

if __name__ == "__main__":
    scrape_all_real_pages()