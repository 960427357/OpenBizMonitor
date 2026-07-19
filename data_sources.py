# -*- coding: utf-8 -*-
"""
数据源抽象层
支持天眼查、企查查等多数据源统一搜索
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

import requests

from region_map import AREA_MAP

logger = logging.getLogger(__name__)


def extract_area(address, name):
    """从地址或名称提取地区"""
    text = f"{address or ''} {name or ''}"

    # 按键长度降序排序，优先匹配更精确的地区
    sorted_areas = sorted(AREA_MAP.items(), key=lambda x: len(x[0]), reverse=True)

    for keyword, area in sorted_areas:
        if keyword in text:
            return area

    return '未知'


def generate_search_combos(keyword, city_names):
    """生成搜索关键词组合，提高覆盖率"""
    combos = []

    # 关键词变体映射 - 精简核心变体，减少搜索时间
    keyword_variants = {
        '网吧': ['网吧', '网咖', '电竞网吧'],
        '网咖': ['网咖', '网吧', '电竞网咖'],
        '电竞': ['电竞', '电竞馆', '电竞俱乐部'],
        '互联网服务': ['互联网服务', '互联网信息服务'],
    }

    # 获取当前关键词的变体
    variants = keyword_variants.get(keyword, [keyword])

    # 为每个城市生成搜索组合
    for city in city_names:
        for variant in variants:
            combo = f"{city} {variant}"
            if combo not in combos:
                combos.append(combo)

    # 如果没有城市，只用关键词变体
    if not city_names:
        for variant in variants:
            if variant not in combos:
                combos.append(variant)

    return combos


def deduplicate_results(results):
    """对搜索结果去重，同名企业只保留一条"""
    seen = set()
    unique_results = []

    for record in results:
        name = record.get('name', '')
        # 只按公司名称去重（不按area，因为同名企业可能在不同搜索中出现）
        if name and name not in seen:
            seen.add(name)
            unique_results.append(record)

    return unique_results


class DataSource(ABC):
    """数据源基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def search(self, keyword: str, regions: list, time_range: int = 1) -> list:
        """搜索企业，返回统一格式的记录列表"""
        ...

    def get_company_detail(self, company_id: str) -> dict | None:
        """获取企业详情（可选实现）"""
        return None


class TianyanChaSource(DataSource):
    """天眼查MCP API"""

    name = "天眼查"

    def __init__(self, api_key: str, api_url: str = "https://mcp.tianyancha.com/v1"):
        self.api_key = api_key
        self.api_url = api_url.rstrip('/')

    def search(self, keyword, regions, time_range=1, user_id=None):
        estiblish_time_start = None
        if time_range > 0:
            cutoff = datetime.now() - timedelta(days=time_range * 365)
            estiblish_time_start = cutoff.strftime('%Y-%m-%d')

        all_results = []

        # 第一步：提取所有地区信息，去重城市
        city_searched = set()  # 已搜索过的城市
        district_list = []     # 需要搜索的区县列表

        for region in regions:
            parts = region.split('-')
            city_name = ''
            district_name = ''
            for part in parts:
                clean = part.replace('省', '').replace('市', '').replace('区', '').replace('县', '').replace('州', '')
                if not clean or len(clean) < 2:
                    continue
                if '市' in part:
                    city_name = clean
                elif '区' in part or '县' in part:
                    district_name = clean
                elif not city_name:
                    city_name = clean

            # 收集区县
            if district_name:
                district_list.append((city_name, district_name))

        # 第二步：市级搜索（每个城市只搜一次）
        for city_name in set(c for c, d in district_list):
            if city_name and city_name not in city_searched:
                city_searched.add(city_name)
                search_key = city_name + ' ' + keyword
                logger.info("天眼查搜索[市级]: %s", search_key)

                url = f"{self.api_url}/core/tools/call"
                headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
                payload = {
                    "tool_name": "search_companies",
                    "arguments": {"searchKey": search_key, "pageSize": 20}
                }
                if estiblish_time_start:
                    payload["arguments"]["estiblishTimeStart"] = estiblish_time_start

                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    items = resp.json().get('content', {}).get('items', [])
                except Exception as e:
                    logger.error("天眼查搜索失败 [%s]: %s", search_key, e)
                    continue

                for item in items:
                    record = self._parse(item, keyword)
                    if record:
                        record['area'] = city_name
                        record['notes'] = '搜索词: ' + search_key
                        all_results.append(record)

        # 第三步：区县级搜索（每个区县搜一次）
        for city_name, district_name in district_list:
            search_key = district_name + ' ' + keyword
            logger.info("天眼查搜索[区县级]: %s", search_key)

            url = f"{self.api_url}/core/tools/call"
            headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
            payload = {
                "tool_name": "search_companies",
                "arguments": {"searchKey": search_key, "pageSize": 20}
            }
            if estiblish_time_start:
                payload["arguments"]["estiblishTimeStart"] = estiblish_time_start

            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()
                items = resp.json().get('content', {}).get('items', [])
            except Exception as e:
                logger.error("天眼查搜索失败 [%s]: %s", search_key, e)
                continue

            for item in items:
                record = self._parse(item, keyword)
                if record:
                    record['area'] = district_name
                    record['notes'] = '搜索词: ' + search_key
                    all_results.append(record)

        # 去重：同名企业只保留一条
        return deduplicate_results(all_results)

    def get_company_detail(self, company_id):
        """尝试通过详情API获取地址"""
        try:
            url = f"{self.api_url}/core/tools/call"
            headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
            payload = {
                "tool_name": "get_company_detail",
                "arguments": {"companyId": int(company_id)}
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json().get('content', {})
                return {"address": data.get('regLocation', '')}
        except Exception as e:
            logger.debug("获取公司详情失败: %s", e)
        return None

    def _parse(self, item, keyword):
        try:
            name = item.get('name', '')
            company_id = str(item.get('id', ''))
            address = item.get('regLocation', '') or ''

            # 尝试通过详情API获取地址和电话
            if (not address.strip() or '电话' not in str(item)) and company_id:
                detail = self.get_company_detail(company_id)
                if detail:
                    if detail.get('address'):
                        address = detail['address']

            area = extract_area(address, name)

            # 提取电话号码
            phone = item.get('phoneNumber', '') or item.get('contactPhone', '') or ''

            return {
                'name': name,
                'legal_person': item.get('legalPersonName', ''),
                'registered_capital': item.get('regCapital', ''),
                'establish_date': (item.get('estiblishTime', '') or '').split(' ')[0],
                'address': address,
                'phone': phone,
                'status': '筹建审批中',
                'source': self.name,
                'area': area,
                'notes': f'搜索词: {keyword}',
                'company_id': company_id
            }
        except Exception as e:
            logger.error("解析记录失败: %s", e)
            return None


class QichachaSource(DataSource):
    """企查查MCP API"""

    name = "企查查"
    _tools_cache = None  # 缓存可用工具列表

    def __init__(self, api_key: str, api_url: str = "https://agent.qcc.com/mcp/company/stream"):
        self.api_key = api_key
        self.api_url = api_url

    def _mcp_request(self, method, params=None):
        """发送MCP请求"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }
        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            return None

        # 企查查返回的Content-Type是text/event-stream，编码可能是ISO-8859-1
        # 需要强制使用UTF-8解码bytes以保留正确的中文
        full_text = resp.content.decode('utf-8', errors='replace')

        # 解析SSE响应 - 企查查返回 event: message\ndata: {...} 格式
        for line in full_text.split('\n'):
            line = line.strip()
            if line.startswith('data:'):
                json_str = line[5:].strip()
                if json_str:
                    try:
                        return json.loads(json_str)
                    except Exception:
                        pass
        return None

    def _discover_tools(self):
        """发现可用的MCP工具"""
        if QichachaSource._tools_cache is not None:
            return QichachaSource._tools_cache

        logger.info("企查查: 发现可用工具...")
        result = self._mcp_request("tools/list")
        if result and 'result' in result:
            tools = result['result'].get('tools', [])
            QichachaSource._tools_cache = tools
            tool_names = [t.get('name', '') for t in tools]
            logger.info("企查查可用工具: %s", tool_names)
            return tools
        logger.warning("企查查: 无法发现工具")
        return []

    def _find_search_tool(self):
        """查找搜索相关的工具"""
        tools = self._discover_tools()
        # 企查查优先使用 get_company_by_query (企业实体识别/搜索)
        for tool in tools:
            name = tool.get('name', '')
            if name == 'get_company_by_query':
                return tool
        # 备选：查找包含 search/query 关键词的工具
        for tool in tools:
            name = tool.get('name', '').lower()
            if any(kw in name for kw in ['search', 'query', 'company_by']):
                return tool
        # 如果没找到，返回第一个工具
        if tools:
            return tools[0]
        return None

    def search(self, keyword, regions, time_range=1):
        if not self.api_key:
            logger.warning("企查查API Key未配置")
            return []

        # 查找搜索工具
        search_tool = self._find_search_tool()
        if not search_tool:
            logger.warning("企查查: 未找到可用的搜索工具")
            return []

        tool_name = search_tool.get('name', '')
        logger.info("企查查使用工具: %s", tool_name)

        # 提取城市名（只取市级）
        city_names = set()
        for region in regions:
            parts = region.split('-')
            city_part = parts[1] if len(parts) >= 2 else parts[0]
            clean = city_part.replace('省', '').replace('市', '').replace('区', '').replace('县', '').replace('州', '')
            if clean and len(clean) >= 2:
                city_names.add(clean)

        # 使用优化的搜索组合策略
        all_results = []
        search_combos = generate_search_combos(keyword, city_names)

        # 根据工具的参数定义构造请求
        tool_input = search_tool.get('inputSchema', {}).get('properties', {})
        logger.info("企查查工具参数: %s", list(tool_input.keys()))

        for search_key in search_combos:
            logger.info("企查查搜索: %s (工具: %s)", search_key, tool_name)

            # 构造参数 - 根据工具参数名灵活适配
            arguments = {}
            for param_name in tool_input:
                param_lower = param_name.lower()
                if any(kw in param_lower for kw in ['keyword', 'key', 'query', 'search', 'name', '关键词', '搜索']):
                    arguments[param_name] = search_key
                elif any(kw in param_lower for kw in ['pagesize', 'size', 'limit', 'count', '条数']):
                    arguments[param_name] = 20
                elif any(kw in param_lower for kw in ['start', 'time', 'date', '日期', '时间', '成立']):
                    if time_range > 0:
                        cutoff = datetime.now() - timedelta(days=time_range * 365)
                        arguments[param_name] = cutoff.strftime('%Y-%m-%d')

            # 至少传一个搜索关键词
            if not arguments:
                arguments = {"searchKey": search_key, "pageSize": 20}

            result = self._mcp_request("tools/call", {"name": tool_name, "arguments": arguments})

            if not result:
                logger.warning("企查查请求失败: 无响应")
                continue

            if 'error' in result:
                logger.warning("企查查工具错误: %s", result['error'].get('message', ''))
                continue

            # 解析结果
            items = []
            if 'result' in result:
                content = result['result'].get('content', [])
                for c in content:
                    if c.get('type') == 'text':
                        try:
                            text = c.get('text', '{}')
                            # 企查查返回的text可能有编码问题，尝试修复
                            try:
                                data = json.loads(text)
                            except:
                                # 尝试将Latin-1编码的字节重新解码为UTF-8
                                try:
                                    fixed_text = text.encode('latin-1').decode('utf-8')
                                    data = json.loads(fixed_text)
                                except:
                                    data = json.loads(text)

                            if isinstance(data, list):
                                items.extend(data)
                            elif isinstance(data, dict):
                                # 企查查返回格式: {"匹配结果":..., "企业信息":[...]}
                                companies = data.get('企业信息', data.get('companies', data.get('items', data.get('result', []))))
                                if isinstance(companies, list):
                                    items.extend(companies)
                                else:
                                    # 尝试所有列表类型的值
                                    for v in data.values():
                                        if isinstance(v, list) and len(v) > 0:
                                            items.extend(v)
                                            break
                        except Exception as e:
                            logger.debug("解析企查查内容失败: %s", e)

            for item in items:
                record = self._parse(item, keyword)
                if record:
                    # 用搜索到的城市名补充地区信息（只提取城市名，不包含关键词）
                    if (not record['address'] or record['area'] == '未知') and search_key != keyword:
                        # 从搜索词中提取城市名（第一个词）
                        search_city = search_key.split()[0] if search_key.split() else ''
                        if search_city:
                            record['area'] = search_city
                            record['notes'] = f'搜索词: {search_key}'
                    all_results.append(record)

        # 对结果去重
        return deduplicate_results(all_results)

    def _parse(self, item, keyword):
        try:
            # 企查查返回的键名可能是中文（编码问题导致乱码）
            # 尝试多种键名映射
            name = item.get('name', item.get('companyName', item.get('企业名称', '')))
            company_id = str(item.get('id', item.get('companyId', item.get('统一社会信用代码', ''))))
            address = item.get('regLocation', item.get('address', item.get('注册地址', ''))) or ''
            legal_person = item.get('legalPersonName', item.get('legalPerson', item.get('法定代表人名称', '')))
            capital = item.get('regCapital', item.get('registeredCapital', item.get('注册资本', '')))
            est_date = item.get('estiblishTime', item.get('establishDate', item.get('成立日期', ''))) or ''
            status = item.get('status', item.get('状态', ''))

            # 如果有编码问题的中文字段，尝试修复
            if not name:
                for k, v in item.items():
                    if isinstance(v, str) and ('网吧' in v or '网咖' in v or '电竞' in v):
                        name = v
                        break

            if not name:
                return None

            area = extract_area(address, name)

            return {
                'name': name,
                'legal_person': legal_person,
                'registered_capital': capital,
                'establish_date': est_date.split(' ')[0] if est_date else '',
                'address': address,
                'status': '筹建审批中' if not status else status,
                'source': self.name,
                'area': area,
                'notes': f'搜索词: {keyword}',
                'company_id': company_id
            }
        except Exception as e:
            logger.error("企查查解析记录失败: %s", e)
            return None


def get_active_sources(config: list) -> list:
    """根据配置返回激活的数据源列表，MCP优先"""
    sources = []
    datasource_config = config.get('datasource', {})
    active = datasource_config.get('active', ['tianyancha', 'tianyancha_web'])

    # 天眼查MCP API优先（最可靠，不被反爬）
    if 'tianyancha' in active:
        ty = config.get('tianyancha', {})
        if ty.get('api_key'):
            sources.append(TianyanChaSource(ty['api_key'], ty.get('api_url', '')))

    # 企查查MCP（如果启用）
    if 'qichacha' in active:
        qc = config.get('qichacha', {})
        if qc.get('api_key'):
            sources.append(QichachaSource(qc['api_key'], qc.get('api_url', '')))

    # 天眼查网页爬虫作为备用（可能被反爬）
    if 'tianyancha_web' in active:
        sources.append(TianyanChaWebSource())

    return sources


class SourceManager:
    """数据源管理器 - 支持优先级和失败回退"""

    def __init__(self, sources: list):
        self.sources = sources
        self._failed_sources = set()

    def search_with_fallback(self, keyword: str, regions: list, time_range: int = 1, user_id: str = None) -> list:
        """带失败回退的搜索：企查查优先，失败后自动切换天眼查"""
        all_results = []
        errors = []

        for source in self.sources:
            source_name = source.name

            # 跳过已失败的数据源
            if source_name in self._failed_sources:
                logger.info("跳过已失败的数据源: %s", source_name)
                continue

            try:
                logger.info("使用数据源: %s", source_name)
                results = source.search(keyword, regions, time_range, user_id=user_id)
                all_results.extend(results)
                logger.info("数据源 %s 返回 %d 条结果", source_name, len(results))
            except Exception as e:
                logger.error("数据源 %s 失败: %s", source_name, e)
                self._failed_sources.add(source_name)
                errors.append(f"{source_name}: {str(e)}")
                continue

        if errors and not all_results:
            logger.warning("所有数据源都失败: %s", '; '.join(errors))

        return all_results

    def reset_failures(self):
        """重置失败状态"""
        self._failed_sources.clear()

    def get_source_status(self) -> dict:
        """获取数据源状态"""
        status = {}
        for source in self.sources:
            if isinstance(source, TianyanChaWebSource):
                source_type = "Web爬虫"
            elif isinstance(source, QichachaSource):
                source_type = "MCP-SSE"
            else:
                source_type = "MCP-JSON-RPC"
            status[source.name] = {
                "active": source.name not in self._failed_sources,
                "type": source_type
            }
        return status


class TianyanChaWebSource(DataSource):
    """天眼查网页爬虫 - 使用 Playwright 无头浏览器"""

    name = "天眼查网页"

    # 全国地区代码映射（省/市/区县三级）
    AREA_CODES = {
        '上海市': '00310000V2024',
        '上海市-嘉定区': '00310114V2024',
        '上海市-奉贤区': '00310120V2024',
        '上海市-宝山区': '00310113V2024',
        '上海市-崇明区': '00310151V2024',
        '上海市-徐汇区': '00310104V2024',
        '上海市-普陀区': '00310107V2024',
        '上海市-杨浦区': '00310110V2024',
        '上海市-松江区': '00310117V2024',
        '上海市-浦东新区': '00310115V2024',
        '上海市-虹口区': '00310109V2024',
        '上海市-金山区': '00310116V2024',
        '上海市-长宁区': '00310105V2024',
        '上海市-闵行区': '00310112V2024',
        '上海市-青浦区': '00310118V2024',
        '上海市-静安区': '00310106V2024',
        '上海市-黄浦区': '00310101V2024',
        '云南省': '00530000V2024',
        '云南省-临沧市': '00530900V2024',
        '云南省-丽江市': '00530700V2024',
        '云南省-保山市': '00530500V2024',
        '云南省-大理白族自治州': '00532900V2024',
        '云南省-德宏傣族景颇族自治州': '00533100V2024',
        '云南省-怒江傈僳族自治州': '00533300V2024',
        '云南省-文山壮族苗族自治州': '00532600V2024',
        '云南省-昆明市': '00530100V2024',
        '云南省-昭通市': '00530600V2024',
        '云南省-普洱市': '00530800V2024',
        '云南省-曲靖市': '00530300V2024',
        '云南省-楚雄彝族自治州': '00532300V2024',
        '云南省-玉溪市': '00530400V2024',
        '云南省-红河哈尼族彝族自治州': '00532500V2024',
        '云南省-西双版纳傣族自治州': '00532800V2024',
        '云南省-迪庆藏族自治州': '00533400V2024',
        '内蒙古自治区': '00150000V2024',
        '内蒙古自治区-乌兰察布市': '00150900V2024',
        '内蒙古自治区-乌海市': '00150300V2024',
        '内蒙古自治区-包头市': '00150200V2024',
        '内蒙古自治区-呼伦贝尔市': '00150700V2024',
        '内蒙古自治区-呼和浩特市': '00150100V2024',
        '内蒙古自治区-巴彦淖尔市': '00150800V2024',
        '内蒙古自治区-赤峰市': '00150400V2024',
        '内蒙古自治区-通辽市': '00150500V2024',
        '内蒙古自治区-鄂尔多斯市': '00150600V2024',
        '北京市': '00110000V2024',
        '北京市-东城区': '00110101V2024',
        '北京市-丰台区': '00110106V2024',
        '北京市-大兴区': '00110115V2024',
        '北京市-密云区': '00110118V2024',
        '北京市-平谷区': '00110117V2024',
        '北京市-延庆区': '00110119V2024',
        '北京市-怀柔区': '00110116V2024',
        '北京市-房山区': '00110111V2024',
        '北京市-昌平区': '00110114V2024',
        '北京市-朝阳区': '00110105V2024',
        '北京市-海淀区': '00110108V2024',
        '北京市-石景山区': '00110107V2024',
        '北京市-西城区': '00110102V2024',
        '北京市-通州区': '00110112V2024',
        '北京市-门头沟区': '00110109V2024',
        '北京市-顺义区': '00110113V2024',
        '吉林省': '00220000V2024',
        '吉林省-吉林市': '00220200V2024',
        '吉林省-四平市': '00220300V2024',
        '吉林省-松原市': '00220700V2024',
        '吉林省-白城市': '00220800V2024',
        '吉林省-白山市': '00220600V2024',
        '吉林省-辽源市': '00220400V2024',
        '吉林省-通化市': '00220500V2024',
        '吉林省-长春市': '00220100V2024',
        '四川省': '00510000V2024',
        '四川省-乐山市': '00511100V2024',
        '四川省-内江市': '00511000V2024',
        '四川省-凉山彝族自治州': '00513400V2024',
        '四川省-南充市': '00511300V2024',
        '四川省-南充市-仪陇县': '00511324V2024',
        '四川省-南充市-南部县': '00511321V2024',
        '四川省-南充市-嘉陵区': '00511304V2024',
        '四川省-南充市-营山县': '00511322V2024',
        '四川省-南充市-蓬安县': '00511323V2024',
        '四川省-南充市-西充县': '00511325V2024',
        '四川省-南充市-阆中市': '00511381V2024',
        '四川省-南充市-顺庆区': '00511302V2024',
        '四川省-南充市-高坪区': '00511303V2024',
        '四川省-宜宾市': '00511500V2024',
        '四川省-巴中市': '00511900V2024',
        '四川省-广元市': '00510800V2024',
        '四川省-广安市': '00511600V2024',
        '四川省-德阳市': '00510600V2024',
        '四川省-成都市': '00510100V2024',
        '四川省-成都市-双流区': '00510116V2024',
        '四川省-成都市-大邑县': '00510129V2024',
        '四川省-成都市-崇州市': '00510184V2024',
        '四川省-成都市-彭州市': '00510182V2024',
        '四川省-成都市-成华区': '00510108V2024',
        '四川省-成都市-新津区': '00510118V2024',
        '四川省-成都市-新都区': '00510114V2024',
        '四川省-成都市-武侯区': '00510107V2024',
        '四川省-成都市-温江区': '00510115V2024',
        '四川省-成都市-简阳市': '00510185V2024',
        '四川省-成都市-蒲江县': '00510131V2024',
        '四川省-成都市-邛崃市': '00510183V2024',
        '四川省-成都市-郫都区': '00510117V2024',
        '四川省-成都市-都江堰市': '00510181V2024',
        '四川省-成都市-金堂县': '00510121V2024',
        '四川省-成都市-金牛区': '00510106V2024',
        '四川省-成都市-锦江区': '00510104V2024',
        '四川省-成都市-青白江区': '00510113V2024',
        '四川省-成都市-青羊区': '00510105V2024',
        '四川省-成都市-龙泉驿区': '00510112V2024',
        '四川省-攀枝花市': '00510400V2024',
        '四川省-泸州市': '00510500V2024',
        '四川省-甘孜藏族自治州': '00513300V2024',
        '四川省-眉山市': '00511400V2024',
        '四川省-绵阳市': '00510700V2024',
        '四川省-自贡市': '00510300V2024',
        '四川省-资阳市': '00512000V2024',
        '四川省-达州市': '00511700V2024',
        '四川省-遂宁市': '00510900V2024',
        '四川省-阿坝藏族羌族自治州': '00513200V2024',
        '四川省-雅安市': '00511800V2024',
        '天津市': '00120000V2024',
        '天津市-东丽区': '00120110V2024',
        '天津市-北辰区': '00120113V2024',
        '天津市-南开区': '00120104V2024',
        '天津市-和平区': '00120101V2024',
        '天津市-宁河区': '00120117V2024',
        '天津市-宝坻区': '00120115V2024',
        '天津市-武清区': '00120114V2024',
        '天津市-河东区': '00120102V2024',
        '天津市-河北区': '00120105V2024',
        '天津市-河西区': '00120103V2024',
        '天津市-津南区': '00120112V2024',
        '天津市-滨海新区': '00120116V2024',
        '天津市-红桥区': '00120106V2024',
        '天津市-蓟州区': '00120119V2024',
        '天津市-西青区': '00120111V2024',
        '天津市-静海区': '00120118V2024',
        '宁夏回族自治区': '00640000V2024',
        '宁夏回族自治区-中卫市': '00640500V2024',
        '宁夏回族自治区-吴忠市': '00640300V2024',
        '宁夏回族自治区-固原市': '00640400V2024',
        '宁夏回族自治区-石嘴山市': '00640200V2024',
        '宁夏回族自治区-银川市': '00640100V2024',
        '安徽省': '00340000V2024',
        '安徽省-亳州市': '00341600V2024',
        '安徽省-六安市': '00341500V2024',
        '安徽省-合肥市': '00340100V2024',
        '安徽省-安庆市': '00340800V2024',
        '安徽省-宣城市': '00341800V2024',
        '安徽省-宿州市': '00341300V2024',
        '安徽省-池州市': '00341700V2024',
        '安徽省-淮北市': '00340600V2024',
        '安徽省-淮南市': '00340400V2024',
        '安徽省-滁州市': '00341100V2024',
        '安徽省-芜湖市': '00340200V2024',
        '安徽省-蚌埠市': '00340300V2024',
        '安徽省-铜陵市': '00340700V2024',
        '安徽省-阜阳市': '00341200V2024',
        '安徽省-马鞍山市': '00340500V2024',
        '安徽省-黄山市': '00341000V2024',
        '山东省': '00370000V2024',
        '山东省-东营市': '00370500V2024',
        '山东省-临沂市': '00371300V2024',
        '山东省-威海市': '00371000V2024',
        '山东省-德州市': '00371400V2024',
        '山东省-日照市': '00371100V2024',
        '山东省-枣庄市': '00370400V2024',
        '山东省-泰安市': '00370900V2024',
        '山东省-济南市': '00370100V2024',
        '山东省-济宁市': '00370800V2024',
        '山东省-淄博市': '00370300V2024',
        '山东省-滨州市': '00371600V2024',
        '山东省-潍坊市': '00370700V2024',
        '山东省-烟台市': '00370600V2024',
        '山东省-聊城市': '00371500V2024',
        '山东省-菏泽市': '00371700V2024',
        '山东省-青岛市': '00370200V2024',
        '山西省': '00140000V2024',
        '山西省-临汾市': '00141000V2024',
        '山西省-吕梁市': '00141100V2024',
        '山西省-大同市': '00140200V2024',
        '山西省-太原市': '00140100V2024',
        '山西省-太原市-万柏林区': '00140109V2024',
        '山西省-太原市-古交市': '00140181V2024',
        '山西省-太原市-娄烦县': '00140123V2024',
        '山西省-太原市-小店区': '00140105V2024',
        '山西省-太原市-尖草坪区': '00140108V2024',
        '山西省-太原市-晋源区': '00140110V2024',
        '山西省-太原市-杏花岭区': '00140107V2024',
        '山西省-太原市-清徐县': '00140121V2024',
        '山西省-太原市-迎泽区': '00140106V2024',
        '山西省-太原市-阳曲县': '00140122V2024',
        '山西省-忻州市': '00140900V2024',
        '山西省-晋中市': '00140700V2024',
        '山西省-晋城市': '00140500V2024',
        '山西省-朔州市': '00140600V2024',
        '山西省-运城市': '00140800V2024',
        '山西省-长治市': '00140400V2024',
        '山西省-阳泉市': '00140300V2024',
        '广东省': '00440000V2024',
        '广东省-东莞市': '00441900V2024',
        '广东省-中山市': '00442000V2024',
        '广东省-云浮市': '00445300V2024',
        '广东省-佛山市': '00440600V2024',
        '广东省-广州市': '00440100V2024',
        '广东省-惠州市': '00441300V2024',
        '广东省-揭阳市': '00445200V2024',
        '广东省-梅州市': '00441400V2024',
        '广东省-汕头市': '00440500V2024',
        '广东省-汕尾市': '00441500V2024',
        '广东省-江门市': '00440700V2024',
        '广东省-河源市': '00441600V2024',
        '广东省-深圳市': '00440300V2024',
        '广东省-清远市': '00441800V2024',
        '广东省-湛江市': '00440800V2024',
        '广东省-潮州市': '00445100V2024',
        '广东省-珠海市': '00440400V2024',
        '广东省-肇庆市': '00441200V2024',
        '广东省-茂名市': '00440900V2024',
        '广东省-阳江市': '00441700V2024',
        '广东省-韶关市': '00440200V2024',
        '广西壮族自治区': '00450000V2024',
        '广西壮族自治区-北海市': '00450500V2024',
        '广西壮族自治区-南宁市': '00450100V2024',
        '广西壮族自治区-崇左市': '00451400V2024',
        '广西壮族自治区-来宾市': '00451300V2024',
        '广西壮族自治区-柳州市': '00450200V2024',
        '广西壮族自治区-桂林市': '00450300V2024',
        '广西壮族自治区-梧州市': '00450400V2024',
        '广西壮族自治区-河池市': '00451200V2024',
        '广西壮族自治区-玉林市': '00450900V2024',
        '广西壮族自治区-百色市': '00451000V2024',
        '广西壮族自治区-贵港市': '00450800V2024',
        '广西壮族自治区-贺州市': '00451100V2024',
        '广西壮族自治区-钦州市': '00450700V2024',
        '广西壮族自治区-防城港市': '00450600V2024',
        '新疆维吾尔自治区': '00650000V2024',
        '新疆维吾尔自治区-乌鲁木齐市': '00650100V2024',
        '新疆维吾尔自治区-伊犁哈萨克自治州': '00654000V2024',
        '新疆维吾尔自治区-克孜勒苏柯尔克孜自治州': '00653000V2024',
        '新疆维吾尔自治区-克拉玛依市': '00650200V2024',
        '新疆维吾尔自治区-博尔塔拉蒙古自治州': '00652700V2024',
        '新疆维吾尔自治区-吐鲁番市': '00650400V2024',
        '新疆维吾尔自治区-和田地区': '00653200V2024',
        '新疆维吾尔自治区-哈密市': '00650500V2024',
        '新疆维吾尔自治区-喀什地区': '00653100V2024',
        '新疆维吾尔自治区-塔城地区': '00654200V2024',
        '新疆维吾尔自治区-巴音郭楞蒙古自治州': '00652800V2024',
        '新疆维吾尔自治区-昌吉回族自治州': '00652300V2024',
        '新疆维吾尔自治区-阿克苏地区': '00652900V2024',
        '新疆维吾尔自治区-阿勒泰地区': '00654300V2024',
        '江苏省': '00320000V2024',
        '江苏省-南京市': '00320100V2024',
        '江苏省-南通市': '00320600V2024',
        '江苏省-宿迁市': '00321300V2024',
        '江苏省-常州市': '00320400V2024',
        '江苏省-徐州市': '00320300V2024',
        '江苏省-扬州市': '00321000V2024',
        '江苏省-无锡市': '00320200V2024',
        '江苏省-泰州市': '00321200V2024',
        '江苏省-淮安市': '00320800V2024',
        '江苏省-盐城市': '00320900V2024',
        '江苏省-苏州市': '00320500V2024',
        '江苏省-连云港市': '00320700V2024',
        '江苏省-镇江市': '00321100V2024',
        '江西省': '00360000V2024',
        '江西省-上饶市': '00361100V2024',
        '江西省-九江市': '00360400V2024',
        '江西省-南昌市': '00360100V2024',
        '江西省-吉安市': '00360800V2024',
        '江西省-宜春市': '00360900V2024',
        '江西省-抚州市': '00361000V2024',
        '江西省-新余市': '00360500V2024',
        '江西省-景德镇市': '00360200V2024',
        '江西省-萍乡市': '00360300V2024',
        '江西省-赣州市': '00360700V2024',
        '江西省-鹰潭市': '00360600V2024',
        '河北省': '00130000V2024',
        '河北省-保定市': '00130600V2024',
        '河北省-唐山市': '00130200V2024',
        '河北省-廊坊市': '00131000V2024',
        '河北省-张家口市': '00130700V2024',
        '河北省-承德市': '00130800V2024',
        '河北省-沧州市': '00130900V2024',
        '河北省-石家庄市': '00130100V2024',
        '河北省-秦皇岛市': '00130300V2024',
        '河北省-衡水市': '00131100V2024',
        '河北省-邢台市': '00130500V2024',
        '河北省-邯郸市': '00130400V2024',
        '河南省': '00410000V2024',
        '河南省-三门峡市': '00411200V2024',
        '河南省-信阳市': '00411500V2024',
        '河南省-南阳市': '00411300V2024',
        '河南省-周口市': '00411600V2024',
        '河南省-商丘市': '00411400V2024',
        '河南省-安阳市': '00410500V2024',
        '河南省-平顶山市': '00410400V2024',
        '河南省-开封市': '00410200V2024',
        '河南省-新乡市': '00410700V2024',
        '河南省-洛阳市': '00410300V2024',
        '河南省-漯河市': '00411100V2024',
        '河南省-濮阳市': '00410900V2024',
        '河南省-焦作市': '00410800V2024',
        '河南省-许昌市': '00411000V2024',
        '河南省-郑州市': '00410100V2024',
        '河南省-驻马店市': '00411700V2024',
        '河南省-鹤壁市': '00410600V2024',
        '浙江省': '00330000V2024',
        '浙江省-丽水市': '00331100V2024',
        '浙江省-台州市': '00331000V2024',
        '浙江省-嘉兴市': '00330400V2024',
        '浙江省-宁波市': '00330200V2024',
        '浙江省-杭州市': '00330100V2024',
        '浙江省-温州市': '00330300V2024',
        '浙江省-湖州市': '00330500V2024',
        '浙江省-绍兴市': '00330600V2024',
        '浙江省-舟山市': '00330900V2024',
        '浙江省-衢州市': '00330800V2024',
        '浙江省-金华市': '00330700V2024',
        '海南省': '00460000V2024',
        '海南省-三亚市': '00460200V2024',
        '海南省-三沙市': '00460300V2024',
        '海南省-儋州市': '00460400V2024',
        '海南省-海口市': '00460100V2024',
        '湖北省': '00420000V2024',
        '湖北省-十堰市': '00420300V2024',
        '湖北省-咸宁市': '00421200V2024',
        '湖北省-孝感市': '00420900V2024',
        '湖北省-宜昌市': '00420500V2024',
        '湖北省-恩施土家族苗族自治州': '00422800V2024',
        '湖北省-武汉市': '00420100V2024',
        '湖北省-荆州市': '00421000V2024',
        '湖北省-荆门市': '00420800V2024',
        '湖北省-襄阳市': '00420600V2024',
        '湖北省-鄂州市': '00420700V2024',
        '湖北省-随州市': '00421300V2024',
        '湖北省-黄冈市': '00421100V2024',
        '湖北省-黄石市': '00420200V2024',
        '湖南省': '00430000V2024',
        '湖南省-娄底市': '00431300V2024',
        '湖南省-岳阳市': '00430600V2024',
        '湖南省-常德市': '00430700V2024',
        '湖南省-张家界市': '00430800V2024',
        '湖南省-怀化市': '00431200V2024',
        '湖南省-株洲市': '00430200V2024',
        '湖南省-永州市': '00431100V2024',
        '湖南省-湘潭市': '00430300V2024',
        '湖南省-湘西土家族苗族自治州': '00433100V2024',
        '湖南省-益阳市': '00430900V2024',
        '湖南省-衡阳市': '00430400V2024',
        '湖南省-邵阳市': '00430500V2024',
        '湖南省-郴州市': '00431000V2024',
        '湖南省-长沙市': '00430100V2024',
        '甘肃省': '00620000V2024',
        '甘肃省-临夏回族自治州': '00622900V2024',
        '甘肃省-兰州市': '00620100V2024',
        '甘肃省-嘉峪关市': '00620200V2024',
        '甘肃省-天水市': '00620500V2024',
        '甘肃省-定西市': '00621100V2024',
        '甘肃省-平凉市': '00620800V2024',
        '甘肃省-庆阳市': '00621000V2024',
        '甘肃省-张掖市': '00620700V2024',
        '甘肃省-武威市': '00620600V2024',
        '甘肃省-甘南藏族自治州': '00623000V2024',
        '甘肃省-白银市': '00620400V2024',
        '甘肃省-酒泉市': '00620900V2024',
        '甘肃省-金昌市': '00620300V2024',
        '甘肃省-陇南市': '00621200V2024',
        '福建省': '00350000V2024',
        '福建省-三明市': '00350400V2024',
        '福建省-南平市': '00350700V2024',
        '福建省-厦门市': '00350200V2024',
        '福建省-宁德市': '00350900V2024',
        '福建省-泉州市': '00350500V2024',
        '福建省-漳州市': '00350600V2024',
        '福建省-福州市': '00350100V2024',
        '福建省-莆田市': '00350300V2024',
        '福建省-龙岩市': '00350800V2024',
        '西藏自治区': '00540000V2024',
        '西藏自治区-山南市': '00540500V2024',
        '西藏自治区-拉萨市': '00540100V2024',
        '西藏自治区-日喀则市': '00540200V2024',
        '西藏自治区-昌都市': '00540300V2024',
        '西藏自治区-林芝市': '00540400V2024',
        '西藏自治区-那曲市': '00540600V2024',
        '西藏自治区-阿里地区': '00542500V2024',
        '贵州省': '00520000V2024',
        '贵州省-六盘水市': '00520200V2024',
        '贵州省-安顺市': '00520400V2024',
        '贵州省-毕节市': '00520500V2024',
        '贵州省-贵阳市': '00520100V2024',
        '贵州省-遵义市': '00520300V2024',
        '贵州省-铜仁市': '00520600V2024',
        '贵州省-黔东南苗族侗族自治州': '00522600V2024',
        '贵州省-黔南布依族苗族自治州': '00522700V2024',
        '贵州省-黔西南布依族苗族自治州': '00522300V2024',
        '辽宁省': '00210000V2024',
        '辽宁省-丹东市': '00210600V2024',
        '辽宁省-大连市': '00210200V2024',
        '辽宁省-抚顺市': '00210400V2024',
        '辽宁省-朝阳市': '00211300V2024',
        '辽宁省-本溪市': '00210500V2024',
        '辽宁省-沈阳市': '00210100V2024',
        '辽宁省-盘锦市': '00211100V2024',
        '辽宁省-营口市': '00210800V2024',
        '辽宁省-葫芦岛市': '00211400V2024',
        '辽宁省-辽阳市': '00211000V2024',
        '辽宁省-铁岭市': '00211200V2024',
        '辽宁省-锦州市': '00210700V2024',
        '辽宁省-阜新市': '00210900V2024',
        '辽宁省-鞍山市': '00210300V2024',
        '重庆市': '00500000V2024',
        '重庆市-万州区': '00500101V2024',
        '重庆市-九龙坡区': '00500107V2024',
        '重庆市-北碚区': '00500109V2024',
        '重庆市-南岸区': '00500108V2024',
        '重庆市-南川区': '00500119V2024',
        '重庆市-合川区': '00500117V2024',
        '重庆市-大渡口区': '00500104V2024',
        '重庆市-巴南区': '00500113V2024',
        '重庆市-开州区': '00500154V2024',
        '重庆市-梁平区': '00500155V2024',
        '重庆市-武隆区': '00500156V2024',
        '重庆市-永川区': '00500118V2024',
        '重庆市-江北区': '00500105V2024',
        '重庆市-江津区': '00500116V2024',
        '重庆市-沙坪坝区': '00500106V2024',
        '重庆市-涪陵区': '00500102V2024',
        '重庆市-渝中区': '00500103V2024',
        '重庆市-渝北区': '00500112V2024',
        '重庆市-潼南区': '00500152V2024',
        '重庆市-璧山区': '00500120V2024',
        '重庆市-荣昌区': '00500153V2024',
        '重庆市-铜梁区': '00500151V2024',
        '重庆市-长寿区': '00500115V2024',
        '陕西省': '00610000V2024',
        '陕西省-咸阳市': '00610400V2024',
        '陕西省-商洛市': '00611000V2024',
        '陕西省-安康市': '00610900V2024',
        '陕西省-宝鸡市': '00610300V2024',
        '陕西省-延安市': '00610600V2024',
        '陕西省-榆林市': '00610800V2024',
        '陕西省-汉中市': '00610700V2024',
        '陕西省-渭南市': '00610500V2024',
        '陕西省-西安市': '00610100V2024',
        '陕西省-铜川市': '00610200V2024',
        '青海省': '00630000V2024',
        '青海省-果洛藏族自治州': '00632600V2024',
        '青海省-海东市': '00630200V2024',
        '青海省-海北藏族自治州': '00632200V2024',
        '青海省-海南藏族自治州': '00632500V2024',
        '青海省-海西蒙古族藏族自治州': '00632800V2024',
        '青海省-玉树藏族自治州': '00632700V2024',
        '青海省-西宁市': '00630100V2024',
        '青海省-西宁市-城东区': '00630102V2024',
        '青海省-西宁市-城中区': '00630103V2024',
        '青海省-西宁市-城西区': '00630104V2024',
        '青海省-西宁市-城北区': '00630105V2024',
        '青海省-西宁市-大通县': '00630121V2024',
        '青海省-西宁市-湟中区': '00630122V2024',
        '青海省-西宁市-湟源县': '00630123V2024',
        '青海省-黄南藏族自治州': '00632300V2024',
        '青海省-玉树藏族自治州-杂多县': '00632722V2024',
        '青海省-玉树藏族自治州-曲麻莱县': '00632726V2024',
        '青海省-玉树藏族自治州-治多县': '00632724V2024',
        '青海省-玉树藏族自治州-囊谦县': '00632725V2024',
        '青海省-果洛藏族自治州-玛多县': '00632633V2024',
        '黑龙江省': '00230000V2024',
        '黑龙江省-七台河市': '00230900V2024',
        '黑龙江省-伊春市': '00230700V2024',
        '黑龙江省-佳木斯市': '00230800V2024',
        '黑龙江省-双鸭山市': '00230500V2024',
        '黑龙江省-哈尔滨市': '00230100V2024',
        '黑龙江省-大庆市': '00230600V2024',
        '黑龙江省-牡丹江市': '00231000V2024',
        '黑龙江省-绥化市': '00231200V2024',
        '黑龙江省-鸡西市': '00230300V2024',
        '黑龙江省-鹤岗市': '00230400V2024',
        '黑龙江省-黑河市': '00231100V2024',
        '黑龙江省-齐齐哈尔市': '00230200V2024',
    }

    def search(self, keyword, regions, time_range=1, user_id=None):
        """搜索企业（使用 Playwright 无头浏览器）"""
        import browser_manager

        all_results = []

        # 时间筛选参数映射（4个时间点）
        # establishTime: 1=3个月, 2=半年, 3=1年, 4=1~3年
        time_filters = {0.25: '1', 0.5: '2', 1: '3', 3: '4'}
        time_filter = time_filters.get(time_range, '3')

        for region in regions:
            area_code = self.AREA_CODES.get(region)
            if not area_code:
                logger.warning("天眼查网页: 未找到地区代码 %s", region)
                continue

            # 构建URL
            url = f"https://www.tianyancha.com/search?key={keyword}&areaCode={area_code}&establishTime={time_filter}"
            logger.info("天眼查网页搜索: %s", region)

            for attempt in range(2):  # 最多重试2次
                try:
                    # 使用 Playwright 获取页面内容
                    if user_id:
                        state = browser_manager.get_page_content_for_user(user_id, url, timeout=60000)
                    else:
                        state = browser_manager.get_page_content(url, timeout=60000)

                    if not state or len(state) < 100:
                        logger.warning("天眼查网页: 获取页面状态失败")
                        continue

                    # 解析结果
                    results = self._parse_results(state, region)

                    if results or attempt > 0:
                        all_results.extend(results)
                        logger.info("天眼查网页: %s - %s, 找到 %d 条结果", region, keyword, len(results))
                        break

                    # 第一次没找到结果，可能是页面未完全渲染，重试
                    if not results and attempt == 0:
                        logger.info("天眼查网页: 第一次未找到结果，重试中...")
                        import time
                        time.sleep(3)

                except Exception as e:
                    logger.error("天眼查网页搜索失败: %s - %s", region, e)
                    continue

        return deduplicate_results(all_results)

    def _parse_results(self, state_output, region):
        """解析搜索结果 - 按企业分区提取，避免字段错位"""
        results = []
        import re

        # 第一步：找到所有企业链接的位置，按位置分割HTML
        company_links = list(re.finditer(r'/company/(\d+)', state_output))
        logger.info("解析搜索结果: 找到 %d 个企业链接, HTML长度=%d", len(company_links), len(state_output))

        # 调试：打印HTML中包含company的片段
        if company_links:
            for m in company_links[:3]:
                start = max(0, m.start() - 50)
                end = min(len(state_output), m.end() + 100)
                logger.info("企业链接片段: ...%s...", state_output[start:end].replace('\n', ' ')[:200])
        else:
            # 检查HTML中是否有company字样
            company_count = state_output.count('/company/')
            logger.info("HTML中/company/出现次数: %d", company_count)
            if company_count > 0:
                idx = state_output.find('/company/')
                logger.info("第一个/company/位置: %s", state_output[max(0,idx-50):idx+100].replace('\n', ' ')[:200])

        if not company_links:
            # 检查是否被反爬拦截
            if '操作存在异常' in state_output or '暂停您的访问' in state_output:
                logger.warning("天眼查反爬拦截，页面被封锁")
            elif '登录' in state_output and '扫码' in state_output:
                logger.warning("天眼查需要登录，未获取到搜索结果")
            return results

        # 第二步：按企业链接位置分割HTML为多个区块
        # 每个区块包含一个企业的所有信息
        sections = []
        for i, match in enumerate(company_links):
            start = match.start()
            # 结束位置：下一个企业链接的开始位置，或文件末尾（预留5000字符）
            if i + 1 < len(company_links):
                end = company_links[i + 1].start()
            else:
                end = min(start + 5000, len(state_output))
            sections.append((match.group(1), state_output[start:end]))

        # 第三步：逐个区块提取企业信息
        for company_id, section in sections:
            # 提取企业名称
            name = ''
            # 模式1: >...文字<em>高亮</em>剩余文字</span> (完整名称)
            name_match = re.search(r'/company/' + company_id + r'[^>]*>(?:<[^>]*>)*([^<]+)<em>([^<]+)</em>([^<]*)</span>', section)
            if name_match:
                name = (name_match.group(1) + name_match.group(2) + name_match.group(3)).strip()
            else:
                # 模式2: >...文字<em>高亮</em> (无后续文字)
                name_match2 = re.search(r'/company/' + company_id + r'[^>]*>(?:<[^>]*>)*([^<]+)<em>([^<]+)</em>', section)
                if name_match2:
                    name = (name_match2.group(1) + name_match2.group(2)).strip()
                else:
                    # 模式3: >...文字</a> (无高亮)
                    name_match3 = re.search(r'/company/' + company_id + r'[^>]*>(?:<[^>]*>)*([^<]{2,60})</a>', section)
                    if name_match3:
                        name = name_match3.group(1).strip()

            name = re.sub(r'\s+', '', name)
            name = re.sub(r'<[^>]+>', '', name)

            if not name or len(name) < 2:
                logger.debug("跳过: name太短或为空, company_id=%s, name='%s'", company_id, name)
                continue

            # 提取成立日期
            date = ''
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', section)
            if date_match:
                date = date_match.group(1)

            # 提取地址 - 在当前区块内查找
            address = ''
            addr_match = re.search(r'((?:北京|天津|上海|重庆|河北|山西|内蒙古|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|广西|海南|四川|贵州|云南|西藏|陕西|甘肃|青海|宁夏|新疆)[^<]{5,80})', section)
            if addr_match:
                address = addr_match.group(1).strip()

            # 提取法定代表人/投资人/经营者
            legal_person = ''
            # 天眼查用"投资人"或"经营者"字段
            for field in ['投资人', '经营者', '法定代表人', '负责人', '法人']:
                lp_match = re.search(field + r'<!-- -->：.*?<span>([^<]+)</span>', section)
                if not lp_match:
                    lp_match = re.search(field + r'[：:]\s*<[^>]*><span>([^<]+)</span>', section)
                if not lp_match:
                    lp_match = re.search(field + r'[：:]\s*([^<]{2,20})', section)
                if lp_match:
                    legal_person = lp_match.group(1).strip()
                    if legal_person in ['：', ':', '—', '-', '/', '', ' ']:
                        legal_person = ''
                    else:
                        break

            # 提取注册资本/出资额
            capital = ''
            # 天眼查用"出资额"字段
            cap_match = re.search(r'出资额<!-- -->：.*?title="([^"]+)"', section)
            if not cap_match:
                cap_match = re.search(r'出资额[：:]\s*<[^>]*title="([^"]+)"', section)
            if not cap_match:
                cap_match = re.search(r'出资额[：:]\s*([^<]+)', section)
            if not cap_match:
                # 尝试注册资本
                cap_match = re.search(r'注册资本<!-- -->：.*?title="([^"]+)"', section)
            if not cap_match:
                cap_match = re.search(r'注册资本[：:]\s*([^<]+)', section)
            if not cap_match:
                # 通用匹配金额
                cap_match = re.search(r'(\d+(?:\.\d+)?万(?:人民币|元|USD))', section)
            if cap_match:
                capital = cap_match.group(1).strip()

            # 提取电话号码
            phone = ''
            # 优先匹配有标签的电话字段
            phone_match = re.search(r'(?:电话|手机|联系)[：:]\s*(?:<[^>]*>)*([\d\-]{7,20})', section)
            if not phone_match:
                # 匹配手机号（1开头，11位，不能是company_id）
                phone_match = re.search(r'(?:^|[>\s])(1[3-9]\d{9})(?:[<\s]|$)', section)
            if not phone_match:
                # 匹配座机号（区号+号码）
                phone_match = re.search(r'(?:^|[>\s])(0\d{2,3}[-]?\d{7,8})(?:[<\s]|$)', section)
            if phone_match:
                phone = phone_match.group(1) if phone_match.lastindex else phone_match.group(0)
                phone = re.sub(r'\s+', '', phone)
                # 验证：排除明显不是电话的数字（如company_id）
                if len(phone) == 10 and phone.isdigit():
                    phone = ''  # 10位纯数字很可能是公司ID，不是电话

            # 数据验证 - 过滤无效记录
            if ';' in name or '经营范围' in name or '营业执照' in name:
                continue
            if name.startswith('...'):
                continue

            # 提取地区
            area = extract_area(address, name)
            if area == '未知':
                parts = region.split('-')
                if len(parts) >= 2:
                    area = parts[1].replace('市', '').replace('省', '')

            results.append({
                'name': name,
                'company_id': company_id,
                'legal_person': legal_person,
                'registered_capital': capital,
                'establish_date': date,
                'address': address,
                'phone': phone,
                'status': '筹建审批中',
                'source': self.name,
                'area': area,
                'notes': f'来源: 天眼查网页',
            })

        return results
