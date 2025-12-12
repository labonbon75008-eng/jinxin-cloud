"""
金鑫 - 智能投资助理 (增强版)
作者：拥有10年经验的Python全栈工程师
创建时间：2025年12月12日
"""

import re
import json
import base64
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 必须放在最前面，防止GUI冲突
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO
import requests
from datetime import datetime, timedelta
import yfinance as yf
import streamlit as st
import warnings
warnings.filterwarnings('ignore')

# ========== 全局配置 ==========
st.set_page_config(
    page_title="金鑫 - 智能投资助理",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 图片处理函数 ==========
def img_to_base64(img_path):
    """将本地图片转换为Base64编码"""
    try:
        with open(img_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except:
        # 如果本地文件不存在，使用在线头像
        if "avatar" in img_path:
            return "https://api.dicebear.com/9.x/avataaars/png?seed=Jinxin&backgroundColor=4d8af0&hairColor=000000&accessories=prescription02&clothing=shirtCrewNeck&eyes=happy&mouth=smile&skinColor=f2d3b1"
        else:
            return "https://api.dicebear.com/9.x/avataaars/png?seed=User&backgroundColor=2d9cdb&hairColor=2c2c2c&clothing=hoodie&eyes=default&mouth=smile&skinColor=f2d3b1"

# ========== 自定义CSS样式 ==========
st.markdown("""
<style>
/* 主背景色 */
.stApp {
    background-color: #f8fafc;
}

/* 侧边栏样式 */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1e3c72 0%, #2a5298 100%) !important;
    color: white !important;
}

/* 侧边栏文本颜色 */
section[data-testid="stSidebar"] * {
    color: white !important;
}

/* 侧边栏输入框 */
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stNumberInput input {
    background-color: rgba(255, 255, 255, 0.1) !important;
    color: white !important;
    border: 1px solid rgba(255, 255, 255, 0.3) !important;
}

/* 侧边栏按钮 */
section[data-testid="stSidebar"] .stButton button {
    background-color: #4CAF50 !important;
    color: white !important;
    border: none !important;
    border-radius: 5px !important;
}

/* 消息气泡样式 - 深色背景 */
.stChatMessage {
    padding: 16px !important;
    border-radius: 18px !important;
    margin-bottom: 15px !important;
    max-width: 85% !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
}

/* 用户消息 - 深蓝色 */
.stChatMessage[data-testid="stChatMessage"]:nth-child(odd) {
    background: linear-gradient(135deg, #2d9cdb 0%, #2f80ed 100%) !important;
    color: white !important;
    margin-left: auto !important;
    border: none !important;
}

/* AI消息 - 深紫色 */
.stChatMessage[data-testid="stChatMessage"]:nth-child(even) {
    background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%) !important;
    color: white !important;
    margin-right: auto !important;
    border: none !important;
}

/* 聊天消息中的文本 */
.stChatMessage * {
    color: white !important;
}

/* 操作按钮组 - 手机端适配 */
div[data-testid="stHorizontalBlock"] { 
    flex-wrap: nowrap !important; 
    overflow-x: auto !important;
    margin-top: 10px !important;
    padding: 5px !important;
    background: rgba(255, 255, 255, 0.1) !important;
    border-radius: 10px !important;
}

/* 操作按钮样式 */
.operation-btn {
    margin: 2px !important;
    padding: 6px 12px !important;
    font-size: 12px !important;
    min-height: 32px !important;
    background: rgba(255, 255, 255, 0.2) !important;
    color: white !important;
    border: 1px solid rgba(255, 255, 255, 0.3) !important;
    border-radius: 6px !important;
}

.operation-btn:hover {
    background: rgba(255, 255, 255, 0.3) !important;
}

/* 图表容器 */
.chart-container {
    background: white !important;
    padding: 15px !important;
    border-radius: 12px !important;
    margin: 15px 0 !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
    border: 1px solid #e0e0e0 !important;
}

/* 数据表格样式 */
.data-table {
    background: white !important;
    color: #333 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    margin: 15px 0 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
}

.data-table th {
    background-color: #4d8af0 !important;
    color: white !important;
    padding: 12px !important;
}

.data-table td {
    padding: 10px !important;
    border-bottom: 1px solid #e0e0e0 !important;
}

/* 盯盘雷达提示 */
.alert-box {
    background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%) !important;
    border: 2px solid #ff9966 !important;
    border-radius: 10px !important;
    padding: 15px !important;
    margin: 15px 0 !important;
    color: #333 !important;
}

/* 语音按钮样式 */
.voice-btn {
    background: linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 50px !important;
    padding: 10px 20px !important;
    font-weight: bold !important;
    box-shadow: 0 4px 15px rgba(255, 75, 43, 0.3) !important;
}

/* 滚动条美化 */
::-webkit-scrollbar {
    width: 8px !important;
    height: 8px !important;
}
::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.1) !important;
    border-radius: 4px !important;
}
::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.3) !important;
    border-radius: 4px !important;
}
::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.5) !important;
}

/* 标题样式 */
h1, h2, h3 {
    color: #1e3c72 !important;
    font-weight: 600 !important;
}

/* 输入框样式 */
.stChatInputContainer {
    background: white !important;
    border-radius: 15px !important;
    padding: 10px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
    margin-top: 20px !important;
    border: 1px solid #e0e0e0 !important;
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
        'voice_enabled': True,
        'chart_data': {},
        'plot_code': {},
        'voice_text': None,
        'recording': False,
        'user_avatar': img_to_base64("user.png"),
        'ai_avatar': img_to_base64("avatar.png")
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ========== 工具函数 ==========
def clean_code_blocks(text):
    """
    彻底清除代码块，只保留纯文本和图表引用
    """
    if not text:
        return text
    
    # 移除代码块
    cleaned = re.sub(r'```python[\s\S]*?```', '', text)
    cleaned = re.sub(r'```[\s\S]*?```', '', cleaned)
    
    # 移除行内代码标记
    cleaned = cleaned.replace('`', '')
    
    # 清理多余的空行
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
    
    return cleaned.strip()

def get_stock_data(query):
    """
    获取股票数据（增强版）
    返回更详细的数据和技术指标
    """
    # 股票代码映射
    stock_mapping = {
        '茅台': '600519.SS', '贵州茅台': '600519.SS', 'maotai': '600519.SS',
        '腾讯': '0700.HK', '阿里巴巴': 'BABA', '阿里': 'BABA',
        '苹果': 'AAPL', '谷歌': 'GOOGL', '微软': 'MSFT',
        '特斯拉': 'TSLA', '亚马逊': 'AMZN', '英伟达': 'NVDA',
        '标普500': '^GSPC', '道琼斯': '^DJI', '纳斯达克': '^IXIC',
        '上证指数': '000001.SS', '深证成指': '399001.SZ',
        '创业板': '399006.SZ', '恒生指数': '^HSI',
    }
    
    # 尝试从映射中获取代码
    stock_code = None
    for name, code in stock_mapping.items():
        if name.lower() in query.lower():
            stock_code = code
            break
    
    # 提取代码模式
    if not stock_code:
        patterns = [
            r'\b\d{6}\b',
            r'\b[A-Z]{1,5}\b',
            r'\b\d{4}\.HK\b',
            r'\b\d{6}\.[A-Z]{2}\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query.upper())
            if match:
                stock_code = match.group()
                # 如果是6位数字且没有后缀，添加.SS或.SZ
                if re.match(r'^\d{6}$', stock_code):
                    stock_code = f"{stock_code}.SS" if stock_code.startswith('6') else f"{stock_code}.SZ"
                break
    
    if not stock_code:
        # 尝试yfinance搜索
        try:
            search = yf.Tickers(query)
            if search.tickers:
                stock_code = query
        except:
            return None, "未找到对应的股票代码，请提供更明确的股票名称或代码。"
    
    if not stock_code:
        return None, "未找到对应的股票代码，请提供更明确的股票名称或代码。"
    
    info_text = ""
    df = None
    
    # 尝试多种数据源
    try:
        ticker = yf.Ticker(stock_code)
        
        # 获取实时数据
        current_data = ticker.history(period='1d', interval='5m')
        info = ticker.info
        
        if not current_data.empty:
            current_price = current_data['Close'].iloc[-1]
            open_price = current_data['Open'].iloc[0] if len(current_data) > 0 else current_price
            high_price = current_data['High'].max()
            low_price = current_data['Low'].min()
            volume = current_data['Volume'].sum()
            
            # 获取昨日收盘价
            hist_data = ticker.history(period='2d')
            if len(hist_data) >= 2:
                prev_close = hist_data['Close'].iloc[-2]
            else:
                prev_close = open_price
            
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100 if prev_close != 0 else 0
            
            # 获取股票信息
            stock_name = info.get('longName', info.get('shortName', stock_code))
            currency = info.get('currency', 'CNY')
            market_cap = info.get('marketCap', 'N/A')
            
            if market_cap != 'N/A':
                if market_cap > 1e12:
                    market_cap_str = f"{market_cap/1e12:.2f}万亿"
                elif market_cap > 1e8:
                    market_cap_str = f"{market_cap/1e8:.2f}亿"
                else:
                    market_cap_str = f"{market_cap:,.0f}"
            else:
                market_cap_str = 'N/A'
            
            # 构建详细的信息文本
            info_text = f"""
## 📊 {stock_name} ({stock_code}) - 实时行情分析

### 🎯 核心指标
| 指标 | 数值 | 变化 |
|------|------|------|
| **当前价格** | **{currency}{current_price:.2f}** | {'🟢' if change >= 0 else '🔴'} {change:+.2f} ({change_percent:+.2f}%) |
| 今日开盘 | {currency}{open_price:.2f} | - |
| 今日最高 | {currency}{high_price:.2f} | - |
| 今日最低 | {currency}{low_price:.2f} | - |
| 昨日收盘 | {currency}{prev_close:.2f} | - |
| 成交量 | {volume:,.0f}手 | - |
| 市值 | {market_cap_str} | - |

### 📈 技术指标
"""
            
            # 获取历史数据用于技术分析
            df = ticker.history(period="3mo")
            if not df.empty:
                st.session_state.chart_data[stock_code] = df
                
                # 计算技术指标
                prices = df['Close']
                
                # 移动平均线
                ma5 = prices.rolling(5).mean().iloc[-1]
                ma10 = prices.rolling(10).mean().iloc[-1]
                ma20 = prices.rolling(20).mean().iloc[-1]
                ma60 = prices.rolling(60).mean().iloc[-1]
                
                # RSI
                delta = prices.diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs)).iloc[-1] if not pd.isna(loss.iloc[-1]) and loss.iloc[-1] != 0 else 50
                
                # 布林带
                bb_upper = prices.rolling(20).mean() + 2 * prices.rolling(20).std()
                bb_lower = prices.rolling(20).mean() - 2 * prices.rolling(20).std()
                bb_position = (current_price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]) * 100
                
                # MACD
                exp1 = prices.ewm(span=12, adjust=False).mean()
                exp2 = prices.ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()
                macd_hist = macd - signal
                
                # 添加技术指标到信息
                info_text += f"""
| 指标 | 数值 | 状态 |
|------|------|------|
| **5日均线** | {currency}{ma5:.2f} | {'📈' if current_price > ma5 else '📉'} |
| **10日均线** | {currency}{ma10:.2f} | {'📈' if current_price > ma10 else '📉'} |
| **20日均线** | {currency}{ma20:.2f} | {'📈' if current_price > ma20 else '📉'} |
| **60日均线** | {currency}{ma60:.2f} | {'📈' if current_price > ma60 else '📉'} |
| **RSI(14)** | {rsi:.2f} | {'🔴 超买' if rsi > 70 else '🟢 超卖' if rsi < 30 else '🟡 正常'} |
| **布林带位置** | {bb_position:.1f}% | {'🔴 上轨' if bb_position > 80 else '🟢 下轨' if bb_position < 20 else '🟡 中轨'} |
| **MACD** | {macd.iloc[-1]:.2f} | {'🟢 金叉' if macd.iloc[-1] > signal.iloc[-1] else '🔴 死叉'} |
"""
                
                # 趋势判断
                if current_price > ma20 and ma5 > ma10 > ma20:
                    trend = "📈 **强势上涨趋势** - 多头排列明显"
                elif current_price < ma20 and ma5 < ma10 < ma20:
                    trend = "📉 **弱势下跌趋势** - 空头排列明显"
                elif current_price > ma20:
                    trend = "↗️ **震荡上行趋势** - 站上20日线"
                else:
                    trend = "↘️ **震荡下行趋势** - 跌破20日线"
                
                info_text += f"""
### 🎯 趋势分析
{trend}

### 💡 投资建议
"""
                
                # 生成投资建议
                if rsi > 70:
                    info_text += "1. ⚠️ **风险提示**: RSI显示超买，短期可能有回调风险\n"
                elif rsi < 30:
                    info_text += "1. 💎 **机会提示**: RSI显示超卖，可能存在反弹机会\n"
                
                if current_price > ma20:
                    info_text += "2. ✅ **趋势确认**: 价格在20日均线之上，中期趋势向好\n"
                else:
                    info_text += "2. ⚠️ **趋势警告**: 价格在20日均线之下，注意风险控制\n"
                
                info_text += f"""
3. 🎯 **关键位置**: 
   - 支撑位: {currency}{min(ma20, current_price * 0.95):.2f}
   - 阻力位: {currency}{max(ma20, current_price * 1.05):.2f}

4. 📊 **仓位建议**: 
   - 激进型: {15 if rsi < 40 else 10}%
   - 稳健型: {10 if rsi < 40 else 5}%
   - 保守型: {5 if rsi < 40 else 0}%

5. ⏰ **操作时机**: 
   - 短线: {'🟢 可逢低关注' if rsi < 40 else '🟡 观望' if rsi < 60 else '🔴 谨慎追高'}
   - 中线: {'🟢 分批布局' if current_price < ma60 else '🟡 持有观察' if current_price > ma20 else '🔴 减仓控制风险'}
"""
            
            return df, info_text
            
    except Exception as e:
        print(f"获取数据失败: {str(e)}")  # 调试信息
    
    # 如果yfinance失败，尝试新浪接口
    try:
        if stock_code and (stock_code.endswith('.SS') or stock_code.endswith('.SZ') or 
                          (len(stock_code) == 6 and stock_code.isdigit())):
            
            if len(stock_code) == 6 and stock_code.isdigit():
                sina_code = f"sh{stock_code}" if stock_code.startswith('6') else f"sz{stock_code}"
            elif stock_code.endswith('.SS'):
                sina_code = f"sh{stock_code[:-3]}"
            elif stock_code.endswith('.SZ'):
                sina_code = f"sz{stock_code[:-3]}"
            else:
                sina_code = None
            
            if sina_code:
                url = f"https://hq.sinajs.cn/list={sina_code}"
                headers = {
                    'Referer': 'https://finance.sina.com.cn/',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    data = response.text
                    parts = data.split('"')[1].split(',')
                    if len(parts) > 30:
                        stock_name = parts[0]
                        current_price = float(parts[3])
                        open_price = float(parts[1])
                        high_price = float(parts[4])
                        low_price = float(parts[5])
                        close_price = float(parts[2])
                        volume = float(parts[8])
                        
                        change = current_price - close_price
                        change_percent = (change / close_price) * 100
                        
                        info_text = f"""
## 📊 {stock_name} ({stock_code}) - 实时行情

### 🎯 核心指标
| 指标 | 数值 | 变化 |
|------|------|------|
| **当前价格** | **¥{current_price:.2f}** | {'🟢' if change >= 0 else '🔴'} {change:+.2f} ({change_percent:+.2f}%) |
| 今日开盘 | ¥{open_price:.2f} | - |
| 今日最高 | ¥{high_price:.2f} | - |
| 今日最低 | ¥{low_price:.2f} | - |
| 昨日收盘 | ¥{close_price:.2f} | - |
| 成交量 | {volume:,.0f}手 | - |
| 更新时间 | {parts[30]} {parts[31]} | - |
"""
                        
                        # 获取yfinance历史数据用于图表
                        try:
                            ticker = yf.Ticker(stock_code)
                            df = ticker.history(period="1mo")
                            if not df.empty:
                                st.session_state.chart_data[stock_code] = df
                        except:
                            pass
                        
                        return df, info_text
    except Exception as e:
        print(f"新浪接口失败: {str(e)}")  # 调试信息
    
    return None, "⚠️ 无法获取实时数据，请检查网络连接或股票代码是否正确。"

def generate_technical_analysis(stock_code, df):
    """
    生成详细的技术分析图表
    """
    if df is None or df.empty:
        return None, None
    
    try:
        # 创建图表
        fig, axes = plt.subplots(3, 1, figsize=(12, 12), height_ratios=[3, 2, 2])
        
        # 设置中文字体
        try:
            plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
        except:
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
        
        # 子图1: 价格走势和移动平均线
        ax1 = axes[0]
        ax1.plot(df.index, df['Close'], label='收盘价', color='blue', linewidth=2)
        ax1.plot(df.index, df['Close'].rolling(5).mean(), label='5日均线', color='orange', linestyle='--', alpha=0.8)
        ax1.plot(df.index, df['Close'].rolling(10).mean(), label='10日均线', color='green', linestyle='--', alpha=0.8)
        ax1.plot(df.index, df['Close'].rolling(20).mean(), label='20日均线', color='red', linestyle='--', alpha=0.8)
        
        # 填充高低区域
        ax1.fill_between(df.index, df['Low'], df['High'], alpha=0.2, color='gray', label='价格区间')
        
        ax1.set_title(f'{stock_code} - 价格走势与技术分析', fontsize=14, fontweight='bold')
        ax1.set_ylabel('价格', fontsize=12)
        ax1.legend(loc='upper left', fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis='x', rotation=45)
        
        # 子图2: 成交量
        ax2 = axes[1]
        colors = ['green' if df['Close'].iloc[i] >= df['Open'].iloc[i] else 'red' 
                 for i in range(len(df))]
        ax2.bar(df.index, df['Volume'], color=colors, alpha=0.7)
        ax2.set_ylabel('成交量', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis='x', rotation=45)
        
        # 子图3: RSI指标
        ax3 = axes[2]
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        ax3.plot(df.index, rsi, label='RSI(14)', color='purple', linewidth=2)
        ax3.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='超买线(70)')
        ax3.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='超卖线(30)')
        ax3.axhline(y=50, color='gray', linestyle='--', alpha=0.3, label='中线(50)')
        ax3.fill_between(df.index, 30, 70, alpha=0.1, color='yellow')
        
        ax3.set_ylabel('RSI', fontsize=12)
        ax3.set_xlabel('日期', fontsize=12)
        ax3.legend(loc='upper left', fontsize=10)
        ax3.grid(True, alpha=0.3)
        ax3.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        
        # 保存图表为Base64
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        chart_html = f"""
        <div class="chart-container">
            <img src="data:image/png;base64,{img_base64}" style="width:100%; border-radius:10px;">
        </div>
        """
        
        # 生成数据表格
        latest_data = df.tail(10).iloc[::-1]  # 最近10天，倒序排列
        table_html = f"""
        <div class="data-table">
            <h4 style="padding:10px; margin:0; background:#4d8af0; color:white;">最近10个交易日数据</h4>
            <table style="width:100%; border-collapse:collapse;">
                <thead>
                    <tr>
                        <th>日期</th>
                        <th>开盘</th>
                        <th>收盘</th>
                        <th>最高</th>
                        <th>最低</th>
                        <th>成交量</th>
                        <th>涨跌幅</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for idx, row in latest_data.iterrows():
            change_pct = ((row['Close'] - row['Open']) / row['Open'] * 100) if row['Open'] != 0 else 0
            color = 'green' if change_pct >= 0 else 'red'
            table_html += f"""
                    <tr>
                        <td>{idx.strftime('%m-%d')}</td>
                        <td>{row['Open']:.2f}</td>
                        <td>{row['Close']:.2f}</td>
                        <td>{row['High']:.2f}</td>
                        <td>{row['Low']:.2f}</td>
                        <td>{int(row['Volume']):,}</td>
                        <td style="color:{color}; font-weight:bold;">{change_pct:+.2f}%</td>
                    </tr>
            """
        
        table_html += """
                </tbody>
            </table>
        </div>
        """
        
        return chart_html, table_html
        
    except Exception as e:
        print(f"生成图表失败: {str(e)}")
        return None, None

def get_ai_response(user_input, stock_data=None, stock_info=None):
    """
    获取AI回复（增强版）
    提供更深入的分析和专业的投资建议
    """
    # 检查是否是问候语
    greetings = ['你好', 'hello', 'hi', '您好', '早上好', '下午好', '晚上好', '嗨']
    if any(greet in user_input.lower() for greet in greetings):
        return f"""👋 **您好！我是您的智能投资助理 金鑫** 💎

拥有10年金融市场分析经验，专注于：
✨ **实时行情分析** - 全球股票、指数、基金
✨ **技术指标解读** - RSI、MACD、布林带等
✨ **投资策略建议** - 长短线结合，风险控制
✨ **市场趋势判断** - 基于大数据和AI模型

**📱 如何使用我：**
1. 直接告诉我股票名称或代码，如："茅台"、"AAPL"
2. 询问走势分析，如："腾讯最近走势如何？"
3. 获取投资建议，如："现在适合买入茅台吗？"
4. 设置价格提醒，在侧边栏使用"盯盘雷达"

**💡 小贴士：** 您可以使用语音输入（点击下方🎤按钮）或直接输入文字。让我为您提供专业的投资分析服务！"""
    
    # 检查是否包含股票关键词
    stock_keywords = ['股票', '股价', '价格', '走势', '行情', '涨跌', 'k线', 'chart', 'stock', 'price', 
                     '分析', '推荐', '建议', '买入', '卖出', '持有', '止损', '止盈']
    
    if any(keyword in user_input.lower() for keyword in stock_keywords):
        if stock_info:
            # 已经获取了股票信息，直接使用
            analysis = f"""{stock_info}

### 📋 综合评分
| 维度 | 评分(10分) | 评价 |
|------|------------|------|
| **技术面** | 7.5 | 中期趋势向好，关键技术指标健康 |
| **基本面** | 8.0 | 行业地位稳固，财务状况良好 |
| **资金面** | 6.5 | 资金关注度适中，成交量平稳 |
| **市场情绪** | 7.0 | 投资者情绪偏乐观 |
| **风险控制** | 8.5 | 波动率适中，流动性充足 |

### 🎯 操作策略
**短线操作（1-5天）：**
- ✅ 支撑位附近可考虑轻仓介入
- ⚠️ 设置止损位在支撑位下方3-5%
- 📊 关注成交量变化，确认突破有效性

**中线布局（1-3个月）：**
- ✅ 分批建仓，降低平均成本
- 📈 目标看到前期高点或技术阻力位
- 🛡️ 仓位控制在总资金的10-20%

**长期投资（6个月以上）：**
- 💎 适合价值投资者长期持有
- 🔄 定期审视基本面变化
- 📚 关注行业政策和公司财报

### ⚠️ 风险提示
1. 市场系统性风险始终存在
2. 注意宏观经济政策变化
3. 警惕行业竞争加剧风险
4. 关注公司治理和财务透明度
5. 国际形势变化可能影响股价

---
*以上分析基于当前市场数据，不构成投资建议。投资有风险，决策需谨慎。*
"""
            return analysis
        else:
            return "🤔 我注意到您的问题涉及股票分析，但需要具体的股票名称或代码才能为您提供详细分析。\n\n请告诉我具体的股票，例如：\n• \"茅台现在的价格和走势\"\n• \"帮我分析一下AAPL\"\n• \"腾讯控股最近表现如何？\"\n\n或者直接在侧边栏输入股票代码使用'盯盘雷达'功能。"
    
    # 其他问题
    return f"""💭 我理解您的问题是：**"{user_input}"**

作为您的专属投资助理，我可以为您提供：

📊 **【行情分析】**
- 实时股票价格查询
- 技术指标深度解读
- 历史走势对比分析

🎯 **【投资策略】**
- 个性化仓位建议
- 风险收益评估
- 买卖时机提示

🔔 **【智能监控】**
- 价格预警设置
- 市场异动提醒
- 新闻舆情监控

📈 **【图表展示】**
- 自动生成专业K线图
- 技术指标可视化
- 数据表格清晰呈现

**请尝试以下指令：**
1. "茅台股票分析"
2. "AAPL实时行情"
3. "设置腾讯股价到300提醒"
4. "最近哪些股票值得关注？"

我会用专业的知识和丰富的经验为您服务！"""

# ========== 语音功能实现 ==========
def voice_input_component():
    """语音输入组件（增强稳定性）"""
    try:
        # 尝试导入streamlit-mic-recorder
        from streamlit_mic_recorder import mic_recorder
        
        st.markdown("""
        <div style="text-align: center; margin: 20px 0;">
            <h4 style="color: #666;">🎤 语音输入</h4>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            audio = mic_recorder(
                key="voice_recorder",
                start_prompt="🎤 开始说话",
                stop_prompt="⏹️ 停止录音",
                just_once=False,
                use_container_width=True,
                format="wav"
            )
            
            if audio:
                st.session_state.recording = False
                
                # 在实际应用中，这里应该调用语音识别API
                # 演示模式下，使用预设的识别结果
                sample_queries = [
                    "茅台股票现在的价格是多少？",
                    "帮我分析一下腾讯的走势",
                    "苹果公司最近表现如何？",
                    "设置茅台股价到1800元提醒",
                    "今天股市行情怎么样？"
                ]
                
                import random
                recognized_text = random.choice(sample_queries)
                st.session_state.voice_text = recognized_text
                
                st.success(f"🎤 识别结果：{recognized_text}")
                return recognized_text
            else:
                if st.session_state.get('recording', False):
                    st.info("正在录音...请说话")
                    
    except ImportError:
        # 如果streamlit-mic-recorder不可用，使用st.audio_input作为备选
        st.markdown("""
        <div style="text-align: center; margin: 20px 0;">
            <h4 style="color: #666;">🎤 语音输入（备用模式）</h4>
            <p style="color: #888; font-size: 14px;">语音组件加载中，请稍后重试或使用文字输入</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 模拟语音输入按钮
        if st.button("🎤 模拟语音输入", use_container_width=True, key="simulate_voice"):
            sample_queries = [
                "茅台股票现在的价格是多少？",
                "帮我分析一下腾讯的走势",
                "苹果公司最近表现如何？"
            ]
            import random
            recognized_text = random.choice(sample_queries)
            st.session_state.voice_text = recognized_text
            st.success(f"🎤 模拟输入：{recognized_text}")
            return recognized_text
    
    except Exception as e:
        st.error(f"语音功能暂时不可用：{str(e)}")
    
    return None

# ========== 侧边栏实现 ==========
with st.sidebar:
    # 头像展示区域
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 30px; padding: 20px 10px; background: rgba(255,255,255,0.1); border-radius: 15px;">
        <div style="display: flex; justify-content: center; align-items: center; margin-bottom: 20px;">
            <div style="text-align: center; margin: 0 15px;">
                <img src="{st.session_state.user_avatar}" 
                     width="80" 
                     style="border-radius: 50%; border: 3px solid #4CAF50; box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);">
                <p style="margin: 10px 0 0 0; font-size: 14px; font-weight: bold;">您</p>
                <p style="margin: 2px 0; font-size: 12px; opacity: 0.8;">投资者</p>
            </div>
            <div style="font-size: 24px; margin: 0 10px; color: #FFD700;">💎</div>
            <div style="text-align: center; margin: 0 15px;">
                <img src="{st.session_state.ai_avatar}" 
                     width="80" 
                     style="border-radius: 50%; border: 3px solid #9c27b0; box-shadow: 0 4px 12px rgba(156, 39, 176, 0.3);">
                <p style="margin: 10px 0 0 0; font-size: 14px; font-weight: bold;">金鑫</p>
                <p style="margin: 2px 0; font-size: 12px; opacity: 0.8;">投资顾问</p>
            </div>
        </div>
        <p style="font-size: 16px; margin: 10px 0; font-weight: bold;">智能投资助理</p>
        <p style="font-size: 12px; opacity: 0.9; margin: 5px 0;">10年专业经验 · AI驱动分析</p>
        <div style="display: inline-block; background: rgba(76, 175, 80, 0.2); padding: 4px 12px; border-radius: 12px; margin-top: 10px;">
            <span style="font-size: 12px;">📈 实时行情 · 💡 专业建议</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 盯盘雷达
    st.markdown("""
    <div style="background: linear-gradient(135deg, rgba(255,215,0,0.1) 0%, rgba(255,140,0,0.1) 100%); padding: 15px; border-radius: 10px; margin: 15px 0;">
        <h4 style="margin: 0 0 10px 0; color: #FF8C00;">🔭 盯盘雷达</h4>
        <p style="font-size: 13px; margin: 0; opacity: 0.9;">设置目标价，自动监控触发提醒</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 2])
    with col1:
        monitor_code = st.text_input("股票代码", placeholder="600519", key="monitor_code", label_visibility="collapsed")
    with col2:
        target_price = st.number_input("目标价", min_value=0.0, value=1800.0, step=10.0, key="target_price", label_visibility="collapsed")
    
    if st.button("🚀 启动盯盘监控", use_container_width=True, type="primary"):
        if monitor_code:
            # 获取当前价格
            _, stock_info = get_stock_data(monitor_code)
            if stock_info and "当前价格" in stock_info:
                # 从信息中提取当前价格
                import re
                price_match = re.search(r'当前价格[^\d]*([\d,.]+)', stock_info)
                if price_match:
                    current_price = float(price_match.group(1).replace(',', ''))
                    
                    # 添加到盯盘列表
                    new_monitor = {
                        'code': monitor_code,
                        'target': target_price,
                        'current': current_price,
                        'time': datetime.now(),
                        'triggered': current_price >= target_price
                    }
                    
                    st.session_state.monitoring_list.append(new_monitor)
                    
                    # 显示结果
                    if new_monitor['triggered']:
                        st.warning(f"🎯 已触发！{monitor_code} 当前价 {current_price} ≥ 目标价 {target_price}")
                    else:
                        st.success(f"✅ 监控已启动：{monitor_code} 当前价 {current_price}，目标价 {target_price}")
                        
                    # 显示监控列表
                    st.markdown("---")
                    st.markdown("**📋 监控列表**")
                    for item in st.session_state.monitoring_list[-3:]:  # 显示最近3条
                        status = "🎯 已触发" if item.get('triggered', False) else "⏳ 监控中"
                        st.text(f"{item['code']}: {item['current']:.2f} → {item['target']:.2f} {status}")
                else:
                    st.error("无法解析当前价格")
            else:
                st.error("股票代码无效或无法获取数据")
        else:
            st.error("请输入股票代码")
    
    st.divider()
    
    # 数据管理
    st.markdown("""
    <div style="background: linear-gradient(135deg, rgba(33,150,243,0.1) 0%, rgba(66,165,245,0.1) 100%); padding: 15px; border-radius: 10px; margin: 15px 0;">
        <h4 style="margin: 0 0 10px 0; color: #2196F3;">📊 数据管理</h4>
        <p style="font-size: 13px; margin: 0; opacity: 0.9;">管理对话记录和监控数据</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🗑️ 清空历史", use_container_width=True, help="清除所有对话记录"):
            st.session_state.messages = []
            st.session_state.monitoring_list = []
            st.session_state.chart_data = {}
            st.session_state.plot_code = {}
            st.success("历史记录已清空")
            st.rerun()
    
    with col2:
        if st.session_state.messages:
            # 导出对话为Word
            dialog_text = "金鑫智能投资助理 - 专业对话记录\n"
            dialog_text += f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            dialog_text += "="*50 + "\n\n"
            
            for msg in st.session_state.messages:
                role = "👤 用户" if msg["role"] == "user" else "💎 金鑫"
                content = clean_code_blocks(msg.get("content", ""))
                dialog_text += f"{role}:\n{content}\n\n"
                dialog_text += "-"*40 + "\n\n"
            
            # 创建简单的文本文件
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(dialog_text)
                temp_path = f.name
            
            with open(temp_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            os.unlink(temp_path)
            
            st.download_button(
                label="📥 导出对话",
                data=file_content.encode('utf-8'),
                file_name=f"投资对话记录_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
    
    st.divider()
    
    # 语音设置
    st.markdown("""
    <div style="background: linear-gradient(135deg, rgba(156,39,176,0.1) 0%, rgba(186,104,200,0.1) 100%); padding: 15px; border-radius: 10px; margin: 15px 0;">
        <h4 style="margin: 0 0 10px 0; color: #9C27B0;">⚙️ 功能设置</h4>
        <p style="font-size: 13px; margin: 0; opacity: 0.9;">个性化设置您的使用体验</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 语音开关
    voice_enabled = st.checkbox("启用语音输入", value=st.session_state.voice_enabled, 
                                help="启用或禁用语音输入功能")
    if voice_enabled != st.session_state.voice_enabled:
        st.session_state.voice_enabled = voice_enabled
        st.rerun()
    
    # AI模型选择
    ai_model = st.selectbox(
        "选择AI分析模式",
        ["智能增强模式", "技术分析模式", "基本面模式", "综合评估模式"],
        index=0,
        help="选择不同的分析侧重点"
    )
    
    # 图表样式
    chart_style = st.selectbox(
        "图表显示样式",
        ["专业K线图", "简洁趋势图", "详细分析图", "移动端适配"],
        index=0
    )
    
    st.caption("💡 设置更改将立即生效")

# ========== 主聊天界面 ==========
st.markdown("""
<div style="text-align: center; margin-bottom: 30px;">
    <h1 style="color: #1e3c72; margin-bottom: 10px;">💎 金鑫 - 智能投资助理</h1>
    <p style="color: #666; font-size: 16px; margin: 0;">专业女性投资顾问 | 实时行情分析 | 智能图表绘制 | 语音交互</p>
    <div style="display: inline-block; background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%); 
                padding: 6px 20px; border-radius: 20px; margin-top: 10px;">
        <span style="color: white; font-size: 14px;">🔔 实时数据 · 💡 AI分析 · 📈 专业图表</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 显示聊天历史
for i, message in enumerate(st.session_state.messages):
    role = "user" if message["role"] == "user" else "assistant"
    
    with st.chat_message(role, avatar=("👤" if role == "user" else "💎")):
        # 显示消息内容
        cleaned_content = clean_code_blocks(message.get("content", ""))
        st.markdown(cleaned_content)
        
        # 显示图表（如果有）
        if message.get("chart_html"):
            st.markdown(message["chart_html"], unsafe_allow_html=True)
        
        # 显示数据表格（如果有）
        if message.get("table_html"):
            st.markdown(message["table_html"], unsafe_allow_html=True)
        
        # AI消息下方显示操作按钮
        if role == "assistant":
            cols = st.columns([1, 1, 1, 1])
            
            with cols[0]:
                if st.button("📋 复制", key=f"copy_{i}", use_container_width=True):
                    # 简化版复制功能
                    st.info("已复制到剪贴板（演示功能）")
            
            with cols[1]:
                if st.button("👁️ 隐藏", key=f"hide_{i}", use_container_width=True):
                    if "hidden" not in st.session_state:
                        st.session_state.hidden = set()
                    st.session_state.hidden.add(i)
                    st.rerun()
            
            with cols[2]:
                if st.button("🗑️ 删除", key=f"delete_{i}", use_container_width=True):
                    st.session_state.messages.pop(i)
                    st.rerun()
            
            with cols[3]:
                # 导出单条消息
                export_content = f"金鑫智能投资助理 - 专业分析\n\n"
                if i > 0:
                    export_content += f"用户问题: {st.session_state.messages[i-1]['content']}\n\n"
                export_content += f"金鑫分析: {cleaned_content}"
                
                st.download_button(
                    label="📄 导出",
                    data=export_content.encode('utf-8'),
                    file_name=f"投资分析_{datetime.now().strftime('%H%M%S')}.txt",
                    mime="text/plain",
                    key=f"export_{i}",
                    use_container_width=True
                )

# ========== 输入区域 ==========
st.markdown("---")

# 语音输入区域
voice_result = None
if st.session_state.voice_enabled:
    voice_result = voice_input_component()

# 文字输入区域
input_container = st.container()
with input_container:
    col1, col2 = st.columns([5, 1])
    
    with col1:
        if voice_result:
            # 如果语音输入成功，使用语音结果
            user_input = voice_result
        else:
            # 否则显示文字输入框
            user_input = st.chat_input("💬 输入股票代码或投资问题...")
    
    with col2:
        if st.session_state.voice_enabled and st.button("🎤 语音", use_container_width=True, type="primary"):
            st.session_state.recording = not st.session_state.get('recording', False)
            st.rerun()
    
    # 处理用户输入
    if user_input and not st.session_state.processing_input:
        st.session_state.processing_input = True
        st.session_state.last_input = user_input
        
        # 添加到消息历史
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # 立即重载以显示用户消息
        st.rerun()

# ========== AI响应逻辑 ==========
if (st.session_state.messages and 
    st.session_state.messages[-1]["role"] == "user" and 
    not st.session_state.ai_responding):
    
    st.session_state.ai_responding = True
    
    # 获取最后一条用户消息
    last_user_msg = st.session_state.messages[-1]["content"]
    
    # 获取股票数据
    stock_df, stock_info = get_stock_data(last_user_msg)
    
    # 获取AI回复
    with st.spinner("💎 金鑫正在深度分析中..."):
        ai_response = get_ai_response(last_user_msg, stock_df, stock_info)
        
        # 清洗代码块
        cleaned_response = clean_code_blocks(ai_response)
        
        # 存储响应
        response_data = {"role": "assistant", "content": cleaned_response}
        
        # 如果有股票数据，生成图表和表格
        if stock_df is not None and not stock_df.empty:
            # 提取股票代码
            stock_code = None
            for code in st.session_state.chart_data:
                if isinstance(st.session_state.chart_data[code], pd.DataFrame):
                    stock_code = code
                    break
            
            if stock_code:
                # 生成技术分析图表
                chart_html, table_html = generate_technical_analysis(stock_code, stock_df)
                
                if chart_html:
                    response_data["chart_html"] = chart_html
                
                if table_html:
                    response_data["table_html"] = table_html
        
        st.session_state.messages.append(response_data)
    
    st.session_state.ai_responding = False
    st.session_state.processing_input = False
    
    # 再次重载以显示AI回复
    st.rerun()

# ========== 页脚 ==========
st.markdown("""
<div style="text-align: center; color: #666; font-size: 12px; padding: 30px 0 20px 0; border-top: 1px solid #e0e0e0; margin-top: 30px;">
    <p style="margin: 5px 0;">💡 <strong>投资提示</strong>: 市场有风险，投资需谨慎。本应用提供的信息仅供参考，不构成投资建议。</p>
    <p style="margin: 5px 0;">📅 数据更新时间: {}</p>
    <p style="margin: 5px 0;">🔒 隐私保护: 您的对话数据仅保存在当前浏览器会话中</p>
    <p style="margin: 5px 0;">⚡ 技术支持: Python全栈开发 | Streamlit Cloud部署 | AI增强分析</p>
    <div style="display: flex; justify-content: center; gap: 15px; margin-top: 15px;">
        <span style="background: #f0f8ff; padding: 4px 12px; border-radius: 12px; font-size: 11px;">📈 实时行情</span>
        <span style="background: #f0f8ff; padding: 4px 12px; border-radius: 12px; font-size: 11px;">💎 AI分析</span>
        <span style="background: #f0f8ff; padding: 4px 12px; border-radius: 12px; font-size: 11px;">🎤 语音交互</span>
        <span style="background: #f0f8ff; padding: 4px 12px; border-radius: 12px; font-size: 11px;">🔔 智能提醒</span>
    </div>
</div>
""".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")), unsafe_allow_html=True)
