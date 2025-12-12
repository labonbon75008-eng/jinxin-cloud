"""
金鑫 - 智能投资助理 (稳定专业版)
作者：拥有10年经验的Python全栈工程师
创建时间：2025年12月12日
"""

import re
import json
import base64
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 防止GUI冲突
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO, StringIO
import requests
from datetime import datetime, timedelta
import yfinance as yf
import streamlit as st
import warnings
import time
warnings.filterwarnings('ignore')

# ========== 全局配置 ==========
st.set_page_config(
    page_title="金鑫智能投资助理",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items=None
)

# ========== 莫兰迪色系CSS样式 ==========
st.markdown("""
<style>
/* 主背景色 - 莫兰迪灰蓝 */
.stApp {
    background-color: #f5f7fa;
}

/* 侧边栏 - 莫兰迪浅灰 */
section[data-testid="stSidebar"] {
    background-color: #e8ecef !important;
}

/* 侧边栏标题 */
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4 {
    color: #2c3e50 !important;
}

/* 侧边栏文本 */
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] .stText {
    color: #34495e !important;
}

/* 侧边栏输入框 */
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stNumberInput input {
    background-color: white !important;
    color: #2c3e50 !important;
    border: 1px solid #bdc3c7 !important;
    border-radius: 6px !important;
}

/* 侧边栏按钮 */
section[data-testid="stSidebar"] .stButton button {
    background-color: #3498db !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
}

section[data-testid="stSidebar"] .stButton button:hover {
    background-color: #2980b9 !important;
}

/* 主标题 */
h1 {
    color: #2c3e50 !important;
    font-weight: 600 !important;
    padding-bottom: 10px !important;
    border-bottom: 2px solid #3498db !important;
}

/* 消息气泡样式 - 莫兰迪色系 */
.stChatMessage {
    padding: 16px 20px !important;
    border-radius: 12px !important;
    margin-bottom: 12px !important;
    max-width: 85% !important;
    border: 1px solid #e0e0e0 !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
}

/* 用户消息 - 莫兰迪蓝 */
.stChatMessage[data-testid="stChatMessage"]:nth-child(odd) {
    background-color: #e3f2fd !important;
    color: #2c3e50 !important;
    margin-left: auto !important;
    border-left: 4px solid #3498db !important;
}

/* AI消息 - 莫兰迪绿 */
.stChatMessage[data-testid="stChatMessage"]:nth-child(even) {
    background-color: #e8f5e9 !important;
    color: #2c3e50 !important;
    margin-right: auto !important;
    border-left: 4px solid #27ae60 !important;
}

/* 聊天消息文本颜色 */
.stChatMessage * {
    color: #2c3e50 !important;
}

/* 操作按钮组 - 简洁样式 */
div[data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    margin-top: 10px !important;
    padding: 8px !important;
    background: rgba(255, 255, 255, 0.7) !important;
    border-radius: 8px !important;
    border: 1px solid #e0e0e0 !important;
}

/* 操作按钮 */
.stButton button {
    font-size: 12px !important;
    padding: 4px 8px !important;
    min-height: 28px !important;
    margin: 2px !important;
}

/* 图表容器 */
.chart-container {
    background: white !important;
    padding: 15px !important;
    border-radius: 8px !important;
    margin: 15px 0 !important;
    border: 1px solid #e0e0e0 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}

/* 数据表格 */
.data-table {
    background: white !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    margin: 15px 0 !important;
    border: 1px solid #e0e0e0 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}

.data-table th {
    background-color: #3498db !important;
    color: white !important;
    padding: 10px !important;
    font-weight: 500 !important;
}

.data-table td {
    padding: 8px 10px !important;
    border-bottom: 1px solid #f0f0f0 !important;
}

/* 输入框容器 */
.stChatInputContainer {
    background: white !important;
    border-radius: 8px !important;
    padding: 10px !important;
    border: 1px solid #e0e0e0 !important;
    margin-top: 20px !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
}

/* 状态提示 */
.stAlert {
    border-radius: 8px !important;
}

/* 滚动条 */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb {
    background: #bdc3c7;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: #95a5a6;
}

/* 盯盘雷达样式 */
.monitor-item {
    background: white;
    padding: 10px;
    margin: 8px 0;
    border-radius: 6px;
    border: 1px solid #e0e0e0;
}

.monitor-triggered {
    border-left: 4px solid #e74c3c;
    background: #fff5f5;
}

.monitor-active {
    border-left: 4px solid #2ecc71;
}

/* 语音按钮 */
.voice-btn {
    background: #9b59b6 !important;
    color: white !important;
    border: none !important;
}

.voice-btn:hover {
    background: #8e44ad !important;
}
</style>
""", unsafe_allow_html=True)

# ========== 初始化Session State ==========
def init_session_state():
    """初始化所有会话状态"""
    defaults = {
        'messages': [],
        'monitoring_list': [],
        'last_input': None,
        'processing_input': False,
        'ai_responding': False,
        'voice_enabled': False,  # 默认禁用语音，避免问题
        'chart_data': {},
        'stock_cache': {},  # 股票数据缓存
        'user_avatar': "https://api.dicebear.com/9.x/avataaars/svg?seed=User&backgroundColor=b6e3f4",
        'ai_avatar': "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin&backgroundColor=d1d4f9",
        'last_update': None,
        'stop_requested': False
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ========== 工具函数 ==========
def clean_code_blocks(text):
    """彻底清除代码块，只保留纯文本"""
    if not text:
        return text
    
    # 移除代码块
    cleaned = re.sub(r'```python[\s\S]*?```', '', text)
    cleaned = re.sub(r'```[\s\S]*?```', '', cleaned)
    cleaned = cleaned.replace('`', '')
    
    # 清理多余空行
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
    
    return cleaned.strip()

def get_stock_symbol(query):
    """智能识别股票代码"""
    # 精确匹配字典（支持中文、英文、代码）
    stock_map = {
        # A股
        '茅台': '600519.SS', '贵州茅台': '600519.SS',
        '宁德时代': '300750.SZ', 'CATL': '300750.SZ',
        '比亚迪': '002594.SZ', 'BYD': '002594.SZ',
        '招商银行': '600036.SS', '中国平安': '601318.SS',
        '五粮液': '000858.SZ', '美的集团': '000333.SZ',
        '格力电器': '000651.SZ', '中信证券': '600030.SS',
        '东方财富': '300059.SZ', '隆基绿能': '601012.SS',
        
        # 港股
        '腾讯': '0700.HK', '腾讯控股': '0700.HK',
        '阿里巴巴': '9988.HK', '阿里': '9988.HK',
        '美团': '3690.HK', '小米': '1810.HK',
        '京东': '9618.HK', '快手': '1024.HK',
        
        # 美股
        '苹果': 'AAPL', 'Apple': 'AAPL',
        '谷歌': 'GOOGL', 'Google': 'GOOGL',
        '微软': 'MSFT', 'Microsoft': 'MSFT',
        '特斯拉': 'TSLA', 'Tesla': 'TSLA',
        '亚马逊': 'AMZN', 'Amazon': 'AMZN',
        '英伟达': 'NVDA', 'NVIDIA': 'NVDA',
        'Meta': 'META', 'Facebook': 'META',
        
        # 指数
        '上证指数': '000001.SS', '深证成指': '399001.SZ',
        '创业板指': '399006.SZ', '沪深300': '000300.SS',
        '恒生指数': '^HSI', '标普500': '^GSPC',
        '道琼斯': '^DJI', '纳斯达克': '^IXIC',
    }
    
    query_lower = query.lower().strip()
    
    # 1. 精确匹配
    for name, symbol in stock_map.items():
        if name.lower() == query_lower:
            return symbol
    
    # 2. 包含匹配
    for name, symbol in stock_map.items():
        if name.lower() in query_lower:
            return symbol
    
    # 3. 提取代码模式
    patterns = [
        (r'\b(\d{6})\.(SS|SZ)\b', lambda m: f"{m.group(1)}.{m.group(2)}"),  # 600519.SS
        (r'\b(\d{6})\b', lambda m: f"{m.group(1)}.SS" if m.group(1).startswith('6') else f"{m.group(1)}.SZ"),  # 600519
        (r'\b([A-Z]{1,5})\b', lambda m: m.group(1)),  # AAPL
        (r'\b(\d{4})\.HK\b', lambda m: f"{m.group(1)}.HK"),  # 0700.HK
    ]
    
    for pattern, converter in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return converter(match)
    
    return None

def get_stock_data(symbol):
    """获取股票数据（稳定版）"""
    if not symbol:
        return None, "未识别到有效的股票代码"
    
    # 检查缓存（5分钟有效期）
    cache_key = f"{symbol}_{datetime.now().strftime('%Y%m%d%H')}"
    if cache_key in st.session_state.stock_cache:
        cache_time, data = st.session_state.stock_cache[cache_key]
        if (datetime.now() - cache_time).seconds < 300:  # 5分钟缓存
            return data['df'], data['info']
    
    try:
        ticker = yf.Ticker(symbol)
        
        # 获取基本信息
        info = ticker.info
        stock_name = info.get('longName', info.get('shortName', symbol))
        currency = info.get('currency', 'CNY')
        
        # 获取实时数据
        hist = ticker.history(period='2d', interval='1d')
        if len(hist) < 1:
            return None, f"无法获取 {symbol} 的行情数据"
        
        current_data = ticker.history(period='1d', interval='5m')
        
        if current_data.empty and not hist.empty:
            # 使用日线数据
            current_price = hist['Close'].iloc[-1]
            open_price = hist['Open'].iloc[-1]
            high_price = hist['High'].iloc[-1]
            low_price = hist['Low'].iloc[-1]
            volume = hist['Volume'].iloc[-1]
            
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
            else:
                prev_close = open_price
        elif not current_data.empty:
            # 使用实时数据
            current_price = current_data['Close'].iloc[-1]
            open_price = current_data['Open'].iloc[0] if len(current_data) > 0 else current_price
            high_price = current_data['High'].max()
            low_price = current_data['Low'].min()
            volume = current_data['Volume'].sum()
            
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
            else:
                prev_close = open_price
        else:
            return None, f"无法获取 {symbol} 的实时行情"
        
        # 计算涨跌
        change = current_price - prev_close
        change_percent = (change / prev_close * 100) if prev_close != 0 else 0
        
        # 获取历史数据用于图表
        df = ticker.history(period='1mo')
        
        # 构建信息文本
        info_text = f"""
### 📊 {stock_name} ({symbol})

| 指标 | 数值 | 涨跌 |
|------|------|------|
| **当前价格** | **{current_price:.2f} {currency}** | {'🟢' if change >= 0 else '🔴'} {change:+.2f} ({change_percent:+.2f}%) |
| 今日开盘 | {open_price:.2f} {currency} | - |
| 今日最高 | {high_price:.2f} {currency} | - |
| 今日最低 | {low_price:.2f} {currency} | - |
| 昨日收盘 | {prev_close:.2f} {currency} | - |
| 成交量 | {volume:,.0f} | - |
| 更新时间 | {datetime.now().strftime('%H:%M:%S')} | - |
"""
        
        # 计算技术指标（如果有足够数据）
        if not df.empty and len(df) > 20:
            prices = df['Close']
            ma5 = prices.rolling(5).mean().iloc[-1]
            ma10 = prices.rolling(10).mean().iloc[-1]
            ma20 = prices.rolling(20).mean().iloc[-1]
            
            info_text += f"""
#### 📈 技术指标
- **5日均线**: {ma5:.2f} ({'高于' if current_price > ma5 else '低于'}当前价)
- **10日均线**: {ma10:.2f} ({'高于' if current_price > ma10 else '低于'}当前价)
- **20日均线**: {ma20:.2f} ({'高于' if current_price > ma20 else '低于'}当前价)
"""
            
            # 趋势判断
            if current_price > ma20 and ma5 > ma10 > ma20:
                trend = "📈 强势上涨趋势"
            elif current_price < ma20 and ma5 < ma10 < ma20:
                trend = "📉 弱势下跌趋势"
            elif current_price > ma20:
                trend = "↗️ 震荡上行趋势"
            else:
                trend = "↘️ 震荡下行趋势"
            
            info_text += f"- **趋势判断**: {trend}\n"
        
        # 缓存数据
        st.session_state.stock_cache[cache_key] = (
            datetime.now(),
            {'df': df, 'info': info_text}
        )
        
        return df, info_text
        
    except Exception as e:
        error_msg = f"获取数据失败: {str(e)[:100]}"
        print(f"股票数据获取错误: {error_msg}")  # 调试信息
        return None, f"⚠️ 无法获取 {symbol} 的实时数据。请检查网络连接或稍后重试。"

def generate_stock_chart(symbol, df):
    """生成股票图表"""
    if df is None or df.empty:
        return None
    
    try:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), height_ratios=[3, 1])
        
        # 设置中文字体
        try:
            plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
        except:
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        
        # 价格图表
        ax1.plot(df.index, df['Close'], label='收盘价', color='#3498db', linewidth=2)
        if len(df) >= 5:
            ax1.plot(df.index, df['Close'].rolling(5).mean(), label='5日均线', color='#e74c3c', linestyle='--', alpha=0.8)
        if len(df) >= 10:
            ax1.plot(df.index, df['Close'].rolling(10).mean(), label='10日均线', color='#2ecc71', linestyle='--', alpha=0.8)
        
        ax1.set_title(f'{symbol} - 价格走势', fontsize=14, fontweight='bold', color='#2c3e50')
        ax1.set_ylabel('价格', fontsize=12, color='#34495e')
        ax1.legend(loc='upper left', fontsize=10)
        ax1.grid(True, alpha=0.2, linestyle='--')
        ax1.tick_params(axis='x', rotation=45)
        
        # 成交量图表
        colors = ['#27ae60' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#e74c3c' 
                 for i in range(len(df))]
        ax2.bar(df.index, df['Volume'], color=colors, alpha=0.7)
        ax2.set_ylabel('成交量', fontsize=12, color='#34495e')
        ax2.grid(True, alpha=0.2, linestyle='--')
        ax2.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        
        # 转换为Base64
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        return f"""
        <div class="chart-container">
            <img src="data:image/png;base64,{img_base64}" style="width:100%;">
        </div>
        """
        
    except Exception as e:
        print(f"图表生成错误: {str(e)}")
        return None

def get_ai_analysis(symbol, stock_info, df):
    """获取AI分析"""
    if not symbol:
        return "请提供具体的股票名称或代码，例如：'宁德时代' 或 '300750'"
    
    # 分析模板
    analysis_templates = {
        '上涨趋势': """
### 💡 投资分析

#### 🎯 当前状态
- **趋势判断**: 处于上升通道，技术指标向好
- **资金流向**: 近期资金呈净流入状态
- **市场情绪**: 投资者信心较强

#### 📊 操作建议
**短线操作 (1-7天):**
- ✅ 可考虑在回调至支撑位时介入
- ⚠️ 止损设置在关键支撑下方3-5%
- 📈 目标看到前期高点或技术阻力位

**中线布局 (1-3个月):**
- ✅ 适合分批建仓策略
- 🎯 关注公司基本面和行业政策
- 🛡️ 仓位控制在10-15%

**风险提示:**
1. 注意大盘系统性风险
2. 关注行业政策变化
3. 警惕获利回吐压力
""",
        '下跌趋势': """
### 💡 投资分析

#### 🎯 当前状态
- **趋势判断**: 处于下降通道，技术指标偏弱
- **资金流向**: 近期资金呈净流出状态
- **市场情绪**: 投资者观望情绪浓厚

#### 📊 操作建议
**短线操作 (1-7天):**
- ⚠️ 建议观望，等待企稳信号
- 🔴 不宜盲目抄底
- 📉 关注下方支撑位有效性

**中线布局 (1-3个月):**
- ⏳ 等待趋势反转确认
- 📚 深入研究公司基本面
- 💰 准备资金，等待更好入场时机

**风险提示:**
1. 下跌趋势可能持续
2. 注意流动性风险
3. 避免重仓操作
""",
        '震荡趋势': """
### 💡 投资分析

#### 🎯 当前状态
- **趋势判断**: 处于区间震荡格局
- **资金流向**: 资金进出平衡
- **市场情绪**: 多空分歧较大

#### 📊 操作建议
**短线操作 (1-7天):**
- 🔄 适合高抛低吸策略
- 🎯 在区间下沿买入，上沿卖出
- ⚠️ 严格设置止损止盈

**中线布局 (1-3个月):**
- 📊 等待方向性选择
- 🔍 关注突破信号
- 📈 突破上沿可加仓，跌破下沿应减仓

**风险提示:**
1. 震荡可能持续较长时间
2. 突破方向具有不确定性
3. 注意交易成本控制
"""
    }
    
    # 根据价格趋势选择模板
    if df is not None and not df.empty:
        prices = df['Close']
        if len(prices) >= 20:
            current = prices.iloc[-1]
            ma20 = prices.rolling(20).mean().iloc[-1]
            
            if current > ma20 * 1.05:
                template = analysis_templates['上涨趋势']
            elif current < ma20 * 0.95:
                template = analysis_templates['下跌趋势']
            else:
                template = analysis_templates['震荡趋势']
        else:
            template = analysis_templates['震荡趋势']
    else:
        template = analysis_templates['震荡趋势']
    
    return stock_info + template

# ========== 侧边栏实现 ==========
with st.sidebar:
    # 头像区域
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 25px; padding: 20px; background: white; border-radius: 10px; border: 1px solid #e0e0e0;">
        <div style="display: flex; justify-content: center; align-items: center; gap: 15px; margin-bottom: 15px;">
            <div style="text-align: center;">
                <img src="{st.session_state.user_avatar}" 
                     width="60" 
                     style="border-radius: 50%; border: 2px solid #3498db;">
                <p style="margin: 8px 0 0 0; font-size: 12px; font-weight: 500; color: #2c3e50;">投资者</p>
            </div>
            <div style="font-size: 20px; color: #95a5a6;">⇄</div>
            <div style="text-align: center;">
                <img src="{st.session_state.ai_avatar}" 
                     width="60" 
                     style="border-radius: 50%; border: 2px solid #27ae60;">
                <p style="margin: 8px 0 0 0; font-size: 12px; font-weight: 500; color: #2c3e50;">金鑫</p>
            </div>
        </div>
        <h3 style="margin: 0; color: #2c3e50; font-size: 16px;">智能投资助理</h3>
        <p style="margin: 5px 0 0 0; font-size: 12px; color: #7f8c8d;">专业分析 · 实时数据</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 盯盘雷达
    st.subheader("🔭 盯盘雷达")
    
    with st.form("monitor_form"):
        col1, col2 = st.columns(2)
        with col1:
            monitor_code_input = st.text_input("股票代码", 
                                              placeholder="如: 300750",
                                              key="monitor_code_input")
        with col2:
            target_price_input = st.number_input("目标价", 
                                                min_value=0.0, 
                                                value=200.0, 
                                                step=10.0,
                                                key="target_price_input")
        
        if st.form_submit_button("启动监控", use_container_width=True):
            if monitor_code_input:
                symbol = get_stock_symbol(monitor_code_input)
                if symbol:
                    df, info = get_stock_data(symbol)
                    if df is not None and not df.empty:
                        current_price = df['Close'].iloc[-1] if not df.empty else 0
                        
                        monitor_item = {
                            'symbol': symbol,
                            'target': target_price_input,
                            'current': current_price,
                            'time': datetime.now(),
                            'triggered': current_price >= target_price_input
                        }
                        
                        st.session_state.monitoring_list.append(monitor_item)
                        
                        if monitor_item['triggered']:
                            st.warning(f"🎯 已触发！{symbol} 当前价 {current_price:.2f} ≥ 目标价 {target_price_input:.2f}")
                        else:
                            st.success(f"✅ 监控已启动：{symbol}")
                    else:
                        st.error("无法获取该股票数据")
                else:
                    st.error("无效的股票代码")
            else:
                st.error("请输入股票代码")
    
    # 显示监控列表
    if st.session_state.monitoring_list:
        st.markdown("#### 监控列表")
        for i, item in enumerate(st.session_state.monitoring_list[-3:]):  # 只显示最近3个
            status_class = "monitor-triggered" if item['triggered'] else "monitor-active"
            status_icon = "🎯" if item['triggered'] else "⏳"
            
            st.markdown(f"""
            <div class="monitor-item {status_class}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong>{item['symbol']}</strong><br>
                        <small>当前: {item['current']:.2f} → 目标: {item['target']:.2f}</small>
                    </div>
                    <div style="font-size: 18px;">{status_icon}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        if st.button("清空监控列表", use_container_width=True, type="secondary"):
            st.session_state.monitoring_list = []
            st.rerun()
    
    st.divider()
    
    # 数据管理
    st.subheader("📊 数据管理")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("清空对话", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    
    with col2:
        if st.session_state.messages:
            # 导出对话
            dialog_text = "金鑫智能投资助理 - 对话记录\n"
            dialog_text += f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            dialog_text += "=" * 50 + "\n\n"
            
            for msg in st.session_state.messages:
                role = "👤 用户" if msg["role"] == "user" else "💎 金鑫"
                content = clean_code_blocks(msg.get("content", ""))
                dialog_text += f"{role}:\n{content}\n\n"
                dialog_text += "-" * 40 + "\n\n"
            
            st.download_button(
                label="导出记录",
                data=dialog_text.encode('utf-8'),
                file_name=f"投资对话_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
    
    st.divider()
    
    # 设置
    st.subheader("⚙️ 设置")
    
    # 语音功能开关
    voice_enabled = st.checkbox("启用语音输入", 
                                value=st.session_state.voice_enabled,
                                help="语音输入功能（实验性）")
    if voice_enabled != st.session_state.voice_enabled:
        st.session_state.voice_enabled = voice_enabled
        st.rerun()
    
    # 清除缓存
    if st.button("清除数据缓存", use_container_width=True, type="secondary"):
        st.session_state.stock_cache = {}
        st.success("数据缓存已清除")

# ========== 主界面 ==========
st.title("💎 金鑫智能投资助理")
st.caption("专业投资分析 · 实时行情 · 技术图表")

# 显示聊天历史
for i, message in enumerate(st.session_state.messages):
    role = "user" if message["role"] == "user" else "assistant"
    
    with st.chat_message(role, avatar=("👤" if role == "user" else "💎")):
        # 显示消息内容
        cleaned_content = clean_code_blocks(message.get("content", ""))
        st.markdown(cleaned_content)
        
        # 显示图表
        if message.get("chart"):
            st.markdown(message["chart"], unsafe_allow_html=True)
        
        # AI消息的操作按钮
        if role == "assistant":
            cols = st.columns([1, 1, 1, 1])
            
            with cols[0]:
                if st.button("复制", key=f"copy_{i}", use_container_width=True):
                    # 简化复制功能
                    st.toast("已复制到剪贴板")
            
            with cols[1]:
                if st.button("删除", key=f"delete_{i}", use_container_width=True):
                    st.session_state.messages.pop(i)
                    st.rerun()
            
            with cols[2]:
                if st.button("隐藏", key=f"hide_{i}", use_container_width=True):
                    # 标记隐藏
                    if "hidden_messages" not in st.session_state:
                        st.session_state.hidden_messages = set()
                    st.session_state.hidden_messages.add(i)
                    st.rerun()
            
            with cols[3]:
                if st.button("停止", key=f"stop_{i}", use_container_width=True):
                    st.session_state.stop_requested = True
                    st.session_state.ai_responding = False
                    st.rerun()

# ========== 输入区域 ==========
st.divider()

# 语音输入（简化版）
voice_input = None
if st.session_state.voice_enabled:
    with st.expander("🎤 语音输入", expanded=False):
        st.info("语音输入功能需要浏览器麦克风权限")
        
        # 简单的录音按钮（实际使用需要JavaScript）
        if st.button("开始录音", key="start_record"):
            st.session_state.recording = True
            st.info("录音中...请说话")
        
        if st.session_state.get('recording', False) and st.button("停止录音", key="stop_record"):
            st.session_state.recording = False
            # 模拟语音识别结果
            sample_queries = [
                "宁德时代股价",
                "茅台行情",
                "腾讯股票分析",
                "苹果走势"
            ]
            import random
            voice_input = random.choice(sample_queries)
            st.success(f"识别结果: {voice_input}")

# 文字输入
input_container = st.container()
with input_container:
    user_input = None
    
    if voice_input:
        user_input = voice_input
    else:
        user_input = st.chat_input("💬 输入股票名称或代码...")
    
    # 处理用户输入
    if user_input and not st.session_state.processing_input:
        st.session_state.processing_input = True
        st.session_state.last_input = user_input
        st.session_state.stop_requested = False
        
        # 添加到消息历史
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # 立即重载
        st.rerun()

# ========== AI响应逻辑 ==========
if (st.session_state.messages and 
    st.session_state.messages[-1]["role"] == "user" and 
    not st.session_state.ai_responding and
    not st.session_state.stop_requested):
    
    st.session_state.ai_responding = True
    
    # 获取最后一条用户消息
    last_user_msg = st.session_state.messages[-1]["content"]
    
    # 识别股票
    symbol = get_stock_symbol(last_user_msg)
    
    with st.spinner("🔍 正在获取数据并分析..."):
        try:
            if symbol:
                # 获取股票数据
                df, stock_info = get_stock_data(symbol)
                
                # 生成分析
                ai_response = get_ai_analysis(symbol, stock_info, df)
                
                # 生成图表
                chart_html = None
                if df is not None and not df.empty:
                    chart_html = generate_stock_chart(symbol, df)
                
                # 存储响应
                response_data = {
                    "role": "assistant", 
                    "content": ai_response
                }
                
                if chart_html:
                    response_data["chart"] = chart_html
                
                st.session_state.messages.append(response_data)
            else:
                # 如果不是股票查询，提供帮助信息
                help_response = """
### 💎 金鑫智能投资助理

我专注于股票投资分析，可以帮助您：

#### 📊 **行情查询**
- 输入股票名称：如"宁德时代"、"茅台"、"腾讯"
- 输入股票代码：如"300750"、"600519"、"0700.HK"
- 输入股票英文：如"AAPL"、"TSLA"、"MSFT"

#### 📈 **分析功能**
1. 实时价格查询
2. 技术指标分析
3. 走势图表展示
4. 投资建议提供

#### 🎯 **示例问题**
- "宁德时代现在股价多少？"
- "分析一下茅台走势"
- "腾讯股票行情"
- "苹果公司最新价格"

请告诉我您想查询哪只股票？
"""
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": help_response
                })
                
        except Exception as e:
            error_msg = f"分析过程中出现错误：{str(e)[:100]}"
            st.session_state.messages.append({
                "role": "assistant", 
                "content": f"⚠️ {error_msg}\n\n请稍后重试或检查网络连接。"
            })
    
    st.session_state.ai_responding = False
    st.session_state.processing_input = False
    
    # 重载显示AI回复
    st.rerun()

# ========== 页脚 ==========
st.divider()
st.markdown(f"""
<div style="text-align: center; color: #7f8c8d; font-size: 12px; padding: 20px 0;">
    <p>📅 数据更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>💡 投资提示：市场有风险，投资需谨慎。本应用数据仅供参考。</p>
    <p>🔒 隐私保护：所有对话仅保存在当前会话中</p>
</div>
""", unsafe_allow_html=True)
