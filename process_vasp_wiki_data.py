import json
import os
from vasp_wiki_scraper import VASPWIKIScraper

def process_and_store_data(input_file='vasp_wiki_data.json', output_dir='processed_vasp_wiki_data'):
    """
    处理和存储爬取的数据
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 读取爬取的数据
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 处理数据 - 这里可以添加各种处理逻辑
    processed_data = []
    for item in data:
        # 例如，可以提取特定部分的内容，或进行文本清洗
        processed_item = {
            'title': item['title'],
            'url': item['url'],
            'content': item['content']  # 可以在这里添加内容处理逻辑
        }
        processed_data.append(processed_item)
    
    # 按标题首字母分类存储
    categorized_data = {}
    for item in processed_data:
        first_char = item['title'][0].upper()
        if not first_char.isalnum():  # 如果不是字母或数字，归类为'OTHER'
            first_char = 'OTHER'
        
        if first_char not in categorized_data:
            categorized_data[first_char] = []
        categorized_data[first_char].append(item)
    
    # 将分类后的数据保存到不同文件
    for char, items in categorized_data.items():
        filename = os.path.join(output_dir, f'vasp_wiki_data_{char}.json')
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"已将 {len(items)} 个以 '{char}' 开头的页面保存到 {filename}")
    
    # 创建一个索引文件
    index_data = {
        'total_pages': len(processed_data),
        'categories': list(categorized_data.keys()),
        'category_counts': {char: len(items) for char, items in categorized_data.items()}
    }
    
    index_filename = os.path.join(output_dir, 'index.json')
    with open(index_filename, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"索引文件已保存到 {index_filename}")

def run_full_scraping_pipeline():
    """
    运行完整的爬取和处理流程
    """
    scraper = VASPWIKIScraper()
    
    # 爬取特定VASP相关页面
    vasp_pages = [
        'INCAR', 'POSCAR', 'KPOINTS', 'POTCAR', 'CHGCAR', 'DOSCAR', 
        'EIGENVAL', 'IBZKPT', 'LOCPOT', 'OSZICAR', 'OUTCAR', 'PARCHG', 
        'PCDAT', 'PROCAR', 'REPORT', 'STOPCAR', 'WAVECAR', 'XDATCAR',
        'ALGO', 'ENCUT', 'EDIFF', 'NSW', 'ISIF', 'ISYM', 'SIGMA',
        'LREAL', 'LWAVE', 'LCHARG', 'ICHARG', 'NELM', 'NELMIN',
        'NSUB', 'ALGO', 'LHFCALC', 'AEXX', 'HFSCREEN', 'TIME',
        'LDAU', 'LDAUTYPE', 'LDAUL', 'LDAUU', 'LDAUJ', 'LDAUPRINT',
        'LMAXMIX', 'AMIX', 'BMIX', 'AMIX_MAG', 'BMIX_MAG',
        'PMIN', 'SMASS', 'APACO', 'POMASS', 'EATOM', 'LPARD',
        'LCORR', 'LMONO', 'LDIPOL', 'IDIPOL', 'DIPOL', 'EFIELD',
        'LUSE_VDW', 'VDW_S6', 'VDW_DS6', 'VDW_D', 'VDW_SCAL6',
        'LNONCOLLINEAR', 'LSORBIT', 'SAXIS', 'MAGMOM', 'ISPIN',
        'LVTOT', 'LVHAR', 'LORBIT', 'RWIGS', 'DMDAV', 'DMDIM',
        'DMNAX', 'KINTER', 'CONSTR', 'SQA', 'SQE', 'MDALGO',
        'PSTRESS', 'TEBEG', 'TEEND', 'SMASS', 'POTIM', 'NSW',
        'IBRION', 'NFREE', 'POTIM', 'IOPT', 'IFOO', 'DFIELD',
        'EBREAK', 'FBREAK', 'DTION', 'DFION', 'SDEV', 'IMAGES',
        'LANGEVIN_GAMMA', 'LANGEVIN_GAMMA_L', 'SQUISH', 'POMASS',
        'APACO', 'PSTRESS', 'SYMPREC', 'IMAGE', 'NIMAGE', 'SPRING',
        'LCLIMB', 'LSYMM', 'LNEBCELL', 'SCHAIN', 'SCINVCURV',
        'SPRING', 'LNEBCELL', 'LCLIMB', 'LSYMM', 'SCINVCURV',
        'KSPACING', 'KGAMMA', 'LORBITALREAL', 'LPLANE', 'NSUB',
        'NPAR', 'NCORE', 'LSCALAPACK', 'LWRITE_MMN', 'LWRITE_MMKP',
        'LNABLA', 'LVEL', 'VCA', 'XCOMPAT', 'LCOMPAT', 'LDAU',
        'LDAUTYPE', 'LDAUL', 'LDAUU', 'LDAUJ', 'LDAUPRINT',
        'LMAXMIX', 'LREAL', 'LREAL_COMPAT', 'LREAL_IN_CORE',
        'NSW', 'IBRION', 'ISIF', 'ISPIN', 'ICHARG', 'LWAVE',
        'LCHARG', 'LVTOT', 'LVHAR', 'LORBIT', 'RWIGS', 'ALGO',
        'EDIFF', 'EDIFFG', 'NSW', 'NELM', 'NELMIN', 'ENAUG',
        'PREC', 'ENCUT', 'ENCUTGW', 'SIGMA', 'ISMEAR', 'AMIX',
        'BMIX', 'AMIX_MAG', 'BMIX_MAG', 'PMIN', 'TIME', 'LMONO',
        'LDIPOL', 'IDIPOL', 'DIPOL', 'EFIELD', 'LUSE_VDW',
        'LVDW', 'VDW_S6', 'VDW_DS6', 'VDW_D', 'VDW_SCAL6',
        'LNONCOLLINEAR', 'LSORBIT', 'SAXIS', 'MAGMOM', 'NUPDOWN',
        'LORBIT', 'LVDW_EWALD', 'LVDW_THRESH', 'IVDW',
        'HFSCREEN', 'HFSCREENC', 'AEXX', 'ALDAC', 'AGGAC',
        'TIME', 'LMETAGGA', 'CSHIFT', 'Fermi-level', 'Fermi energy',
        'DOS', 'Density of States', 'Band structure', 'KPOINTS',
        'K-point', 'Brillouin zone', 'VASP', 'Ab initio', 'DFT',
        'DFT+U', 'Hubbard U', 'LDA', 'GGA', 'PBE', 'PW', 'PAW',
        'Plane wave', 'Pseudopotential', 'VASP tutorial',
        'VASP examples', 'VASP calculations', 'Electronic structure',
        'Ionic relaxation', 'Geometry optimization', 'SCF',
        'Self-consistent field', 'Convergence', 'VASP INCAR tags',
        'VASP parameters', 'VASP settings', 'VASP configuration'
    ]
    
    # 爬取数据
    print("开始爬取VASP wiki页面...")
    scraper.scrape_specific_pages(vasp_pages, 'vasp_wiki_raw_data.json')
    
    # 处理和存储数据
    print("开始处理和存储数据...")
    process_and_store_data('vasp_wiki_raw_data.json', 'processed_vasp_wiki_data')

if __name__ == "__main__":
    # 执行完整的爬取和处理流程
    run_full_scraping_pipeline()