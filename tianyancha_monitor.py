#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网吧监控脚本 - 通用版
支持多数据源（天眼查、企查查）
"""
import sys
import io
import time
from datetime import datetime, timedelta

# 修复Windows控制台GBK编码不支持emoji的问题
if sys.platform == 'win32' and sys.stdout and sys.stdout.buffer:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

from log_config import setup_logging, get_logger
from config_manager import config_mgr
from data_sources import get_active_sources, SourceManager

logger = get_logger('monitor')


def should_exclude(name, config):
    """判断是否应该排除"""
    exclude_keywords = config.get('monitor', {}).get('exclude_keywords', [])
    for keyword in exclude_keywords:
        if keyword in name:
            return True
    return False


def is_in_target_regions(record, target_regions):
    """检查企业是否在目标地区内"""
    record_area = record.get('area', '')

    if not record_area or record_area == '未知':
        return False

    # 清理地区名称（去掉省/市/区/县/州后缀，用于模糊匹配）
    def clean_area(area):
        return area.replace('省', '').replace('市', '').replace('区', '').replace('县', '').replace('州', '')

    record_clean = clean_area(record_area)

    for target_region in target_regions:
        # 精确匹配
        if record_area == target_region:
            return True
        # record_area 是 target_region 的子区域
        if record_area.startswith(target_region):
            return True
        # target_region 是 record_area 的子区域
        if target_region.startswith(record_area):
            return True
        # 模糊匹配：检查清理后的名称是否互相包含
        # 例如 "南充" 匹配 "四川省-南充市"
        target_clean = clean_area(target_region)
        if record_clean and target_clean:
            if record_clean in target_clean or target_clean in record_clean:
                return True

    return False


def run_monitor(user_id=None):
    """运行监控"""
    if user_id:
        config = config_mgr.load_user_config(user_id)
    else:
        config = config_mgr.load_config()
    keywords = config.get('monitor', {}).get('keywords', [])
    regions = config.get('monitor', {}).get('regions', [])
    time_range = config.get('monitor', {}).get('time_range', 1)

    if not keywords:
        logger.error("未配置搜索关键词")
        print("错误: 请先配置搜索关键词")
        return

    if not regions:
        logger.error("未配置监控地区")
        print("错误: 请先配置监控地区")
        return

    sources = get_active_sources(config)
    if not sources:
        logger.error("没有可用的数据源，请检查API Key配置")
        print("错误: 没有可用的数据源，请检查API Key配置")
        return

    # 使用SourceManager实现优先级回退
    source_manager = SourceManager(sources)

    source_names = ', '.join(s.name for s in sources)
    logger.info("="*60)
    logger.info("开始监控")
    logger.info("数据源优先级: %s (企查查优先，失败自动回退)", source_names)
    logger.info("关键词: %s", ', '.join(keywords))
    logger.info("监控地区: %s", ', '.join(regions))
    logger.info("时间范围: 最近%d年", time_range)

    print(f"{'='*60}")
    print(f"开始监控")
    print(f"{'='*60}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"数据源: {source_names} (企查查优先)")
    print(f"关键词: {', '.join(keywords)}")
    print(f"监控地区: {', '.join(regions)}")
    print(f"时间范围: 最近{time_range}年")
    print(f"搜索词: {len(keywords)} 个")
    for q in keywords:
        print(f"      - {q}")
    print(f"{'='*60}")

    total_new = 0
    all_results = []

    for keyword in keywords:
        logger.info("搜索: %s", keyword)
        print(f"\n搜索: {keyword}")

        # 使用SourceManager进行带回退的搜索
        results = source_manager.search_with_fallback(keyword, regions, time_range, user_id=user_id)

        logger.info("搜索完成: keyword=%s, 找到 %d 条结果", keyword, len(results))
        print(f"  找到 {len(results)} 条结果")

        for record in results:
            name = record['name']

            if should_exclude(name, config):
                logger.debug("跳过(排除关键词): %s", name)
                print(f"  跳过: {name} (匹配排除关键词)")
                continue

            if time_range > 0 and record.get('establish_date'):
                try:
                    cutoff_date = datetime.now() - timedelta(days=time_range * 365)
                    establish_date = datetime.strptime(record['establish_date'], '%Y-%m-%d')
                    if establish_date < cutoff_date:
                        logger.debug("跳过(时间过期): %s %s", name, record['establish_date'])
                        print(f"  跳过: {name} (成立时间 {record['establish_date']} 超过{time_range}年)")
                        continue
                except ValueError:
                    pass

            if regions and not is_in_target_regions(record, regions):
                logger.info("跳过(地区不匹配): %s area=%s", name, record.get('area'))
                print(f"  跳过: {name} (地区: {record.get('area', '未知')} 不在监控范围内)")
                continue

            logger.info("匹配成功: %s area=%s date=%s", name, record.get('area'), record.get('establish_date'))

            if user_id:
                added = config_mgr.add_user_record(user_id, record)
            else:
                added = config_mgr.add_record(record)
            if added:
                logger.info("新增: %s area=%s source=%s", name, record['area'], record.get('source', '未知'))
                print(f"  新增: {name} ({record['area']})")
                total_new += 1
                all_results.append(record)
            else:
                logger.debug("已存在: %s", name)
                print(f"  已存在: {name}")

    logger.info("="*60)
    logger.info("监控完成! 新增 %d 家企业", total_new)
    print(f"\n{'='*60}")
    print(f"监控完成!")
    print(f"{'='*60}")
    print(f"新增企业: {total_new} 家")

    if all_results:
        print(f"\n新增企业列表:")
        for i, r in enumerate(all_results, 1):
            print(f"  {i}. {r['name']} ({r['area']})")


if __name__ == '__main__':
    setup_logging()

    # 解析 --user-id 参数
    user_id = None
    for i, arg in enumerate(sys.argv):
        if arg == '--user-id' and i + 1 < len(sys.argv):
            user_id = sys.argv[i + 1]

    if user_id:
        logger.info("监控脚本启动 (user=%s)", user_id)
    else:
        logger.info("监控脚本启动")

    start_time = time.time()
    run_monitor(user_id=user_id)
    elapsed = time.time() - start_time
    logger.info("监控脚本结束, 耗时 %.2f秒", elapsed)
    print(f"\n耗时: {elapsed:.2f}秒")
