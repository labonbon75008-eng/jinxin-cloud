"""
金鑫智能投资助理 - 专业稳定版
专注于股票查询分析的AI助手
"""

import re
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import requests
from datetime import datetime, timedelta
import yfinance as yf
import streamlit as st
import warnings
warnings.filterwarnings('ignore')

# ========== 全局配置 ==========
st.set_page_config(
    page_title="金鑫投资助理",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 深色模式CSS ==========
st.markdown("""
<style>
/* 深色主背景 */
.stApp {
    background-color: #0f172a;
    color: #e2e8f0;
}

/* 深色侧边栏 */
section[data-testid="stSidebar"] {
    background-color: #1e293b !important;
    border-right: 1px solid #334155;
}

/* 侧边栏文本 */
section[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}

/* 输入框 */
.stTextInput input, .stNumberInput input {
    background-color: #334155 !important;
    color: #e2e8f0 !important;
    border: 1px solid #475569 !important;
}

/* 按钮 */
.stButton button {
    background-color: #3b82f6 !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
}

.stButton button:hover {
    background-color: #2563eb !important;
}

/* 聊天消息 */
.stChatMessage {
    padding: 16px;
    border-radius: 10px;
    margin-bottom: 12px;
    max-width: 85%;
}

/* 用户消息 - 深蓝色 */
.stChatMessage[data-testid="stChatMessage"]:nth-child(odd) {
    background-color: #1e40af;
    color: white;
    margin-left: auto;
    border-left: 4px solid #60a5fa;
}

/* AI消息 - 深绿色 */
.stChatMessage[data-testid="stChatMessage"]:nth-child(even) {
    background-color: #064e3b;
    color: white;
    margin-right: auto;
    border-left: 4px solid #10b981;
}

/* 标题 */
h1, h2, h3, h4 {
    color: #e2e8f0 !important;
}

/* 图表容器 */
.chart-box {
    background: #1e293b;
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
    border: 1px solid #334155;
}

/* 数据表格 */
.data-table {
    background: #1e293b;
    border-radius: 8px;
    overflow: hidden;
    margin: 15px 0;
    border: 1px solid #334155;
}

.data-table th {
    background-color: #334155;
    color: #e2e8f0;
    padding: 10px;
}

.data-table td {
    padding: 8px 10px;
    border-bottom: 1px solid #475569;
    color: #cbd5e1;
}

/* 操作按钮 */
.action-buttons {
    display: flex;
    gap: 8px;
    margin-top: 10px;
    flex-wrap: wrap;
}

.action-btn {
    background: #475569 !important;
    color: #e2e8f0 !important;
    border: 1px solid #64748b !important;
    font-size: 12px !important;
    padding: 4px 8px !important;
}

/* 盯盘项 */
.monitor-item {
    background: #334155;
    padding: 10px;
    margin: 8px 0;
    border-radius: 6px;
    border-left: 4px solid #3b82f6;
}

.monitor-triggered {
    border-left-color: #ef4444;
    background: #450a0a;
}
</style>
""", unsafe_allow_html=True)

# ========== 初始化状态 ==========
if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'monitoring' not in st.session_state:
    st.session_state.monitoring = []

if 'processing' not in st.session_state:
    st.session_state.processing = False

if 'stock_cache' not in st.session_state:
    st.session_state.stock_cache = {}

# ========== 股票代码映射 ==========
STOCK_MAP = {
    # A股
    '茅台': '600519.SS', '贵州茅台': '600519.SS',
    '宁德时代': '300750.SZ', 'catl': '300750.SZ',
    '比亚迪': '002594.SZ', 'byd': '002594.SZ',
    '腾讯': '0700.HK', '腾讯控股': '0700.HK',
    '阿里巴巴': '9988.HK', '阿里': '9988.HK', '巴巴': '9988.HK',
    '苹果': 'AAPL', 'apple': 'AAPL',
    '特斯拉': 'TSLA', 'tesla': 'TSLA',
    '微软': 'MSFT', 'microsoft': 'MSFT',
    '谷歌': 'GOOGL', 'google': 'GOOGL',
    '亚马逊': 'AMZN', 'amazon': 'AMZN',
    '英伟达': 'NVDA', 'nvidia': 'NVDA',
    
    # 指数
    '上证': '000001.SS', '上证指数': '000001.SS',
    '深证': '399001.SZ', '深证成指': '399001.SZ',
    '创业': '399006.SZ', '创业板': '399006.SZ',
    '恒生': '^HSI', '恒生指数': '^HSI',
    '标普': '^GSPC', '标普500': '^GSPC',
    '道琼斯': '^DJI', '纳斯达克': '^IXIC',
}

# ========== 核心函数 ==========
def extract_stock_code(text):
    """从文本中提取股票代码"""
    text = text.lower().strip()
    
    # 1. 精确匹配
    for name, code in STOCK_MAP.items():
        if name.lower() == text:
            return code
    
    # 2. 包含匹配（避免模糊匹配导致错误）
    for name, code in STOCK_MAP.items():
        if name.lower() in text and len(name) > 1:  # 避免单字匹配
            return code
    
    # 3. 直接代码匹配
    patterns = [
        (r'\b(\d{6})\.(ss|sz)\b', lambda m: f"{m.group(1)}.{m.group(2).upper()}"),
        (r'\b(\d{6})\b', lambda m: f"{m.group(1)}.SS" if m.group(1).startswith('6') else f"{m.group(1)}.SZ"),
        (r'\b([a-z]{1,5})\b', lambda m: m.group(1).upper()),
        (r'\b(\d{4})\.hk\b', lambda m: f"{m.group(1)}.HK"),
    ]
    
    for pattern, converter in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return converter(match)
    
    return None

def get_stock_info(symbol):
    """获取股票信息"""
    if not symbol:
        return None, "未识别到股票"
    
    # 检查缓存
    cache_key = symbol
    if cache_key in st.session_state.stock_cache:
        cached_time, data = st.session_state.stock_cache[cache_key]
        if (datetime.now() - cached_time).seconds < 300:  # 5分钟缓存
            return data['df'], data['info']
    
    try:
        ticker = yf.Ticker(symbol)
        
        # 获取日线数据
        hist = ticker.history(period='5d')
        if hist.empty:
            return None, f"无法获取 {symbol} 的数据"
        
        # 基本信息
        info = ticker.info
        name = info.get('longName', info.get('shortName', symbol))
        currency = info.get('currency', 'USD')
        
        # 最新数据
        latest = hist.iloc[-1]
        current = latest['Close']
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else latest['Open']
        
        change = current - prev_close
        change_pct = (change / prev_close * 100) if prev_close != 0 else 0
        
        # 构建信息
        info_text = f"""
### 📊 {name} ({symbol})

**当前价格**: {current:.2f} {currency}
**涨跌幅**: {'🟢' if change >= 0 else '🔴'} {change:+.2f} ({change_pct:+.2f}%)
**今日区间**: {latest['Low']:.2f} - {latest['High']:.2f}
**成交量**: {latest['Volume']:,.0f}
**更新时间**: {datetime.now().strftime('%H:%M:%S')}
"""
        
        # 缓存数据
        st.session_state.stock_cache[cache_key] = (
            datetime.now(),
            {'df': hist, 'info': info_text}
        )
        
        return hist, info_text
        
    except Exception as e:
        return None, f"获取数据失败: {str(e)[:50]}"

def create_chart(symbol, df):
    """创建股票图表"""
    if df.empty:
        return None
    
    try:
        fig, ax = plt.subplots(figsize=(10, 5))
        
        # 深色背景
        fig.patch.set_facecolor('#1e293b')
        ax.set_facecolor('#1e293b')
        
        # 价格线
        ax.plot(df.index, df['Close'], color='#60a5fa', linewidth=2, label='收盘价')
        
        # 样式
        ax.set_title(f'{symbol} 价格走势', color='#e2e8f0', fontsize=14, pad=20)
        ax.set_ylabel('价格', color='#cbd5e1')
        ax.set_xlabel('日期', color='#cbd5e1')
        ax.tick_params(colors='#94a3b8')
        ax.grid(True, alpha=0.2, color='#475569')
        ax.legend(facecolor='#334155', edgecolor='#475569', labelcolor='#e2e8f0')
        
        # 保存为Base64
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight', 
                   facecolor='#1e293b', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        
        img_base64 = base64.b64encode(buf.read()).decode()
        return f'<div class="chart-box"><img src="data:image/png;base64,{img_base64}" style="width:100%"></div>'
        
    except Exception as e:
        print(f"图表错误: {e}")
        return None

def generate_analysis(symbol, df, basic_info):
    """生成分析报告"""
    if df.empty:
        return basic_info + "\n\n⚠️ 数据不足，无法进行详细分析"
    
    # 计算技术指标
    prices = df['Close']
    
    analysis = basic_info + "\n\n### 📈 技术分析\n"
    
    if len(prices) >= 5:
        ma5 = prices.rolling(5).mean().iloc[-1]
        current = prices.iloc[-1]
        analysis += f"**5日均线**: {ma5:.2f} ({'高于' if current > ma5 else '低于'}当前价)\n"
    
    if len(prices) >= 20:
        ma20 = prices.rolling(20).mean().iloc[-1]
        analysis += f"**20日均线**: {ma20:.2f} ({'高于' if current > ma20 else '低于'}当前价)\n"
    
    # 趋势判断
    if len(prices) >= 20:
        if current > ma20 * 1.05:
            trend = "上涨趋势"
        elif current < ma20 * 0.95:
            trend = "下跌趋势"
        else:
            trend = "震荡整理"
        analysis += f"**趋势判断**: {trend}\n"
    
    # 简单建议
    analysis += "\n### 💡 操作建议\n"
    
    if '上涨' in analysis:
        analysis += """1. **短线**: 可考虑持有，设好止盈
2. **中线**: 趋势向好，可分批布局
3. **风险**: 注意回调风险，控制仓位"""
    elif '下跌' in analysis:
        analysis += """1. **短线**: 建议观望，等待企稳
2. **中线**: 谨慎操作，控制风险
3. **风险**: 下跌趋势，避免重仓"""
    else:
        analysis += """1. **短线**: 高抛低吸，区间操作
2. **中线**: 等待方向选择
3. **风险**: 震荡行情，严格止损"""
    
    return analysis

# ========== 侧边栏 ==========
with st.sidebar:
    # 头像区域 - 使用emoji
    st.markdown("""
    <div style="text-align: center; padding: 20px 0;">
        <div style="font-size: 48px; margin-bottom: 10px;">💎</div>
        <h3 style="margin: 5px 0;">金鑫</h3>
        <p style="color: #94a3b8; margin: 0;">智能投资助理</p>
        <p style="color: #64748b; font-size: 12px; margin: 5px 0;">专业 · 准确 · 及时</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 盯盘功能
    st.subheader("🔭 价格提醒")
    
    with st.form("monitor_form"):
        stock_input = st.text_input("股票名称/代码", key="monitor_stock")
        target_price = st.number_input("目标价格", min_value=0.0, value=100.0, step=1.0, key="monitor_price")
        
        if st.form_submit_button("设置提醒", use_container_width=True):
            if stock_input:
                symbol = extract_stock_code(stock_input)
                if symbol:
                    df, info = get_stock_info(symbol)
                    if df is not None:
                        current = df['Close'].iloc[-1]
                        
                        st.session_state.monitoring.append({
                            'symbol': symbol,
                            'target': target_price,
                            'current': current,
                            'time': datetime.now(),
                            'triggered': current >= target_price
                        })
                        
                        if current >= target_price:
                            st.warning(f"🎯 已触发！{symbol} 当前价 {current:.2f}")
                        else:
                            st.success(f"✅ 提醒已设置: {symbol}")
                    else:
                        st.error("无法获取股票数据")
                else:
                    st.error("无法识别股票代码")
    
    # 显示提醒列表
    if st.session_state.monitoring:
        st.markdown("**当前提醒**")
        for item in st.session_state.monitoring[-3:]:
            status = "🔴 已触发" if item['triggered'] else "🟡 监控中"
            st.markdown(f"""
            <div class="monitor-item {'monitor-triggered' if item['triggered'] else ''}">
                <strong>{item['symbol']}</strong><br>
                <small>当前: {item['current']:.2f} → 目标: {item['target']:.2f}</small><br>
                <small>{status}</small>
            </div>
            """, unsafe_allow_html=True)
        
        if st.button("清空提醒", use_container_width=True, type="secondary"):
            st.session_state.monitoring = []
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
        if st.button("清除缓存", use_container_width=True, type="secondary"):
            st.session_state.stock_cache = {}
            st.success("缓存已清除")
    
    st.divider()
    
    # 设置
    st.subheader("⚙️ 设置")
    st.caption("当前版本专注于股票查询分析")

# ========== 主界面 ==========
st.title("📈 金鑫智能投资助理")
st.caption("输入股票名称或代码获取实时行情和分析")

# 显示对话历史
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "💎"):
        st.markdown(msg["content"])
        
        # 显示图表
        if msg.get("chart"):
            st.markdown(msg["chart"], unsafe_allow_html=True)
        
        # AI消息的操作按钮
        if msg["role"] == "assistant":
            st.markdown('<div class="action-buttons">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("复制", key=f"copy_{i}"):
                    st.toast("已复制")
            with col2:
                if st.button("删除", key=f"delete_{i}"):
                    st.session_state.messages.pop(i)
                    st.rerun()
            with col3:
                if st.button("停止", key=f"stop_{i}"):
                    st.session_state.processing = False
            st.markdown('</div>', unsafe_allow_html=True)

# ========== 输入处理 ==========
st.divider()

# 输入区域
user_input = st.chat_input("💬 请输入股票名称或代码...")

if user_input and not st.session_state.processing:
    st.session_state.processing = True
    
    # 添加用户消息
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.rerun()

# ========== AI响应 ==========
if (st.session_state.messages and 
    st.session_state.messages[-1]["role"] == "user" and 
    st.session_state.processing):
    
    user_msg = st.session_state.messages[-1]["content"]
    
    # 识别股票
    symbol = extract_stock_code(user_msg)
    
    if symbol:
        # 获取数据
        df, basic_info = get_stock_info(symbol)
        
        if df is not None:
            # 生成分析
            analysis = generate_analysis(symbol, df, basic_info)
            
            # 生成图表
            chart_html = create_chart(symbol, df)
            
            # 构建响应
            response = {"role": "assistant", "content": analysis}
            if chart_html:
                response["chart"] = chart_html
            
            st.session_state.messages.append(response)
        else:
            st.session_state.messages.append({
                "role": "assistant", 
                "content": f"⚠️ 无法获取 {symbol} 的数据，请检查股票代码或稍后重试。"
            })
    else:
        # 如果不是股票查询
        st.session_state.messages.append({
            "role": "assistant",
            "content": """💎 **金鑫投资助理**

我专注于股票行情分析，请告诉我您想查询的股票：

**📊 支持查询：**
- 股票名称：如"宁德时代"、"茅台"、"腾讯"
- 股票代码：如"300750"、"600519"、"AAPL"
- 指数：如"上证指数"、"恒生指数"

**📈 示例：**
- "宁德时代股价"
- "茅台行情分析"
- "AAPL今天走势"

请输入具体的股票名称或代码："""
        })
    
    st.session_state.processing = False
    st.rerun()

# ========== 页脚 ==========
st.divider()
st.markdown(f"""
<div style="text-align: center; color: #64748b; font-size: 12px; padding: 20px 0;">
    <p>📅 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>💡 数据来源: Yahoo Finance • 仅供参考</p>
</div>
""", unsafe_allow_html=True)
