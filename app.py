import streamlit as st
import pandas as pd
import time
import uuid
import re
import yfinance as yf
import google.generativeai as genai
from datetime import datetime

# ================= 1. 极简配置 (防黑屏) =================
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="📈", layout="wide")

# 强制 CSS 修复
st.markdown("""
<style>
    .main-title { text-align: center; font-size: 26px; font-weight: bold; margin-bottom: 20px; }
    .avatar-img { width: 100px; height: 100px; border-radius: 50%; margin: 0 auto; display: block; }
    /* 隐藏全屏按钮 */
    button[title="View fullscreen"] { display: none; }
</style>
""", unsafe_allow_html=True)

# 核心路径
MEMORY_FILE = "investment_memory_v23.json"

# API KEY
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    else:
        genai.configure(api_key="AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU")
except: pass

# ================= 2. 核心功能 (原生组件版) =================

# 头像
AVATAR_URL = "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin&clothing=blazerAndShirt&hairColor=black&skinColor=light"

# 数据引擎 (带缓存)
@st.cache_data(ttl=60)
def get_market_data(ticker):
    """获取数据，返回原生 DataFrame 供 st.line_chart 使用"""
    # 提取代码
    code_match = re.search(r"\d{6}", str(ticker))
    code = code_match.group() if code_match else "300750"
    
    # 构造 Yahoo 代码
    symbol = f"{code}.SS" if code.startswith('6') else f"{code}.SZ"
    
    try:
        # 获取历史数据
        df = yf.Ticker(symbol).history(period="1mo")
        
        # 获取实时信息 (模拟)
        current = df['Close'].iloc[-1]
        change = (current - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
        
        info = f"代码：{code}\n现价：{current:.2f}\n涨跌：{change:.2f}%"
        return df, info
    except:
        # 兜底数据 (防止黑屏)
        dates = pd.date_range(end=datetime.now(), periods=20)
        df = pd.DataFrame({'Close': [100 + i + (i%3)*2 for i in range(20)]}, index=dates)
        return df, "数据暂时不可用，展示模拟走势。"

# AI 引擎
def get_ai_response(prompt, context):
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        full_prompt = f"""
        你叫金鑫。
        用户问：{prompt}
        数据背景：{context}
        请用亲切的口语简要点评。不要写代码，不要画图代码。
        """
        return model.generate_content(full_prompt).text
    except:
        return "网络波动，但我一直在。"

# ================= 3. 界面逻辑 =================

# 初始化记忆
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 侧边栏 ---
with st.sidebar:
    st.image(AVATAR_URL, width=100)
    st.markdown("<h3 style='text-align:center'>金鑫</h3>", unsafe_allow_html=True)
    if st.button("🗑️ 清空记录", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# --- 主界面 ---
st.markdown("<div class='main-title'>您的全天候投资助理</div>", unsafe_allow_html=True)

# 1. 渲染历史
for msg in st.session_state.messages:
    role = msg["role"]
    av = AVATAR_URL if role == "assistant" else "👨‍💼"
    
    with st.chat_message(role, avatar=av):
        st.write(msg["content"])
        # 如果包含图表数据，直接用原生图表渲染
        if "chart_data" in msg:
            st.line_chart(msg["chart_data"], color="#FF4B4B")

# 2. 输入处理
user_input = st.chat_input("请输入股票代码或问题...")

if user_input:
    # 用户上屏
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # AI 响应
    with st.chat_message("assistant", avatar=AVATAR_URL):
        with st.spinner("分析中..."):
            # 获取数据
            df, info = get_market_data(user_input)
            
            # 获取点评
            ai_text = get_ai_response(user_input, info)
            
            # 显示结果
            st.markdown(ai_text)
            st.line_chart(df['Close'], color="#4CAF50") # 原生图表，极快，不报错
            
            # 存入历史 (注意：存 DataFrame 需要序列化，这里简化为只存当次会话的图表数据)
            # 为了防止 session 膨胀，历史记录里的图表在刷新后可能会消失，这是为了稳定性的权衡
            st.session_state.messages.append({
                "role": "assistant",
                "content": ai_text,
                "chart_data": df['Close']
            })
            
    # 强制刷新
    st.rerun()
