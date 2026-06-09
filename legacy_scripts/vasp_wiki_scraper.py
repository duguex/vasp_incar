import requests
from bs4 import BeautifulSoup
import time
import json
import os
from urllib.parse import urljoin, quote

class VASPWIKIScraper:
    def __init__(self):
        self.base_url = "https://vasp.at/wiki/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def get_all_pages(self):
        """
        获取所有页面列表
        """
        all_pages = []
        # 首先尝试获取以特定字符开头的所有页面
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

        for char in alphabet:
            url = f"{self.base_url}Special:AllPages?from={char}"
            print(f"正在获取以 {char} 开头的页面: {url}")

            # 获取以当前字母开头的所有页面
            page_url = url
            while page_url:
                print(f"正在获取页面: {page_url}")
                response = self.session.get(page_url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                # 查找页面列表
                page_list = soup.find('div', {'id': 'mw-content-text'})
                if page_list:
                    for link in page_list.find_all('a', href=True):
                        href = link.get('href')
                        if href and '/wiki/' in href and not href.startswith('/wiki/Special:'):
                            page_name = href.split('/wiki/')[-1]
                            if page_name not in all_pages and page_name != '':
                                all_pages.append(page_name)

                # 查找下一页链接
                next_link = soup.find('a', string=lambda text: text and 'Next page' in text)
                if next_link:
                    page_url = urljoin(self.base_url, next_link.get('href'))
                    print(f"找到下一页: {page_url}")
                else:
                    # 检查是否有">"符号表示下一页
                    next_link = soup.find('a', string='>')
                    if next_link:
                        page_url = urljoin(self.base_url, next_link.get('href'))
                        print(f"找到下一页: {page_url}")
                    else:
                        print(f"以 {char} 开头的页面已全部获取")
                        page_url = None

                # 避免请求过于频繁
                time.sleep(1)

        # 最后获取特殊页面
        special_url = self.base_url + "Special:AllPages"
        print(f"正在获取特殊页面: {special_url}")
        response = self.session.get(special_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        page_list = soup.find('div', {'id': 'mw-content-text'})
        if page_list:
            for link in page_list.find_all('a', href=True):
                href = link.get('href')
                if href and '/wiki/' in href and not href.startswith('/wiki/Special:'):
                    page_name = href.split('/wiki/')[-1]
                    if page_name not in all_pages and page_name != '':
                        all_pages.append(page_name)

        return all_pages
    
    def get_page_content(self, page_name):
        """
        获取单个页面的内容
        """
        url = self.base_url + page_name
        print(f"正在获取页面内容: {url}")
        
        response = self.session.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取页面标题
        title = soup.find('h1', {'class': 'firstHeading'})
        title_text = title.get_text().strip() if title else page_name
        
        # 提取主要内容
        content_div = soup.find('div', {'id': 'mw-content-text'})
        if content_div:
            # 移除编辑链接等无关元素
            for edit_link in content_div.find_all('div', {'class': 'mw-editsection'}):
                edit_link.decompose()
            
            content = content_div.get_text(separator='\\n', strip=True)
        else:
            content = ""
        
        return {
            'title': title_text,
            'url': url,
            'content': content
        }
    
    def scrape_all_pages(self, output_dir='vasp_wiki_data'):
        """
        爬取所有页面内容
        """
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取所有页面列表
        print("正在获取所有页面列表...")
        all_pages = self.get_all_pages()
        print(f"共找到 {len(all_pages)} 个页面")
        
        # 爬取每个页面
        scraped_data = []
        for i, page_name in enumerate(all_pages):
            try:
                page_data = self.get_page_content(page_name)
                scraped_data.append(page_data)
                
                # 每爬取10个页面保存一次
                if (i + 1) % 10 == 0 or i == len(all_pages) - 1:
                    filename = os.path.join(output_dir, f'vasp_wiki_data_part_{i//10 + 1}.json')
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(scraped_data, f, ensure_ascii=False, indent=2)
                    print(f"已保存 {len(scraped_data)} 个页面到 {filename}")
                    
                    # 清空当前数据，继续下一个批次
                    if i < len(all_pages) - 1:
                        scraped_data = []
                
                # 避免请求过于频繁
                time.sleep(1)
                
            except Exception as e:
                print(f"爬取页面 {page_name} 时出错: {e}")
                continue
    
    def scrape_specific_pages(self, page_names, output_file='vasp_wiki_data.json'):
        """
        爬取特定页面
        """
        scraped_data = []
        for page_name in page_names:
            try:
                page_data = self.get_page_content(page_name)
                scraped_data.append(page_data)
                print(f"已爬取: {page_data['title']}")
                
                # 避免请求过于频繁
                time.sleep(1)
                
            except Exception as e:
                print(f"爬取页面 {page_name} 时出错: {e}")
                continue
        
        # 保存数据
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(scraped_data, f, ensure_ascii=False, indent=2)
        
        print(f"已将 {len(scraped_data)} 个页面保存到 {output_file}")

if __name__ == "__main__":
    scraper = VASPWIKIScraper()
    
    # 示例：爬取特定页面
    # scraper.scrape_specific_pages(['INCAR', 'POSCAR', 'KPOINTS', 'POTCAR'])
    
    # 或者爬取所有页面（注意：这可能需要很长时间）
    # scraper.scrape_all_pages()