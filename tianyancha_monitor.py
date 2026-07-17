#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天眼查网吧监控脚本 - 通用版
支持通过UI配置监控地区和关键词
"""
import json
import os
import time
import requests
import sys
import uuid
from datetime import datetime, timedelta

# 配置管理
class ConfigManager:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.base_dir, 'config.json')
        self.db_path = os.path.join(self.base_dir, 'database.json')
        
        # 默认配置
        self.default_config = {
            "tianyancha": {
                "api_url": "https://mcp.tianyancha.com/v1",
                "api_key": ""
            },
            "monitor": {
                "regions": [],
                "keywords": ["网吧", "网咖", "电竞"],
                "exclude_keywords": [],
                "time_range": 1
            },
            "web": {
                "port": 8080,
                "title": "网吧监控系统"
            },
            "system": {
                "version": "2.0.0",
                "last_updated": ""
            }
        }
        
        # 初始化
        if not os.path.exists(self.config_path):
            self.save_config(self.default_config)
        if not os.path.exists(self.db_path):
            self.save_db({"meta": {"version": "2.0", "total_records": 0, "last_updated": ""}, "records": []})
    
    def load_config(self):
        """加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并默认配置
                for key in self.default_config:
                    if key not in config:
                        config[key] = self.default_config[key]
                    elif isinstance(self.default_config[key], dict):
                        for k in self.default_config[key]:
                            if k not in config[key]:
                                config[key][k] = self.default_config[key][k]
                return config
        except Exception as e:
            print(f"配置加载失败: {e}")
            return self.default_config.copy()
    
    def save_config(self, config):
        """保存配置文件"""
        # 确保system字段存在
        if 'system' not in config:
            config['system'] = {}
        config['system']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"配置保存失败: {e}")
            return False
    
    def load_db(self):
        """加载数据库"""
        if not os.path.exists(self.db_path):
            return {
                "meta": {
                    "version": "2.0",
                    "total_records": 0,
                    "last_updated": ""
                },
                "records": []
            }
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"数据库加载失败: {e}")
            return {"meta": {"version": "2.0", "total_records": 0, "last_updated": ""}, "records": []}
    
    def save_db(self, db):
        """保存数据库"""
        try:
            db['meta']['total_records'] = len(db.get('records', []))
            db['meta']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"数据库保存失败: {e}")
            return False
    
    def add_record(self, record):
        """添加记录"""
        db = self.load_db()
        records = db.get('records', [])
        
        # 检查重复
        for existing in records:
            if existing.get('name') == record.get('name') and \
               existing.get('address', '') == record.get('address', ''):
                return False
        
        # 生成唯一ID
        record['id'] = str(uuid.uuid4())[:8]
        
        # 添加时间戳
        record['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        
        records.append(record)
        return self.save_db(db)
    
    def get_db_path(self):
        """获取数据库路径"""
        return self.db_path

# 全局实例
config_mgr = ConfigManager()

def tianyancha_search(keyword, api_key, estiblish_time_start=None):
    """天眼查MCP搜索"""
    try:
        url = "https://mcp.tianyancha.com/v1/core/tools/call"
        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "tool_name": "search_companies",
            "arguments": {
                "searchKey": keyword,
                "pageSize": 20
            }
        }
        
        # 添加成立时间过滤（减少API调用量）
        if estiblish_time_start:
            payload["arguments"]["estiblishTimeStart"] = estiblish_time_start
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            content = result.get('content', {})
            return content.get('items', [])
        else:
            print(f"  ⚠️ 请求失败: {response.status_code}")
            return []
    except Exception as e:
        print(f"  ❌ 搜索异常: {e}")
        return []

def extract_area(address, name):
    """从地址或名称提取地区"""
    text = (address or '') + ' ' + (name or '')
    
    # 省-市-区映射
    area_map = {
        # 四川省
        '南充': '四川省-南充市', '顺庆': '四川省-南充市-顺庆区',
        '高坪': '四川省-南充市-高坪区', '嘉陵': '四川省-南充市-嘉陵区',
        '南部': '四川省-南充市-南部县', '营山': '四川省-南充市-营山县',
        '蓬安': '四川省-南充市-蓬安县', '仪陇': '四川省-南充市-仪陇县',
        '西充': '四川省-南充市-西充县', '阆中': '四川省-南充市-阆中市',
        '成都': '四川省-成都市', '绵阳': '四川省-绵阳市',
        '自贡': '四川省-自贡市', '攀枝花': '四川省-攀枝花市',
        '泸州': '四川省-泸州市', '德阳': '四川省-德阳市',
        '广元': '四川省-广元市', '遂宁': '四川省-遂宁市',
        '内江': '四川省-内江市', '乐山': '四川省-乐山市',
        '眉山': '四川省-眉山市', '宜宾': '四川省-宜宾市',
        '广安': '四川省-广安市', '达州': '四川省-达州市',
        '雅安': '四川省-雅安市', '巴中': '四川省-巴中市',
        '资阳': '四川省-资阳市', '阿坝': '四川省-阿坝州',
        '甘孜': '四川省-甘孜州', '凉山': '四川省-凉山州',
        
        # 青海省
        '西宁': '青海省-西宁市', '城东': '青海省-西宁市-城东区',
        '城中': '青海省-西宁市-城中区', '城西': '青海省-西宁市-城西区',
        '城北': '青海省-西宁市-城北区', '大通': '青海省-西宁市-大通县',
        '湟中': '青海省-西宁市-湟中区', '湟源': '青海省-西宁市-湟源县',
        '海东': '青海省-海东市', '海北': '青海省-海北州',
        '黄南': '青海省-黄南州', '海南州': '青海省-海南州',
        '果洛': '青海省-果洛州', '玉树': '青海省-玉树州',
        '海西': '青海省-海西州', '杂多': '青海省-玉树州-杂多县',
        '曲麻莱': '青海省-玉树州-曲麻莱县', '治多': '青海省-玉树州-治多县',
        '囊谦': '青海省-玉树州-囊谦县', '玛多': '青海省-果洛州-玛多县',
        
        # 其他省份
        '北京': '北京市', '天津': '天津市', '上海': '上海市', '重庆': '重庆市',
        '石家庄': '河北省-石家庄市', '唐山': '河北省-唐山市',
        '太原': '山西省-太原市', '大同': '山西省-大同市',
        '呼和浩特': '内蒙古-呼和浩特市', '包头': '内蒙古-包头市',
        '沈阳': '辽宁省-沈阳市', '大连': '辽宁省-大连市',
        '长春': '吉林省-长春市', '哈尔滨': '黑龙江省-哈尔滨市',
        '南京': '江苏省-南京市', '苏州': '江苏省-苏州市',
        '杭州': '浙江省-杭州市', '宁波': '浙江省-宁波市',
        '合肥': '安徽省-合肥市', '福州': '福建省-福州市',
        '南昌': '江西省-南昌市', '济南': '山东省-济南市',
        '青岛': '山东省-青岛市', '郑州': '河南省-郑州市',
        '武汉': '湖北省-武汉市', '长沙': '湖南省-长沙市',
        '广州': '广东省-广州市', '深圳': '广东省-深圳市',
        '珠海': '广东省-珠海市', '汕头': '广东省-汕头市',
        '佛山': '广东省-佛山市', '韶关': '广东省-韶关市',
        '湛江': '广东省-湛江市', '肇庆': '广东省-肇庆市',
        '江门': '广东省-江门市', '茂名': '广东省-茂名市',
        '惠州': '广东省-惠州市', '梅州': '广东省-梅州市',
        '汕尾': '广东省-汕尾市', '河源': '广东省-河源市',
        '阳江': '广东省-阳江市', '清远': '广东省-清远市',
        '东莞': '广东省-东莞市', '中山': '广东省-中山市',
        '潮州': '广东省-潮州市', '揭阳': '广东省-揭阳市',
        '云浮': '广东省-云浮市',
        '南宁': '广西-南宁市', '柳州': '广西-柳州市',
        '桂林': '广西-桂林市', '海口': '海南省-海口市',
        '三亚': '海南省-三亚市',
        '贵阳': '贵州省-贵阳市', '昆明': '云南省-昆明市',
        '拉萨': '西藏-拉萨市', '西安': '陕西省-西安市',
        '兰州': '甘肃省-兰州市', '银川': '宁夏-银川市',
        '乌鲁木齐': '新疆-乌鲁木齐市',
        
        # 其他城市
        '马鞍山': '安徽省-马鞍山市', '芜湖': '安徽省-芜湖市',
        '泉州': '福建省-泉州市', '漳州': '福建省-漳州市',
        '赣州': '江西省-赣州市', '九江': '江西省-九江市',
        '烟台': '山东省-烟台市', '潍坊': '山东省-潍坊市',
        '徐州': '江苏省-徐州市', '常州': '江苏省-常州市',
        '温州': '浙江省-温州市', '嘉兴': '浙江省-嘉兴市',
        '绍兴': '浙江省-绍兴市', '金华': '浙江省-金华市',
    }
    
    # 按长度排序，优先匹配更精确的地区
    sorted_areas = sorted(area_map.items(), key=lambda x: len(x[0]), reverse=True)
    
    for keyword, area in sorted_areas:
        if keyword in text:
            return area
    
    return '未知'

def parse_record(item, keyword, api_key):
    """解析搜索结果"""
    try:
        name = item.get('name', '')
        company_id = item.get('id', '')
        
        # 获取注册地址（从API返回的数据中）
        address = item.get('regLocation', '') or ''
        
        # 优先从地址提取地区，如果没有地址则从名称提取
        area = extract_area(address, name)
        
        return {
            'name': name,
            'legal_person': item.get('legalPersonName', ''),
            'registered_capital': item.get('regCapital', ''),
            'establish_date': (item.get('estiblishTime', '') or '').split(' ')[0],
            'address': address,
            'status': '筹建审批中',
            'source': '天眼查',
            'area': area,
            'notes': f'搜索词: {keyword}',
            'company_id': str(company_id) if company_id else ''
        }
    except Exception as e:
        print(f"解析记录失败: {e}")
        return None

def extract_original_keyword(query, keywords):
    """从搜索词中提取关键词"""
    # 搜索词就是关键词本身
    for keyword in keywords:
        if query == keyword:
            return keyword
    return query

def should_exclude(name):
    """判断是否应该排除"""
    config = config_mgr.load_config()
    exclude_keywords = config.get('monitor', {}).get('exclude_keywords', [])
    
    for keyword in exclude_keywords:
        if keyword in name:
            return True
    return False

def is_in_target_regions(record, target_regions):
    """检查企业是否在目标地区内"""
    record_area = record.get('area', '')
    
    # 如果没有地区信息，返回False（跳过）
    if not record_area or record_area == '未知':
        return False
    
    # 检查是否匹配任意一个目标地区
    for target_region in target_regions:
        # 完全匹配
        if record_area == target_region:
            return True
        # 检查是否是子区域（如"四川省-南充市-顺庆区" 包含在 "四川省-南充市"）
        if record_area.startswith(target_region):
            return True
        # 检查是否是父区域（如"四川省-南充市" 包含了 "四川省-南充市-顺庆区"）
        if target_region.startswith(record_area):
            return True
    
    return False

def run_monitor():
    """运行监控"""
    config = config_mgr.load_config()
    api_key = config.get('tianyancha', {}).get('api_key', '')
    
    if not api_key:
        print("❌ 请先配置天眼查API Key")
        return
    
    keywords = config.get('monitor', {}).get('keywords', [])
    regions = config.get('monitor', {}).get('regions', [])
    time_range = config.get('monitor', {}).get('time_range', 1)  # 默认1年
    
    if not keywords:
        print("❌ 请先配置搜索关键词")
        return
    
    if not regions:
        print("❌ 请先配置监控地区")
        return
    
    # 搜索词直接使用用户设置的关键词（不添加地区前缀）
    search_queries = keywords
    
    print(f"{'='*60}")
    print(f"🔍 开始监控")
    print(f"{'='*60}")
    print(f"📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔑 API: {'***' if api_key else '未配置'}")
    print(f"🎯 关键词: {', '.join(keywords)}")
    print(f"🌍 监控地区: {', '.join(regions)}")
    print(f"⏰ 时间范围: 最近{time_range}年")
    print(f"📋 搜索词: {len(search_queries)} 个")
    for q in search_queries:
        print(f"      - {q}")
    print(f"{'='*60}")
    
    total_new = 0
    all_results = []
    
    # 计算时间过滤参数（减少API调用量）
    estiblish_time_start = None
    if time_range > 0:
        cutoff_date = datetime.now() - timedelta(days=time_range * 365)
        estiblish_time_start = cutoff_date.strftime('%Y-%m-%d')
        print(f"🔹 API过滤：只返回 {estiblish_time_start} 之后成立的企业")
    
    for query in search_queries:
        print(f"\n📋 搜索: {query}")
        results = tianyancha_search(query, api_key, estiblish_time_start)
        print(f"  找到 {len(results)} 条结果")
        
        for item in results:
            record = parse_record(item, extract_original_keyword(query, keywords), api_key)
            if not record:
                continue
            
            name = record['name']
            
            # 检查排除关键词
            if should_exclude(name):
                print(f"  ⏭️  跳过: {name} (匹配排除关键词)")
                continue
            
            # 检查时间范围
            if time_range > 0 and record.get('establish_date'):
                try:
                    cutoff_date = datetime.now() - timedelta(days=time_range * 365)
                    establish_date = datetime.strptime(record['establish_date'], '%Y-%m-%d')
                    if establish_date < cutoff_date:
                        print(f"  ⏭️  跳过: {name} (成立时间 {record['establish_date']} 超过{time_range}年)")
                        continue
                except:
                    pass  # 日期解析失败则不跳过
            
            # 检查地区匹配（防止跨地区搜索混入）
            if regions and not is_in_target_regions(record, regions):
                print(f"  ⏭️  跳过: {name} (不在监控地区范围内)")
                continue
            
            # 添加到数据库
            if config_mgr.add_record(record):
                print(f"  ✅ 新增: {name} ({record['area']})")
                total_new += 1
                all_results.append(record)
            else:
                print(f"  ⏭️  已存在: {name}")
    
    print(f"\n{'='*60}")
    print(f"✨ 监控完成！")
    print(f"{'='*60}")
    print(f"🆕 新增企业: {total_new} 家")
    
    if all_results:
        print(f"\n📋 新增企业列表:")
        for i, r in enumerate(all_results, 1):
            print(f"  {i}. {r['name']} ({r['area']})")
    
    print(f"\n⏱️  耗时: {time.time() - start_time:.2f}秒")

if __name__ == '__main__':
    start_time = time.time()
    run_monitor()
