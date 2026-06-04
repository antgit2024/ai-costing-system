# -*- coding: utf-8 -*-

"""
每日监测数据计算脚本 - V5专业版 (时间一致性修复版)
功能：基于净值监测 + 持仓跟踪，生成每日监测记录并同步到宜搭

V5核心改进：
1. 基于fund_nav_data表的真实历史数据进行趋势判断
2. 使用fund_basic_info表的个性化风险阈值
3. 专业的"中期趋势+当日调整"判断方案
4. 解决"都下跌了还显示普通上涨"的问题

时间一致性修复：
5. 修复holdings表查询的时间点一致性问题
6. 确保holding_date和updated_at都不超过分析日期
7. 避免使用"未来"数据计算历史收益

作者：基金分析系统
版本：5.0 - 时间一致性修复版
日期：2025-06-28
"""

import sys
import os
import json
import logging
import argparse
import pymysql
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class OAuth2Client:
    """OAuth2客户端"""
    def __init__(self, app_key, app_secret):
        self.app_key = app_key
        self.app_secret = app_secret
        self.access_token = None
        self.token_expires_at = 0
        self.base_url = "https://api.dingtalk.com/v1.0"
        
    def get_access_token(self):
        """获取访问令牌"""
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token
            
        try:
            url = "https://oapi.dingtalk.com/gettoken"
            params = {
                'appkey': self.app_key,
                'appsecret': self.app_secret
            }
            response = requests.get(url, params=params)
            result = response.json()
            
            if result.get('errcode') == 0:
                self.access_token = result['access_token']
                self.token_expires_at = time.time() + result['expires_in'] - 300  # 提前5分钟刷新
                return self.access_token
            else:
                raise Exception(f"获取token失败: {result}")
                
        except Exception as e:
            raise Exception(f"OAuth2认证失败: {e}")

class DailyMonitoringCalculatorV5:
    """每日监测计算器 - V5专业版"""
    
    def __init__(self, config_path: str = None):
        """初始化计算器"""
        # 设置配置文件路径
        if config_path is None:
            # 尝试多个可能的配置文件位置
            possible_paths = [
                '/home/ubuntu/config/yida_config.json',
                '/home/admin/fund_sync_v2/config/yida_config.json',
                './config/yida_config.json',
                './yida_config.json'
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
                    break
            
            if config_path is None:
                raise FileNotFoundError("未找到配置文件，请检查配置文件路径")
        
        self.config_path = config_path
        self.config = self._load_config()
        self.logger = self._setup_logger()
        
        # 宜搭表单配置 - 使用固定的form_uuid
        self.form_uuid = "FORM-9E85D027BD0A490D84641BB161B4B0D72G3Q"
        
        # 初始化宜搭客户端
        self.oauth_client = OAuth2Client(
            self.config['yida']['app_key'],
            self.config['yida']['app_secret']
        )
        
        # 记录ID缓存，用于批量处理
        self.existing_record_cache = {}
        
        # 字段映射配置（RDS字段名 -> 宜搭字段ID）
        self.field_mapping = {
            'analysis_date': 'dateField_l0c4zqvy',
            'record_id': 'textField_mbmwduwh',
            'fund_code': 'textField_maq60d8w',
            'fund_name': 'textField_maq60d8x',
            'fund_type': 'selectField_matblv4t',
            'holder': 'selectField_maq9ebgv',
            'unit_nav': 'numberField_mb2w4w1o',
            'accumulated_nav': 'numberField_mb2w4w1p',
            'daily_return': 'numberField_mb2w4w1q',
            'latest_nav_date': 'dateField_mb7kcnqf',
            'holding_shares': 'numberField_mat0lij3',
            'market_value': 'numberField_mbmwduwj',
            'accumulated_profit': 'numberField_mat0liiy',
            'total_return_rate': 'numberField_mat0liiz',
            'return_1w': 'numberField_maq958g4',
            'hs300_return_1w': 'numberField_mb5ompo4',
            'avg_return_1w': 'numberField_maqm1bqo',
            'holding_end_date': 'dateField_mat0lij6',
            'today_change': 'numberField_mbmwduwi',
            'vs_hs300': 'numberField_mbmwduwt',
            'suggested_position_ratio': 'numberField_mbojsdb3',
            'volatility_7d': 'numberField_mbmwduwp',
            'consecutive_days': 'numberField_mbnmeqr8',
            'avg_return_7d': 'numberField_mbmwduws',
            'alert_enabled': 'selectField_mbmwduw7',
            'alert_status': 'selectField_mbmwduwr',
            'risk_level': 'selectField_mbmwduwq',
            'trend_direction': 'selectField_mbmwduwu',
            'suggested_action': 'selectField_mbojsdb4',
            'max_drawdown': 'numberField_mbojsdb5',
            'drawdown_status': 'selectField_mbojsdb7',
            'weekly_report_code': 'textField_mb9hjfgu',
            'ai_analysis_status': 'selectField_mbtgh4q5',
            'ai_recommendation': 'selectField_mbr8wu5v',
            'ai_analysis_time': 'dateField_mbr8wu5y',
            'ai_rating': 'selectField_mbr8wu5w',
            'ai_confidence': 'numberField_mbr8wu5x',
            'ai_action_advice': 'textareaField_mbr8wu60',
            'ai_analysis_result': 'textareaField_mbr8wu5u',
            'ai_decision_basis': 'textareaField_mbr8wu5z',
            'pe_percentile': 'numberField_mcb7dpso',  # PE分位点
            'return_3m': 'numberField_mcb7dpsw',  # 近3月涨幅
            'return_1y': 'numberField_mcb7dpsx',  # 近1年涨幅
            'drawdown_attention': 'numberField_mboh0rtp',
            'drawdown_alert': 'numberField_mboh0rtq',
            'credit_spread_alert': 'numberField_mboh0rtr',
            'attention_return_threshold': 'numberField_mbmwduw0',
            'alert_return_threshold': 'numberField_mbmwduw3',
            'attention_consecutive_days': 'numberField_mbmwduw6',
            'alert_consecutive_days': 'numberField_mbmw6vjo',
            'volatility_attention_threshold': 'numberField_mbmwduw1',
            'ai_analysis_instruction': 'textareaField_mbrdlnt4',
            'ai_operation_logic': 'textField_mboh0rtm'
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.logger.info("配置文件加载成功") if hasattr(self, 'logger') else print("配置文件加载成功")
            return config
        except Exception as e:
            print(f"配置文件加载失败: {e}")
            raise
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger('DailyMonitoringCalculatorV5')
        logger.setLevel(logging.INFO)
        
        # 避免重复添加handler
        if not logger.handlers:
            # 控制台输出
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 日志格式
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        return logger
    
    def _get_db_connection(self) -> pymysql.Connection:
        """获取数据库连接"""
        try:
            connection = pymysql.connect(
                host=self.config['rds']['host'],
                port=self.config['rds']['port'],
                user=self.config['rds']['username'],  # 修正字段名
                password=self.config['rds']['password'],
                database=self.config['rds']['database'],
                charset='utf8mb4',
                autocommit=True
            )
            return connection
        except Exception as e:
            self.logger.error(f"数据库连接失败: {e}")
            raise
    
    def get_base_data(self, fund_codes: List[str] = None, analysis_date: date = None) -> List[Dict[str, Any]]:
        """
        获取基础数据 - 简化版
        
        核心改进：
        1. 直接从 holdings 获取持仓数据
        2. 从 fund_nav_data 获取最新净值
        3. 计算估算市值和收益变化
        4. 避免依赖 daily_returns 表
        """
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    
                    # 如果没有指定分析日期，使用今天
                    if analysis_date is None:
                        analysis_date = date.today()
                    
                    self.logger.info(f"🔍 获取 {analysis_date} 的监测数据")
                    
                    # 1. 获取活跃基金列表
                    if fund_codes:
                        fund_filter = f"AND fbi.fund_code IN ({','.join(['%s'] * len(fund_codes))})"
                        fund_params = fund_codes
                    else:
                        fund_filter = ""
                        fund_params = []
                    
                    # 获取持有状态的基金基础信息
                    fund_sql = f"""
                    SELECT 
                        fbi.fund_code,
                        fbi.fund_name,
                        fbi.fund_type,
                        fbi.holder,
                        fbi.drawdown_attention,
                        fbi.drawdown_warning as drawdown_alert,
                        fbi.credit_spread_warning as credit_spread_alert,
                        fbi.attention_threshold as attention_return_threshold,
                        fbi.warning_threshold as alert_return_threshold,
                        fbi.attention_consecutive_days,
                        fbi.warning_consecutive_days as alert_consecutive_days,
                        fbi.volatility_threshold as volatility_attention_threshold,
                        fbi.ai_analysis_instruction,
                        fbi.ai_operation_logic
                    FROM fund_basic_info fbi
                    WHERE fbi.management_status = '持有'
                    {fund_filter}
                    ORDER BY fbi.fund_code
                    LIMIT 30
                    """
                    
                    cursor.execute(fund_sql, fund_params)
                    fund_list = cursor.fetchall()
                    
                    if not fund_list:
                        self.logger.warning("未找到活跃基金")
                        return []
                    
                    self.logger.info(f"📊 找到 {len(fund_list)} 个活跃基金")
                    
                    results = []
                    
                    for fund_info in fund_list:
                        fund_code = fund_info['fund_code']
                        
                        try:
                            # 2. 获取最新净值数据（基于分析日期）
                            nav_data = self._get_latest_nav_data(cursor, fund_code, analysis_date)
                            if not nav_data:
                                self.logger.warning(f"⚠️ {fund_code} 无净值数据，跳过")
                                continue
                            
                            # 3. 获取最新持仓数据（分析日期之前的最新数据）
                            holding_data = self._get_latest_holding_data(cursor, fund_code, analysis_date)
                            self.logger.info(f"🔍 {fund_code} 持仓数据获取完成: {holding_data}")
                            
                            # 4. 计算估算市值和收益（与原始脚本完全一致）
                            self.logger.info(f"🔍 {fund_code} 准备调用_calculate_estimated_values")
                            calculated_data = self._calculate_estimated_values(
                                nav_data, holding_data, fund_code, analysis_date
                            )
                            self.logger.info(f"🔍 {fund_code} _calculate_estimated_values调用完成: {calculated_data}")
                            
                            # 5. 获取历史表现数据
                            performance_data = self._get_performance_data(cursor, fund_code)
                            
                            # 6. 合并所有数据
                            record = {
                                **fund_info,
                                **nav_data,
                                **holding_data,  # 添加持仓数据
                                **calculated_data,
                                **performance_data,
                                'analysis_date': analysis_date
                            }
                            
                            results.append(record)
                            self.logger.info(f"✅ {fund_code} 数据处理完成")
                            
                        except Exception as e:
                            self.logger.error(f"❌ 处理 {fund_code} 失败: {e}")
                            continue
                    
                    self.logger.info(f"🎉 共处理 {len(results)} 条记录")
                    return results
                    
        except Exception as e:
            self.logger.error(f"获取基础数据失败: {e}")
            return []

    def _get_latest_nav_data(self, cursor, fund_code: str, analysis_date: date) -> Dict[str, Any]:
        """获取最新净值数据 - 基于分析日期获取净值"""
        try:
            # 获取分析日期或之前的最新净值
            query = """
            SELECT 
                nav_date,
                unit_nav,
                total_nav as accumulated_nav,
                daily_return
            FROM fund_nav_data 
            WHERE fund_code = %s AND nav_date <= %s 
            ORDER BY nav_date DESC 
            LIMIT 1
            """
            cursor.execute(query, (fund_code, analysis_date))
            latest_nav = cursor.fetchone()
            
            if not latest_nav:
                self.logger.warning(f"   ⚠️ {fund_code} 在{analysis_date}之前无净值数据")
                return {
                    'latest_nav_date': analysis_date,
                    'unit_nav': 1.0000,
                    'accumulated_nav': 1.0000,
                    'daily_return': 0.0
                }
            
            # 获取历史净值用于计算收益率
            history_query = """
            SELECT daily_return
            FROM fund_nav_data 
            WHERE fund_code = %s AND nav_date <= %s 
            ORDER BY nav_date DESC 
            LIMIT 30
            """
            cursor.execute(history_query, (fund_code, analysis_date))
            history_data = cursor.fetchall()
            
            # 计算7日平均收益率
            recent_7d = [row['daily_return'] for row in history_data[:7] if row['daily_return'] is not None]
            avg_return_7d = sum(recent_7d) / len(recent_7d) if recent_7d else 0
            
            self.logger.info(f"   📊 {fund_code} 净值数据: 分析日期={analysis_date}, 净值日期={latest_nav['nav_date']}, 净值={latest_nav['unit_nav']}")
            
            return {
                'latest_nav_date': latest_nav['nav_date'],
                'unit_nav': float(latest_nav['unit_nav']),
                'accumulated_nav': float(latest_nav['accumulated_nav']),
                'daily_return': float(latest_nav['daily_return'] or 0),
                'avg_return_7d': avg_return_7d
            }
            
        except Exception as e:
            self.logger.error(f"获取净值数据失败 {fund_code}: {e}")
            return {
                'latest_nav_date': analysis_date,
                'unit_nav': 1.0000,
                'accumulated_nav': 1.0000,
                'daily_return': 0.0,
                'avg_return_7d': 0.0
            }

    def _get_latest_holding_data(self, cursor, fund_code: str, analysis_date: date) -> Dict[str, Any]:
        """获取最新持仓数据 - 时间一致性修复版"""
        try:
            query = """
            SELECT 
                holding_shares,
                market_value,
                accumulated_earnings,
                total_return,
                return_rate as total_return_rate,
                current_nav as unit_nav,
                daily_return,
                avg_cost,
                total_cost,
                holding_date
            FROM holdings 
            WHERE fund_code = %s 
              AND DATE(holding_date) <= %s
              AND DATE(updated_at) <= %s
            ORDER BY holding_date DESC, updated_at DESC
            LIMIT 1
            """
            cursor.execute(query, (fund_code, analysis_date, analysis_date))
            holding = cursor.fetchone()
            
            if not holding:
                self.logger.warning(f"   ⚠️ {fund_code} holdings表无数据")
                return {
                    'holding_shares': 0.0,
                    'market_value': 0.0,
                    'accumulated_profit': 0.0,
                    'total_return_rate': 0.0,
                    'avg_cost': 1.0000,
                    'total_cost': 0.0,
                    'holding_end_date': analysis_date
                }
            
            # 添加调试日志
            self.logger.info(f"   📊 {fund_code} holdings数据: 份额={holding.get('holding_shares')}, 持仓日期={holding.get('holding_date')}")
            
            return {
                'holding_shares': float(holding['holding_shares'] or 0),
                'market_value': float(holding['market_value'] or 0),
                'accumulated_profit': float(holding['accumulated_earnings'] or 0),
                'total_return_rate': float(holding['total_return_rate'] or 0),
                'avg_cost': float(holding['avg_cost'] or 1.0000),
                'total_cost': float(holding['total_cost'] or 0),
                'holding_end_date': holding.get('holding_date', analysis_date)  # 使用holding_date作为持仓日期
            }
            
        except Exception as e:
            self.logger.error(f"获取持仓数据失败 {fund_code}: {e}")
            return {
                'holding_shares': 0.0,
                'market_value': 0.0,
                'accumulated_profit': 0.0,
                'total_return_rate': 0.0,
                'avg_cost': 1.0000,
                'total_cost': 0.0,
                'holding_end_date': analysis_date
            }

    def _calculate_estimated_values(self, nav_data: Dict, holding_data: Dict, 
                                  fund_code: str, analysis_date: date) -> Dict[str, Any]:
        """
        计算市值和收益数据 - 与原始脚本完全一致
        
        数据获取策略：
        1. 净值数据：优先使用fund_nav_data（最新、准确）
        2. 持仓数据：从holdings获取（真实持仓）
        3. 市值计算：最新净值 × 持仓份额
        4. 收益数据：从holdings获取（真实收益）
        """
        try:
            self.logger.info(f"🔍 {fund_code} 开始计算估算值")
            
            # 净值数据：优先使用fund_nav_data（最新）
            unit_nav = nav_data.get('unit_nav', 0) or holding_data.get('unit_nav', 0)
            accumulated_nav = nav_data.get('accumulated_nav', 0)
            daily_return = nav_data.get('daily_return', 0) or holding_data.get('daily_return', 0)
            latest_nav_date = nav_data.get('latest_nav_date') or holding_data.get('holding_end_date')
            
            self.logger.info(f"🔍 {fund_code} 净值数据: unit_nav={unit_nav}, daily_return={daily_return}")
            
            # 持仓数据：从holdings获取
            holding_shares = holding_data.get('holding_shares', 0)
            holdings_market_value = holding_data.get('market_value', 0)  # holdings表中的市值
            accumulated_profit = holding_data.get('accumulated_profit', 0)
            total_return_rate = holding_data.get('total_return_rate', 0)
            holding_end_date = holding_data.get('holding_end_date')
            
            self.logger.info(f"🔍 {fund_code} 持仓数据: holding_shares={holding_shares}, market_value={holdings_market_value}")
            
            # 计算当前市值：使用最新净值 × 持仓份额
            current_market_value = holding_shares * unit_nav if holding_shares > 0 and unit_nav > 0 else holdings_market_value
            
            self.logger.info(f"🔍 {fund_code} 当前市值计算: {holding_shares} × {unit_nav} = {current_market_value}")
            
            # 计算今日收益变化（基于日涨跌幅和当前市值）
            today_change = current_market_value * (daily_return / 100) if current_market_value > 0 and daily_return != 0 else 0
            
            self.logger.info(f"🔍 {fund_code} today_change计算: {current_market_value} × ({daily_return}/100) = {today_change}")
            
            # 计算累计收益：当日收益 + 昨日累计收益（混合策略）
            self.logger.info(f"🔍 {fund_code} 开始计算累计收益")
            accumulated_profit = self._calculate_accumulated_profit(fund_code, analysis_date, today_change)
            self.logger.info(f"🔍 {fund_code} 累计收益计算完成: {accumulated_profit}")
            
            total_return_rate = holding_data.get('total_return_rate', 0)
            
            self.logger.info(f"📊 {fund_code} 数据整合:")
            self.logger.info(f"   持仓份额: {holding_shares}")
            self.logger.info(f"   最新净值: {unit_nav} (来源: fund_nav_data)")
            self.logger.info(f"   累计净值: {accumulated_nav}")
            self.logger.info(f"   当前市值: {current_market_value} (计算值)")
            self.logger.info(f"   holdings市值: {holdings_market_value} (holdings表)")
            self.logger.info(f"   累计收益: {accumulated_profit} (公式: 当日收益 + 昨日累计收益)")
            self.logger.info(f"   收益率: {total_return_rate}%")
            self.logger.info(f"   日涨跌幅: {daily_return}%")
            self.logger.info(f"   今日收益变化: {today_change}")
            
            return {
                'unit_nav': round(unit_nav, 4),
                'accumulated_nav': round(accumulated_nav, 4),
                'holding_shares': round(holding_shares, 2),
                'market_value': round(current_market_value, 2),
                'accumulated_profit': round(accumulated_profit, 2),
                'today_change': round(today_change, 2),
                'total_return_rate': round(total_return_rate, 2),
                'daily_return': round(daily_return, 2),
                'latest_nav_date': latest_nav_date,
                'holding_end_date': holding_end_date
            }
            
        except Exception as e:
            self.logger.error(f"处理 {fund_code} 数据失败: {e}")
            return {
                'unit_nav': 0,
                'accumulated_nav': 0,
                'holding_shares': 0,
                'market_value': 0,
                'accumulated_profit': 0,
                'today_change': 0,
                'total_return_rate': 0,
                'daily_return': 0,
                'latest_nav_date': None,
                'holding_end_date': None
            }

    def _get_performance_data(self, cursor, fund_code: str) -> Dict[str, Any]:
        """获取历史表现数据"""
        try:
            query = """
            SELECT return_1w, hs300_return_1w, avg_return_1w
            FROM fund_historical_performance 
            WHERE fund_code = %s 
            ORDER BY collection_time DESC 
            LIMIT 1
            """
            cursor.execute(query, (fund_code,))
            performance = cursor.fetchone()
            
            if performance:
                return {
                    'return_1w': float(performance['return_1w'] or 0),
                    'hs300_return_1w': float(performance['hs300_return_1w'] or 0),
                    'avg_return_1w': float(performance['avg_return_1w'] or 0)
                }
            else:
                return {
                    'return_1w': 0,
                    'hs300_return_1w': 0,
                    'avg_return_1w': 0
                }
                
        except Exception as e:
            self.logger.error(f"获取历史表现失败 {fund_code}: {e}")
            return {
                'return_1w': 0,
                'hs300_return_1w': 0,
                'avg_return_1w': 0
            }

    def _preload_yida_records(self, record_ids: List[str]) -> None:
        """预加载宜搭记录到缓存"""
        try:
            access_token = self.oauth_client.get_access_token()
            if not access_token:
                self.logger.error("无法获取access_token")
                return
                
            self.logger.info(f"预加载 {len(record_ids)} 条记录的宜搭状态")
            
            # 批量查询宜搭记录
            for record_id in record_ids:
                url = "https://api.dingtalk.com/v1.0/yida/forms/instances/search"
                
                headers = {
                    "Content-Type": "application/json",
                    "x-acs-dingtalk-access-token": access_token
                }
                
                search_condition = {
                    "textField_mbmwduwh": record_id
                }
                
                payload = {
                    "appType": self.config['yida']['app_type'],
                    "systemToken": self.config['yida']['system_token'],
                    "userId": self.config['yida']['user_id'],
                    "formUuid": self.form_uuid,
                    "pageSize": 1,
                    "currentPage": 1,
                    "searchFieldJson": json.dumps(search_condition)
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        data_list = result.get('data', [])
                        if len(data_list) > 0:
                            found_record = None
                            for record in data_list:
                                form_data = record.get('formData', {})
                                if form_data.get('textField_mbmwduwh') == record_id:
                                    found_record = record
                                    break
                            
                            if found_record:
                                self.existing_record_cache[record_id] = found_record
                                self.logger.info(f"记录 {record_id} 存在")
                            else:
                                self.existing_record_cache[record_id] = None
                        else:
                            self.existing_record_cache[record_id] = None
                    except json.JSONDecodeError as e:
                        self.logger.error(f"JSON解析失败: {e}")
                        self.existing_record_cache[record_id] = None
                else:
                    self.logger.error(f"API请求失败: {response.status_code}")
                    self.existing_record_cache[record_id] = None
                    
            self.logger.info(f"缓存加载完成，存在记录: {sum(1 for v in self.existing_record_cache.values() if v is not None)} 条")
            
        except Exception as e:
            self.logger.error(f"预加载宜搭记录失败: {e}")

    def calculate_technical_indicators(self, fund_code: str, analysis_date: date) -> Dict[str, Any]:
        """计算技术指标"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    # 从fund_nav_data获取历史净值数据用于计算
                    sql = """
                    SELECT nav_date, unit_nav, total_nav as accumulated_nav, daily_return
                    FROM fund_nav_data 
                    WHERE fund_code = %s 
                        AND nav_date <= %s
                    ORDER BY nav_date DESC 
                    LIMIT 30
                    """
                    
                    cursor.execute(sql, (fund_code, analysis_date))
                    nav_data = cursor.fetchall()
                    
                    if len(nav_data) < 3:
                        self.logger.warning(f"基金 {fund_code} 净值数据不足，无法计算技术指标")
                        return {
                            'volatility_7d': 0,
                            'avg_return_7d': 0,
                            'consecutive_days': 0,
                            'vs_hs300': 0,
                            'max_drawdown': 0,
                            'trend_direction': '未知',
                            'risk_level': '未知',
                            'drawdown_status': '正常',
                            'today_change': 0.0
                        }
                    
                    # 转换为DataFrame便于计算
                    df = pd.DataFrame(nav_data)
                    df['daily_return'] = df['daily_return'].astype(float)
                    df = df.sort_values('nav_date')
                    
                    # 计算7日波动率（daily_return已经是百分比格式，直接计算标准差）
                    recent_7d = df.tail(7)
                    volatility_7d = recent_7d['daily_return'].std() if len(recent_7d) > 1 else 0
                    
                    # 计算7日平均收益
                    avg_return_7d = recent_7d['daily_return'].mean() if len(recent_7d) > 0 else 0
                    
                    # 计算连续上涨/下跌天数
                    consecutive_days = self._calculate_consecutive_days(df['daily_return'].tolist())
                    
                    # 计算最大回撤
                    max_drawdown = self._calculate_max_drawdown(df['unit_nav'].tolist())
                    
                    # V5版本：使用专业趋势判断
                    trend_direction = self._determine_trend_v5(fund_code, analysis_date)
                    
                    # 评估风险等级（基于波动率和最大回撤）
                    if volatility_7d > 20 or max_drawdown > 15:
                        risk_level = '高风险'
                    elif volatility_7d > 15 or max_drawdown > 10:
                        risk_level = '中风险'
                    else:
                        risk_level = '低风险'
                    
                    # 计算相对沪深300表现（暂时设为0，后续可扩展）
                    vs_hs300 = 0.0
                    
                    # 判断回撤状态
                    drawdown_status = self._assess_drawdown_status_v5(max_drawdown)
                    
                    # 计算今日收益变化 - 使用原始脚本的算法
                    today_change = self._calculate_today_change_in_technical_indicators(fund_code, analysis_date, nav_data)
                    
                    return {
                        'volatility_7d': volatility_7d,
                        'avg_return_7d': avg_return_7d,
                        'consecutive_days': consecutive_days,
                        'vs_hs300': vs_hs300,
                        'max_drawdown': max_drawdown,
                        'trend_direction': trend_direction,
                        'risk_level': risk_level,
                        'drawdown_status': drawdown_status,
                        'today_change': today_change
                    }
                    
        except Exception as e:
            self.logger.error(f"计算技术指标失败: {e}")
            return {
                'volatility_7d': 0,
                'avg_return_7d': 0,
                'consecutive_days': 0,
                'vs_hs300': 0,
                'max_drawdown': 0,
                'trend_direction': '未知',
                'risk_level': '未知',
                'drawdown_status': '正常',
                'today_change': 0.0
            }

    def _calculate_consecutive_days(self, returns: List[float]) -> int:
        """计算连续上涨/下跌天数"""
        if not returns or len(returns) < 2:
            return 0
        
        # 从最新的数据开始计算
        consecutive = 0
        last_direction = None
        
        # 取最近10天的数据
        recent_returns = returns[-10:] if len(returns) >= 10 else returns
        
        for daily_return in reversed(recent_returns):
            if daily_return > 0:
                current_direction = 'up'
            elif daily_return < 0:
                current_direction = 'down'
            else:
                break  # 遇到0收益率，停止计算
            
            if last_direction is None:
                last_direction = current_direction
                consecutive = 1
            elif last_direction == current_direction:
                consecutive += 1
            else:
                break
        
        # 返回连续天数，下跌为负数
        return consecutive if last_direction == 'up' else -consecutive

    def _calculate_max_drawdown(self, nav_values: List[float]) -> float:
        """计算最大回撤"""
        if not nav_values or len(nav_values) < 2:
            return 0.0
        
        max_drawdown = 0.0
        peak = nav_values[0]
        
        for nav in nav_values:
            if nav > peak:
                peak = nav
            else:
                drawdown = (peak - nav) / peak * 100
                max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown

    def _determine_trend_v5(self, fund_code: str, analysis_date: date) -> str:
        """V5专业趋势判断 - 中期趋势+当日调整方案"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    # 获取最近5天的净值数据
                    sql = """
                    SELECT nav_date, daily_return
                    FROM fund_nav_data 
                    WHERE fund_code = %s 
                        AND nav_date <= %s
                    ORDER BY nav_date DESC 
                    LIMIT 5
                    """
                    
                    cursor.execute(sql, (fund_code, analysis_date))
                    nav_data = cursor.fetchall()
                    
                    if len(nav_data) < 2:
                        self.logger.warning(f"   ⚠️ {fund_code} 净值数据不足({len(nav_data)}天)，无法判断趋势")
                        return '数据不足'
                    
                    # 提取收益率数据
                    returns = [float(row['daily_return'] or 0) for row in nav_data]
                    today_return = returns[0]  # 当日收益率
                    
                    # 计算5天累计收益率
                    cumulative_return = sum(returns)
                    
                    # 计算上涨天数占比
                    positive_days = sum(1 for r in returns if r > 0)
                    trend_strength = positive_days / len(returns)
                    
                    # 详细日志输出
                    self.logger.info(f"   📊 {fund_code} 趋势分析数据:")
                    self.logger.info(f"      🔢 最近5天收益率: {[f'{r:+.2f}%' for r in returns]}")
                    self.logger.info(f"      📈 5天累计收益: {cumulative_return:+.2f}%")
                    self.logger.info(f"      ⬆️ 上涨天数: {positive_days}/5天 ({trend_strength:.1%})")
                    self.logger.info(f"      📅 当日收益率: {today_return:+.2f}%")
                    
                    # 1. 判断中期趋势（基于5天累计收益率）
                    if cumulative_return >= 5:
                        mid_term_trend = "强势上涨"
                    elif cumulative_return >= 1:
                        mid_term_trend = "普通上涨"
                    elif cumulative_return <= -5:
                        mid_term_trend = "强势下跌"
                    elif cumulative_return <= -1:
                        mid_term_trend = "普通下跌"
                    else:
                        mid_term_trend = "震荡"
                    
                    # 2. 判断当日趋势强度
                    if today_return >= 1:
                        today_strength = "大涨"
                    elif today_return >= 0.1:
                        today_strength = "小涨"
                    elif today_return <= -1:
                        today_strength = "大跌"
                    elif today_return <= -0.1:
                        today_strength = "小跌"
                    else:
                        today_strength = "平盘"
                    
                    self.logger.info(f"      🎯 中期趋势: {mid_term_trend}")
                    self.logger.info(f"      🎯 当日强度: {today_strength}")
                    
                    # 3. V5专业组合判断
                    final_trend = ""
                    if mid_term_trend in ["强势上涨", "普通上涨"]:
                        if today_strength in ["小涨", "大涨"]:
                            final_trend = mid_term_trend  # 显示中期趋势
                        elif today_strength == "平盘":
                            final_trend = mid_term_trend
                        elif today_strength == "小跌":
                            final_trend = "小幅回调"  # 专业术语，避免"上涨"字样
                        else:  # 大跌
                            final_trend = "深度回调"
                    elif mid_term_trend in ["强势下跌", "普通下跌"]:
                        if today_strength in ["小跌", "大跌"]:
                            final_trend = mid_term_trend
                        elif today_strength == "平盘":
                            final_trend = mid_term_trend
                        elif today_strength == "小涨":
                            final_trend = "弱势反弹"
                        else:  # 大涨
                            final_trend = "强势反弹"
                    else:  # 震荡
                        if today_strength == "大涨":
                            final_trend = "大涨"
                        elif today_strength == "小涨":
                            final_trend = "小涨"
                        elif today_strength == "平盘":
                            final_trend = "震荡"
                        elif today_strength == "小跌":
                            final_trend = "小跌"
                        else:  # 大跌
                            final_trend = "大跌"
                    
                    self.logger.info(f"      ✅ V5最终判断: {final_trend}")
                    return final_trend
                            
        except Exception as e:
            self.logger.error(f"V5趋势判断失败 {fund_code}: {e}")
            return '计算失败'

    def _assess_risk_level(self, volatility: float, max_drawdown: float) -> str:
        """评估风险等级"""
        try:
            # 综合波动率和最大回撤评估风险
            if volatility > 15 or max_drawdown > 20:
                return '高风险'
            elif volatility > 8 or max_drawdown > 10:
                return '中风险'
            else:
                return '低风险'
        except Exception as e:
            self.logger.error(f"评估风险等级失败: {e}")
            return '未知'

    def _assess_drawdown_status_v5(self, max_drawdown: float) -> str:
        """V5专业回撤状态评估"""
        try:
            if max_drawdown > 30:
                return '极度回撤'
            elif max_drawdown > 20:
                return '严重回撤'
            elif max_drawdown > 10:
                return '中度回撤'
            elif max_drawdown > 5:
                return '轻微回撤'
            else:
                return '正常状态'
        except Exception as e:
            self.logger.error(f"评估回撤状态失败: {e}")
            return '正常状态'

    def _generate_weekly_report_code(self, fund_code: str, analysis_date: date) -> str:
        """生成周报代码"""
        try:
            # 获取年份和周数
            year = analysis_date.year
            week_number = analysis_date.isocalendar()[1]
            
            # 生成格式：基金代码-年-周 (159300-2025-26)
            weekly_code = f"{fund_code}-{year}-{week_number}"
            
            return weekly_code
            
        except Exception as e:
            self.logger.error(f"生成周报代码失败: {e}")
            return f"{fund_code}-ERROR"

    def _get_fund_config_and_returns(self, fund_code: str) -> Dict[str, Any]:
        """获取基金配置参数和近期收益率"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    # 获取基金配置参数
                    config_sql = """
                    SELECT 
                        drawdown_attention,
                        drawdown_warning,
                        credit_spread_warning,
                        attention_threshold,
                        warning_threshold,
                        attention_consecutive_days,
                        warning_consecutive_days,
                        volatility_threshold
                    FROM fund_basic_info 
                    WHERE fund_code = %s
                    """
                    cursor.execute(config_sql, (fund_code,))
                    config_result = cursor.fetchone()
                    
                    self.logger.info(f"   📊 {fund_code} 基金配置查询结果: {config_result}")
                    
                    # 计算近3月和近1年收益率
                    returns_sql = """
                    SELECT 
                        nav_date,
                        unit_nav
                    FROM fund_nav_data 
                    WHERE fund_code = %s 
                        AND nav_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
                    ORDER BY nav_date DESC
                    """
                    cursor.execute(returns_sql, (fund_code,))
                    nav_history = cursor.fetchall()
                    
                    self.logger.info(f"   📊 {fund_code} 获取到{len(nav_history)}条历史净值数据")
                    
                    # 计算收益率
                    return_3m = 0.0
                    return_1y = 0.0
                    
                    if nav_history:
                        current_nav = float(nav_history[0]['unit_nav'] or 0)
                        self.logger.info(f"   📊 {fund_code} 当前净值: {current_nav}")
                        
                        # 查找3个月前的净值（更灵活的匹配）
                        nav_3m_found = False
                        for nav_record in nav_history:
                            nav_date = nav_record['nav_date']
                            if isinstance(nav_date, str):
                                nav_date = datetime.strptime(nav_date, '%Y-%m-%d').date()
                            
                            days_ago = (date.today() - nav_date).days
                            
                            # 3个月前（约90天，范围扩大到80-100天）
                            if 80 <= days_ago <= 100:
                                nav_3m = float(nav_record['unit_nav'] or 0)
                                if nav_3m > 0:
                                    return_3m = ((current_nav - nav_3m) / nav_3m) * 100
                                    nav_3m_found = True
                                self.logger.info(f"   📊 {fund_code} 3个月前净值({days_ago}天前): {nav_3m}, 收益率: {return_3m:.2f}%")
                                break
                        
                        if not nav_3m_found:
                            self.logger.warning(f"   ⚠️ {fund_code} 未找到3个月前的净值数据")
                        
                        # 查找1年前的净值（更灵活的匹配）
                        nav_1y_found = False
                        for nav_record in nav_history:
                            nav_date = nav_record['nav_date']
                            if isinstance(nav_date, str):
                                nav_date = datetime.strptime(nav_date, '%Y-%m-%d').date()
                            
                            days_ago = (date.today() - nav_date).days
                            
                            # 1年前（约365天，范围扩大到350-380天）
                            if 350 <= days_ago <= 380:
                                nav_1y = float(nav_record['unit_nav'] or 0)
                                if nav_1y > 0:
                                    return_1y = ((current_nav - nav_1y) / nav_1y) * 100
                                    nav_1y_found = True
                                self.logger.info(f"   📊 {fund_code} 1年前净值({days_ago}天前): {nav_1y}, 收益率: {return_1y:.2f}%")
                                break
                        
                        if not nav_1y_found:
                            self.logger.warning(f"   ⚠️ {fund_code} 未找到1年前的净值数据")
                    
                    self.logger.info(f"   📊 {fund_code} 最终收益率: 3个月={return_3m:.2f}%, 1年={return_1y:.2f}%")
                    
                    # 组合结果
                    result = {
                        'return_3m': return_3m,
                        'return_1y': return_1y
                    }
                    
                    # 添加配置参数（直接使用数据库中的真实值，不使用默认值）
                    if config_result:
                        result.update({
                            'drawdown_attention': float(config_result.get('drawdown_attention')) if config_result.get('drawdown_attention') is not None else None,
                            'drawdown_alert': float(config_result.get('drawdown_warning')) if config_result.get('drawdown_warning') is not None else None,
                            'credit_spread_alert': float(config_result.get('credit_spread_warning')) if config_result.get('credit_spread_warning') is not None else None,
                            'attention_return_threshold': float(config_result.get('attention_threshold')) if config_result.get('attention_threshold') is not None else None,
                            'alert_return_threshold': float(config_result.get('warning_threshold')) if config_result.get('warning_threshold') is not None else None,
                            'attention_consecutive_days': int(config_result.get('attention_consecutive_days')) if config_result.get('attention_consecutive_days') is not None else None,
                            'alert_consecutive_days': int(config_result.get('warning_consecutive_days')) if config_result.get('warning_consecutive_days') is not None else None,
                            'volatility_attention_threshold': float(config_result.get('volatility_threshold')) if config_result.get('volatility_threshold') is not None else None
                        })
                        self.logger.info(f"   📊 {fund_code} 配置参数已添加（使用数据库真实值，包括None值）")
                    else:
                        # 如果没有配置数据，所有参数设为None
                        result.update({
                            'drawdown_attention': None,
                            'drawdown_alert': None,
                            'credit_spread_alert': None,
                            'attention_return_threshold': None,
                            'alert_return_threshold': None,
                            'attention_consecutive_days': None,
                            'alert_consecutive_days': None,
                            'volatility_attention_threshold': None
                        })
                        self.logger.warning(f"   ⚠️ {fund_code} fund_basic_info表无配置数据，所有参数设为None")
                    
                    return result
                    
        except Exception as e:
            self.logger.error(f"获取基金配置和收益率失败 {fund_code}: {e}")
            return {
                'return_3m': 0.0,
                'return_1y': 0.0,
                'drawdown_attention': 0.0,
                'drawdown_alert': 0.0,
                'credit_spread_alert': 0.0,
                'attention_return_threshold': 0.0,
                'alert_return_threshold': 0.0,
                'attention_consecutive_days': 0,
                'alert_consecutive_days': 0,
                'volatility_attention_threshold': 0.0
            }

    def generate_monitoring_record(self, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成监测记录"""
        try:
            fund_code = base_data['fund_code']
            analysis_date = base_data['analysis_date']
            
            # 计算技术指标
            technical_indicators = self.calculate_technical_indicators(fund_code, analysis_date)
            
            # 获取基金配置参数和近期收益率
            fund_config = self._get_fund_config_and_returns(fund_code)
            
            # 生成记录ID (格式: 基金代码_YYYY-MM-DD)
            record_id = f"{fund_code}_{analysis_date.strftime('%Y-%m-%d')}"
            
            # 生成周报代码
            weekly_report_code = self._generate_weekly_report_code(fund_code, analysis_date)
            
            # 合并基础数据和技术指标
            record = {
                'record_id': record_id,
                'weekly_report_code': weekly_report_code,
                **base_data,
                **technical_indicators,
                **fund_config  # 添加基金配置参数和近期收益率
            }
            
            # V5版本：生成专业预警状态
            alert_data = self._generate_alert_status_v5(record)
            record.update(alert_data)
            
            # V5版本：生成专业建议操作
            suggestion_data = self._generate_suggestions_v5(record)
            record.update(suggestion_data)
            
            return record
            
        except Exception as e:
            self.logger.error(f"生成监测记录失败: {e}")
            return base_data

    def _generate_alert_status_v5(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """V5专业预警状态生成 - 基于fund_basic_info表的个性化阈值"""
        try:
            # 获取当前指标值
            volatility = record.get('volatility_7d', 0) or 0
            consecutive_days = abs(record.get('consecutive_days', 0) or 0)
            max_drawdown = record.get('max_drawdown', 0) or 0
            today_change = record.get('today_change', 0) or 0
            daily_return = record.get('daily_return', 0) or 0
            
            # 获取个性化阈值（从fund_basic_info表获取）
            volatility_threshold = record.get('volatility_attention_threshold') or 25
            attention_threshold = record.get('attention_return_threshold') or -3
            warning_threshold = record.get('alert_return_threshold') or -5
            attention_consecutive = record.get('attention_consecutive_days') or 3
            warning_consecutive = record.get('alert_consecutive_days') or 5
            drawdown_attention = record.get('drawdown_attention') or 10
            drawdown_warning = record.get('drawdown_alert') or 20
            
            alert_status = '正常'
            alert_enabled = '否'
            
            # V5专业预警逻辑
            # 1. 预警级别（最高优先级）
            if (daily_return <= warning_threshold or 
                consecutive_days >= warning_consecutive or 
                max_drawdown >= drawdown_warning or
                volatility > volatility_threshold * 1.5):
                alert_status = '预警'
                alert_enabled = '是'
            
            # 2. 关注级别（中等优先级）
            elif (daily_return <= attention_threshold or 
                  consecutive_days >= attention_consecutive or 
                  max_drawdown >= drawdown_attention or
                  volatility > volatility_threshold):
                alert_status = '关注'
                alert_enabled = '是'
            
            # 3. 正常级别（默认）
            else:
                alert_status = '正常'
                alert_enabled = '否'
            
            return {
                'alert_status': alert_status,
                'alert_enabled': alert_enabled
            }
            
        except Exception as e:
            self.logger.error(f"生成V5预警状态失败: {e}")
            return {
                'alert_status': '正常',
                'alert_enabled': '否'
            }

    def _generate_suggestions_v5(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """V5专业建议操作生成"""
        try:
            trend_direction = record.get('trend_direction', '未知')
            risk_level = record.get('risk_level', '未知')
            alert_status = record.get('alert_status', '正常')
            drawdown_status = record.get('drawdown_status', '正常状态')
            total_return_rate = record.get('total_return_rate', 0)
            volatility_7d = record.get('volatility_7d', 0)
            max_drawdown = record.get('max_drawdown', 0)
            
            # V5专业建议逻辑
            
            # 1. 极端风险控制（立即减仓）
            if (alert_status == '预警' or 
                drawdown_status in ['极度回撤', '严重回撤'] or
                max_drawdown > 25):
                suggested_action = '减仓'
                suggested_position_ratio = 20
                
            # 2. 风险控制（谨慎减仓）
            elif (alert_status == '关注' or 
                  drawdown_status == '中度回撤' or
                  trend_direction in ['强势下跌', '普通下跌']):
                suggested_action = '减仓'
                suggested_position_ratio = 40
                
            # 3. 积极加仓（优质机会）
            elif (trend_direction in ['强势上涨', '普通上涨'] and 
                  risk_level == '低风险' and 
                  volatility_7d < 8 and
                  total_return_rate > 5):
                suggested_action = '加仓'
                suggested_position_ratio = 85
                
            # 4. 适度加仓（良好机会）
            elif (trend_direction in ['强势上涨', '普通上涨', '强势反弹'] and 
                  risk_level in ['低风险', '中风险'] and
                  total_return_rate > 0):
                suggested_action = '加仓'
                suggested_position_ratio = 75
                
            # 5. 持有观望（回调中的上涨趋势）
            elif trend_direction in ['小幅回调', '深度回调']:
                suggested_action = '持有'
                suggested_position_ratio = 60
                
            # 6. 持有观望（震荡状态）
            elif trend_direction in ['震荡', '弱势反弹']:
                suggested_action = '持有'
                suggested_position_ratio = 55
                
            # 7. 谨慎持有（下跌趋势但损失不大）
            elif (trend_direction in ['弱势下跌', '小跌'] and 
                  total_return_rate > -10):
                suggested_action = '持有'
                suggested_position_ratio = 45
                
            # 8. 默认持有
            else:
                suggested_action = '持有'
                suggested_position_ratio = 50
            
            return {
                'suggested_position_ratio': suggested_position_ratio,
                'suggested_action': suggested_action
            }
            
        except Exception as e:
            self.logger.error(f"生成V5建议失败: {e}")
            return {
                'suggested_position_ratio': 50,
                'suggested_action': '持有'
            }

    def save_to_database(self, record: Dict[str, Any]) -> bool:
        """保存到数据库"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor() as cursor:
                    
                    # 检查记录是否已存在
                    check_sql = "SELECT COUNT(*) FROM daily_monitoring WHERE fund_code = %s AND analysis_date = %s"
                    cursor.execute(check_sql, (record['fund_code'], record['analysis_date']))
                    exists = cursor.fetchone()[0] > 0
                    
                    # 安全转换函数
                    def safe_decimal(value, default=None):
                        try:
                            if value is None or value == '':
                                return default
                            return Decimal(str(value)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
                        except:
                            return default
                    
                    def safe_int(value, default=0):
                        try:
                            return int(float(value)) if value is not None else default
                        except:
                            return default
                    
                    def safe_str(value, default=''):
                        try:
                            return str(value) if value is not None else default
                        except:
                            return default
                    
                    if exists:
                        # 更新记录
                        update_sql = """
                        UPDATE daily_monitoring SET
                            fund_name = %s, fund_type = %s, holder = %s,
                            unit_nav = %s, accumulated_nav = %s, daily_return = %s, latest_nav_date = %s,
                            holding_shares = %s, market_value = %s, accumulated_profit = %s,
                            total_return_rate = %s, return_1w = %s, hs300_return_1w = %s, avg_return_1w = %s,
                            holding_end_date = %s, today_change = %s, vs_hs300 = %s, suggested_position_ratio = %s,
                            volatility_7d = %s, consecutive_days = %s, avg_return_7d = %s, alert_enabled = %s,
                            alert_status = %s, risk_level = %s, trend_direction = %s, suggested_action = %s,
                            max_drawdown = %s, drawdown_status = %s, weekly_report_code = %s,
                            drawdown_attention = %s, drawdown_alert = %s, credit_spread_alert = %s,
                            attention_return_threshold = %s, alert_return_threshold = %s,
                            attention_consecutive_days = %s, alert_consecutive_days = %s,
                            volatility_attention_threshold = %s, ai_analysis_instruction = %s,
                            ai_operation_logic = %s, updated_at = NOW()
                        WHERE fund_code = %s AND analysis_date = %s
                        """
                        
                        cursor.execute(update_sql, (
                            safe_str(record.get('fund_name')),
                            safe_str(record.get('fund_type')),
                            safe_str(record.get('holder')),
                            safe_decimal(record.get('unit_nav')),
                            safe_decimal(record.get('accumulated_nav')),
                            safe_decimal(record.get('daily_return')),
                            record.get('latest_nav_date'),
                            safe_decimal(record.get('holding_shares')),
                            safe_decimal(record.get('market_value')),
                            safe_decimal(record.get('accumulated_profit')),
                            safe_decimal(record.get('total_return_rate')),
                            safe_decimal(record.get('return_1w')),
                            safe_decimal(record.get('hs300_return_1w')),
                            safe_decimal(record.get('avg_return_1w')),
                            record.get('holding_end_date'),
                            safe_decimal(record.get('today_change')),
                            safe_decimal(record.get('vs_hs300')),
                            safe_int(record.get('suggested_position_ratio')),
                            safe_decimal(record.get('volatility_7d')),
                            safe_int(record.get('consecutive_days')),
                            safe_decimal(record.get('avg_return_7d')),
                            safe_str(record.get('alert_enabled')),
                            safe_str(record.get('alert_status')),
                            safe_str(record.get('risk_level')),
                            safe_str(record.get('trend_direction')),
                            safe_str(record.get('suggested_action')),
                            safe_decimal(record.get('max_drawdown')),
                            safe_str(record.get('drawdown_status')),
                            safe_str(record.get('weekly_report_code')),
                            safe_decimal(record.get('drawdown_attention')),
                            safe_decimal(record.get('drawdown_alert')),  # 使用新字段名
                            safe_decimal(record.get('credit_spread_alert')),  # 使用新字段名
                            safe_decimal(record.get('attention_return_threshold')),  # 使用新字段名
                            safe_decimal(record.get('alert_return_threshold')),  # 使用新字段名
                            safe_int(record.get('attention_consecutive_days')),
                            safe_int(record.get('alert_consecutive_days')),  # 使用新字段名
                            safe_decimal(record.get('volatility_attention_threshold')),  # 使用新字段名
                            safe_str(record.get('ai_analysis_instruction')),
                            safe_str(record.get('ai_operation_logic')),
                            record['fund_code'],
                            record['analysis_date']
                        ))
                    else:
                        # 插入新记录
                        insert_sql = """
                        INSERT INTO daily_monitoring (
                            fund_code, fund_name, fund_type, analysis_date, record_id,
                            unit_nav, accumulated_nav, daily_return, latest_nav_date,
                            holding_shares, market_value, accumulated_profit, total_return_rate, 
                            today_change, holding_end_date, holder,
                            return_1w, hs300_return_1w, avg_return_1w, vs_hs300, volatility_7d,
                            consecutive_days, avg_return_7d, max_drawdown, suggested_position_ratio,
                            risk_level, trend_direction, suggested_action, alert_enabled, alert_status,
                            drawdown_status, weekly_report_code, drawdown_attention, drawdown_alert, credit_spread_alert,
                            ai_analysis_status, ai_recommendation, ai_analysis_time, ai_rating,
                            ai_confidence, ai_action_advice, ai_analysis_result, ai_decision_basis,
                            attention_return_threshold, alert_return_threshold, attention_consecutive_days,
                            alert_consecutive_days, volatility_attention_threshold, ai_analysis_instruction,
                            ai_operation_logic, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                        )
                        """
                        
                        cursor.execute(insert_sql, (
                            safe_str(record.get('fund_code')), safe_str(record.get('fund_name')), safe_str(record.get('fund_type')), 
                            record.get('analysis_date'), safe_str(record.get('record_id')),
                            safe_decimal(record.get('unit_nav')), safe_decimal(record.get('accumulated_nav')), 
                            safe_decimal(record.get('daily_return')), record.get('latest_nav_date'),
                            safe_decimal(record.get('holding_shares')), safe_decimal(record.get('market_value')), 
                            safe_decimal(record.get('accumulated_profit')), safe_decimal(record.get('total_return_rate')),
                            safe_decimal(record.get('today_change')), record.get('holding_end_date'), safe_str(record.get('holder'), 'B'),
                            safe_decimal(record.get('return_1w')), safe_decimal(record.get('hs300_return_1w')), 
                            safe_decimal(record.get('avg_return_1w')), safe_decimal(record.get('vs_hs300')), safe_decimal(record.get('volatility_7d')),
                            safe_int(record.get('consecutive_days')), safe_decimal(record.get('avg_return_7d')), 
                            safe_decimal(record.get('max_drawdown')), safe_int(record.get('suggested_position_ratio'), 60),
                            safe_str(record.get('risk_level'), '中等风险'), safe_str(record.get('trend_direction'), '震荡'), 
                            safe_str(record.get('suggested_action'), '持有'), safe_str(record.get('alert_enabled'), '否'), safe_str(record.get('alert_status'), '正常'),
                            safe_str(record.get('drawdown_status'), '正常'), safe_str(record.get('weekly_report_code')), 
                            safe_decimal(record.get('drawdown_attention'), 12.0), safe_decimal(record.get('drawdown_alert'), 15.0), safe_decimal(record.get('credit_spread_alert'), 0),
                            safe_str(record.get('ai_analysis_status'), '待分析'), safe_str(record.get('ai_recommendation')), 
                            record.get('ai_analysis_time'), safe_str(record.get('ai_rating')),
                            safe_decimal(record.get('ai_confidence'), 0.0), safe_str(record.get('ai_action_advice')), 
                            safe_str(record.get('ai_analysis_result')), safe_str(record.get('ai_decision_basis')),
                            safe_decimal(record.get('attention_return_threshold'), -5.0), safe_decimal(record.get('alert_return_threshold'), -10.0), 
                            safe_int(record.get('attention_consecutive_days'), 3),
                            safe_int(record.get('alert_consecutive_days'), 4), safe_decimal(record.get('volatility_attention_threshold'), 25.0), 
                            safe_str(record.get('ai_analysis_instruction')), safe_str(record.get('ai_operation_logic'))
                        ))
                    
                    return True
                    
        except Exception as e:
            self.logger.error(f"保存数据库失败: {e}")
            return False

    def sync_to_yida(self, record: Dict[str, Any]) -> bool:
        """同步到宜搭"""
        try:
            access_token = self.oauth_client.get_access_token()
            record_id = record.get('record_id')
            
            # 准备宜搭数据
            yida_data = {}
            for rds_field, yida_field_id in self.field_mapping.items():
                value = record.get(rds_field)
                if value is not None:
                    # 特殊处理日期字段
                    if 'date' in rds_field.lower() and isinstance(value, date):
                        # 转换为毫秒时间戳
                        if isinstance(value, date) and not isinstance(value, datetime):
                            # 如果是date对象，转换为datetime
                            value = datetime.combine(value, datetime.min.time())
                        yida_data[yida_field_id] = int(value.timestamp() * 1000)
                    # 特殊处理Decimal类型
                    elif isinstance(value, Decimal):
                        yida_data[yida_field_id] = float(value)
                    else:
                        yida_data[yida_field_id] = value
                        
                    # 特别记录today_change的传递情况
                    if rds_field == 'today_change':
                        self.logger.info(f"   📊 {record_id} today_change传递: {value} -> {yida_field_id}")
            
            # 检查today_change是否在yida_data中
            today_change_field_id = 'numberField_mbmwduwi'
            if today_change_field_id in yida_data:
                self.logger.info(f"   ✅ {record_id} today_change已添加到宜搭数据: {yida_data[today_change_field_id]}")
            else:
                self.logger.warning(f"   ⚠️ {record_id} today_change未添加到宜搭数据")
                # 检查原始记录中是否有today_change
                if 'today_change' in record:
                    self.logger.info(f"   📊 {record_id} 原始记录中today_change值: {record['today_change']}")
                else:
                    self.logger.warning(f"   ⚠️ {record_id} 原始记录中没有today_change字段")
            
            # 检查记录是否已存在
            existing_record = self.existing_record_cache.get(record_id)
            
            headers = {
                "Content-Type": "application/json",
                "x-acs-dingtalk-access-token": access_token
            }
            
            if existing_record:
                # 更新现有记录
                url = "https://api.dingtalk.com/v1.0/yida/forms/instances"
                payload = {
                    "appType": self.config['yida']['app_type'],
                    "systemToken": self.config['yida']['system_token'],
                    "userId": self.config['yida']['user_id'],
                    "formInstanceId": existing_record['formInstanceId'],
                    "updateFormDataJson": json.dumps(yida_data, ensure_ascii=False),
                    "language": "zh_CN",
                    "useLatestVersion": False
                }
                
                self.logger.info(f"   🔄 更新宜搭记录: {record_id}")
                response = requests.put(url, headers=headers, json=payload, timeout=30)
                operation = "更新"
            else:
                # 创建新记录
                url = "https://api.dingtalk.com/v1.0/yida/forms/instances"
                payload = {
                    "appType": self.config['yida']['app_type'],
                    "systemToken": self.config['yida']['system_token'],
                    "userId": self.config['yida']['user_id'],
                    "formUuid": self.form_uuid,
                    "formDataJson": json.dumps(yida_data, ensure_ascii=False)
                }
                
                self.logger.info(f"   ➕ 创建宜搭记录: {record_id}")
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                operation = "创建"
            
            if response.status_code in [200, 201]:
                result = response.json()
                if result.get('success', True):  # 有些API返回success字段
                    self.logger.info(f"   ✅ {operation}宜搭记录成功: {record_id}")
                    return True
                else:
                    self.logger.error(f"   ❌ {operation}宜搭记录失败: {result}")
                    return False
            else:
                self.logger.error(f"   ❌ {operation}宜搭记录HTTP错误: {response.status_code}")
                self.logger.error(f"   📄 响应内容: {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"宜搭同步异常: {e}")
            return False

    def is_market_closed(self, check_date: date) -> bool:
        """判断市场是否休市"""
        try:
            # 周末休市
            if check_date.weekday() >= 5:  # 5=周六, 6=周日
                return True
            
            # 这里可以添加节假日判断逻辑
            # 暂时只判断周末
            return False
            
        except Exception as e:
            self.logger.error(f"判断休市状态失败: {e}")
            return False

    def _get_daily_return(self, fund_code: str, analysis_date: date) -> Optional[float]:
        """从daily_returns表获取日收益率（备用方法）"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    sql = """
                    SELECT daily_return
                    FROM daily_returns 
                    WHERE fund_code = %s AND calculation_date = %s
                    """
                    cursor.execute(sql, (fund_code, analysis_date))
                    result = cursor.fetchone()
                    
                    if result:
                        return float(result['daily_return'])
                    else:
                        return None
                        
        except Exception as e:
            self.logger.error(f"获取日收益率失败: {e}")
            return None

    def _calculate_today_change(self, fund_code: str, analysis_date: date) -> float:
        """计算今日收益变化：持有份额 × (当日净值 - 前一日净值)"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    # 获取持有份额
                    holding_data = self._get_latest_holding_data(cursor, fund_code, analysis_date)
                    holding_shares = holding_data.get('holding_shares', 0)
                    
                    if not holding_shares or holding_shares <= 0:
                        self.logger.info(f"   📊 {fund_code} 持仓份额为0，今日收益为0")
                        return 0.0
                    
                    # 获取当日净值
                    current_nav_sql = """
                    SELECT unit_nav 
                    FROM fund_nav_data 
                    WHERE fund_code = %s AND nav_date = %s
                    """
                    cursor.execute(current_nav_sql, (fund_code, analysis_date))
                    current_result = cursor.fetchone()
                    
                    if not current_result or not current_result['unit_nav']:
                        self.logger.warning(f"   ⚠️ {fund_code} 未找到当日净值数据")
                        return 0.0
                    
                    current_nav = float(current_result['unit_nav'])
                    
                    # 获取前一日净值
                    prev_nav_sql = """
                    SELECT unit_nav 
                    FROM fund_nav_data 
                    WHERE fund_code = %s AND nav_date < %s
                    ORDER BY nav_date DESC
                    LIMIT 1
                    """
                    cursor.execute(prev_nav_sql, (fund_code, analysis_date))
                    prev_result = cursor.fetchone()
                    
                    if not prev_result or not prev_result['unit_nav']:
                        self.logger.warning(f"   ⚠️ {fund_code} 未找到前一日净值数据")
                        return 0.0
                    
                    prev_nav = float(prev_result['unit_nav'])
                    
                    # 计算今日收益变化：持有份额 × (当日净值 - 前一日净值)
                    today_change = float(holding_shares) * (current_nav - prev_nav)
                    
                    self.logger.info(f"   📊 {fund_code} 今日收益计算:")
                    self.logger.info(f"      持有份额: {holding_shares}")
                    self.logger.info(f"      当日净值: {current_nav}")
                    self.logger.info(f"      前日净值: {prev_nav}")
                    self.logger.info(f"      净值差额: {current_nav - prev_nav}")
                    self.logger.info(f"      今日收益: {today_change}")
                    
                    return today_change
                        
        except Exception as e:
            self.logger.error(f"计算今日变化失败: {e}")
            return 0.0

    def run_daily_monitoring(self, fund_codes: List[str] = None, analysis_date: date = None, 
                           save_to_db: bool = True, sync_to_yida: bool = True) -> List[Dict[str, Any]]:
        """运行每日监测"""
        try:
            if analysis_date is None:
                analysis_date = date.today()
            
            self.logger.info(f"🚀 开始V5版本每日监测计算: {analysis_date}")
            
            # 检查是否为休市日
            if self.is_market_closed(analysis_date):
                self.logger.info(f"📅 {analysis_date} 为休市日，跳过监测")
                return []
            
            # 获取基础数据
            self.logger.info("📊 获取基础数据...")
            base_data_list = self.get_base_data(fund_codes, analysis_date)
            
            if not base_data_list:
                self.logger.warning("⚠️ 未获取到基础数据")
                return []
            
            self.logger.info(f"获取基础数据完成，共{len(base_data_list)}只基金")
            
            # 预加载宜搭记录
            if sync_to_yida:
                record_ids = [f"{data['fund_code']}_{analysis_date.strftime('%Y-%m-%d')}" 
                              for data in base_data_list]
                self._preload_yida_records(record_ids)
            
            # 处理每只基金
            results = []
            success_count = 0
            
            for i, base_data in enumerate(base_data_list, 1):
                fund_code = base_data['fund_code']
                fund_name = base_data.get('fund_name', '')
                
                try:
                    self.logger.info(f"📈 处理基金 {i}/{len(base_data_list)}: {fund_code} {fund_name}")
                    
                    # 生成监测记录
                    record = self.generate_monitoring_record(base_data)
                    
                    # V5版本：显示趋势判断结果
                    trend_direction = record.get('trend_direction', '未知')
                    daily_return = record.get('daily_return', 0)
                    self.logger.info(f"   📊 V5趋势判断: {fund_code} 当日{daily_return:+.2f}% → {trend_direction}")
                    
                    # 保存到数据库
                    if save_to_db:
                        if self.save_to_database(record):
                            self.logger.info(f"   ✅ 数据库保存成功: {fund_code}")
                        else:
                            self.logger.error(f"   ❌ 数据库保存失败: {fund_code}")
                    
                    # 同步到宜搭
                    if sync_to_yida:
                        if self.sync_to_yida(record):
                            self.logger.info(f"   ✅ 宜搭同步成功: {fund_code}")
                            success_count += 1
                        else:
                            self.logger.error(f"   ❌ 宜搭同步失败: {fund_code}")
                    else:
                        success_count += 1
                    
                    results.append(record)
                    
                except Exception as e:
                    self.logger.error(f"❌ 处理基金 {fund_code} 失败: {e}")
                    continue
            
            self.logger.info(f"🎯 V5版本计算完成: 成功 {success_count}/{len(base_data_list)}")
            
            if success_count < len(base_data_list):
                self.logger.warning("⚠️ 部分基金处理失败，请检查日志")
            
            return results
            
        except Exception as e:
            self.logger.error(f"每日监测运行失败: {e}")
            return []

    def _calculate_accumulated_profit(self, fund_code: str, analysis_date: date, today_change: float) -> float:
        """计算累计收益"""
        try:
            # 获取前一个交易日的累计收益
            prev_date = self._get_previous_trading_date(analysis_date)
            prev_accumulated_profit = self._get_prev_accumulated_profit_from_monitoring(fund_code, prev_date)
            
            if prev_accumulated_profit is None:
                # 如果监测表中没有数据，尝试从holdings表获取
                prev_accumulated_profit = self._get_prev_total_return_from_holdings(fund_code, prev_date)
                if prev_accumulated_profit is None:
                    prev_accumulated_profit = 0.0
            
            # 累计收益 = 前日累计收益 + 今日变化
            accumulated_profit = prev_accumulated_profit + today_change
            
            return accumulated_profit
            
        except Exception as e:
            self.logger.error(f"计算累计收益失败: {e}")
            return 0.0

    def _get_prev_total_return_from_holdings(self, fund_code: str, prev_date: date) -> float:
        """从holdings表获取前日总收益 - 时间一致性修复版"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    sql = """
                    SELECT total_return
                    FROM holdings 
                    WHERE fund_code = %s 
                        AND DATE(holding_date) <= %s
                        AND DATE(updated_at) <= %s
                    ORDER BY holding_date DESC, updated_at DESC
                    LIMIT 1
                    """
                    cursor.execute(sql, (fund_code, prev_date, prev_date))
                    result = cursor.fetchone()
                    
                    if result and result['total_return'] is not None:
                        return float(result['total_return'])
                    else:
                        return None
                        
        except Exception as e:
            self.logger.error(f"从holdings表获取前日总收益失败: {e}")
            return None

    def _get_prev_accumulated_profit_from_monitoring(self, fund_code: str, prev_date: date) -> float:
        """从monitoring表获取前日累计收益"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    sql = """
                    SELECT accumulated_profit
                    FROM daily_monitoring 
                    WHERE fund_code = %s AND analysis_date = %s
                    """
                    cursor.execute(sql, (fund_code, prev_date))
                    result = cursor.fetchone()
                    
                    if result and result['accumulated_profit'] is not None:
                        return float(result['accumulated_profit'])
                    else:
                        return None
                        
        except Exception as e:
            self.logger.error(f"从monitoring表获取前日累计收益失败: {e}")
            return None

    def _get_previous_trading_date(self, analysis_date: date) -> date:
        """获取前一个交易日"""
        try:
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    sql = """
                    SELECT DISTINCT nav_date
                    FROM fund_nav_data 
                    WHERE nav_date < %s
                    ORDER BY nav_date DESC 
                    LIMIT 1
                    """
                    cursor.execute(sql, (analysis_date,))
                    result = cursor.fetchone()
                    
                    if result:
                        return result['nav_date']
                    else:
                        # 如果没有找到，返回前一天
                        return analysis_date - timedelta(days=1)
                        
        except Exception as e:
            self.logger.error(f"获取前一个交易日失败: {e}")
            return analysis_date - timedelta(days=1)

    def _calculate_today_change_in_technical_indicators(self, fund_code: str, analysis_date: date, nav_data: List[Dict]) -> float:
        """在技术指标计算中计算今日收益变化 - 使用原始脚本算法 (时间一致性修复版)"""
        try:
            # 获取持仓数据 - 确保时间点一致性
            with self._get_db_connection() as connection:
                with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    holding_sql = """
                    SELECT holding_shares, market_value
                    FROM holdings 
                    WHERE fund_code = %s 
                      AND DATE(holding_date) <= %s
                      AND DATE(updated_at) <= %s
                    ORDER BY holding_date DESC, updated_at DESC
                    LIMIT 1
                    """
                    cursor.execute(holding_sql, (fund_code, analysis_date, analysis_date))
                    holding = cursor.fetchone()
                    
                    if not holding:
                        self.logger.warning(f"   ⚠️ {fund_code} 未找到持仓数据")
                        return 0.0
                    
                    holding_shares = float(holding['holding_shares'] or 0)
                    holdings_market_value = float(holding['market_value'] or 0)
                    
                    # 获取当日净值和日涨跌幅
                    if not nav_data:
                        return 0.0
                    
                    current_nav_data = nav_data[0]  # 最新的净值数据
                    unit_nav = float(current_nav_data['unit_nav'] or 0)
                    daily_return = float(current_nav_data['daily_return'] or 0)
                    
                    # 计算当前市值：使用最新净值 × 持仓份额
                    current_market_value = holding_shares * unit_nav if holding_shares > 0 and unit_nav > 0 else holdings_market_value
                    
                    # 计算今日收益变化（基于日涨跌幅和当前市值）- 原始脚本算法
                    today_change = current_market_value * (daily_return / 100) if current_market_value > 0 and daily_return != 0 else 0
                    
                    self.logger.info(f"   🔍 {fund_code} today_change计算: {current_market_value} × ({daily_return}/100) = {today_change}")
                    
                    return today_change
                    
        except Exception as e:
            self.logger.error(f"计算今日收益变化失败 {fund_code}: {e}")
            return 0.0


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='每日监测数据计算脚本 V5')
    parser.add_argument('--date', type=str, help='分析日期 (YYYY-MM-DD)')
    parser.add_argument('--funds', type=str, nargs='+', help='指定基金代码列表')
    parser.add_argument('--no-db', action='store_true', help='不保存到数据库')
    parser.add_argument('--no-yida', action='store_true', help='不同步到宜搭')
    parser.add_argument('--config', type=str, help='配置文件路径')
    
    args = parser.parse_args()
    
    try:
        # 解析日期
        analysis_date = None
        if args.date:
            analysis_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        
        # 初始化计算器
        calculator = DailyMonitoringCalculatorV5(args.config)
        
        # 运行监测
        results = calculator.run_daily_monitoring(
            fund_codes=args.funds,
            analysis_date=analysis_date,
            save_to_db=not args.no_db,
            sync_to_yida=not args.no_yida
        )
        
        print(f"✅ V5版本监测完成，处理了 {len(results)} 只基金")
        
    except Exception as e:
        print(f"❌ V5版本监测失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
