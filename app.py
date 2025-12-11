import streamlit as st
import os
import sys
import time
import json
import uuid
import re
import io
import warnings
import asyncio
import threading
from datetime import datetime, timedelta

# ================= 1. 绝对第一行的配置 (防黑屏) =================
st.set_page_config(page_title="金鑫 - 智能财富合伙人", page_icon="👩‍💼", layout="wide")
warnings.filterwarnings("ignore")

# ================= 2. 紧急修复环境 =================
try:
    import matplotlib
    matplotlib.use('Agg') # 强制后台画图，防崩溃
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    from docx import Document
    from docx.shared import Inches
    from streamlit_mic_recorder import mic_recorder
    import speech_recognition as sr
    import edge_tts
    import requests
    import pandas as pd
    import yfinance as yf
    from PIL import Image
    import google.generativeai as genai
    import contextlib
except ImportError as e:
    st.error(f"环境缺失，请检查 requirements.txt: {e}")
    st.stop()

# ================= 3. 核心变量初始化 =================
MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"

# 自动修复文件夹
for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API KEY 安全读取
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.warning("⚠️ 未配置 Secrets，使用临时 Key (可能不稳定)")
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU"

# ================= 4. 核心功能函数 =================

def load_avatar(filename, default_emoji):
    """智能查找本地头像"""
    extensions = ["png", "jpg", "jpeg", "PNG", "JPG"]
    base = filename.split('.')[0]
    for ext in extensions:
        p = f"{base}.{ext}"
        if os.path.exists(p): return p
    return None

def get_stock_data_v10(ticker_symbol):
    """V10 极速数据引擎 (新浪+Yahoo)"""
    # 1. 格式化代码
    s = ticker_symbol.strip().upper().replace(".SS","").replace(".SZ","").replace(".HK","")
    if s.isdigit():
        if len(s)==5: sina_code = f"hk{s}"
        elif len(s)==4: sina_code = f"hk0{s}"
        elif s.startswith('6'): sina_code = f"sh{s}"
        elif s.startswith('0') or s.startswith('3'): sina_code = f"sz{s}"
        elif s.startswith('8') or s.startswith('4'): sina_code = f"bj{s}"
    else: sina_code = f"sh{s}"

    info_str = "暂无数据"
    current_price = 0.0
    
    # 2. 新浪实时 (极速)
    try:
        url = f"http://hq.sinajs.cn/list={sina_code}"
        r = requests.get(url, headers={'Referer':'https://finance.sina.com.cn'}, timeout=2, proxies={"http":None,"https":None})
        if '=""' not in r.text and len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            name = parts[0]
            current_price = float(parts[3])
            prev = float(parts[2])
            pct = ((current_price - prev) / prev) * 100 if prev != 0 else 0
            t_str = datetime.now().strftime("%H:%M:%S")
            info_str = f"【{name}】 现价: {current_price:.2f} ({pct:+.2f}%) | 时间: {t_str}"
    except: pass

    # 3. Yahoo 历史 (画图用)
    df = None
    try:
        y_sym = ticker_symbol.upper()
        if y_sym.isdigit():
            if y_sym.startswith('6'): y_sym += ".SS"
            elif y_sym.startswith('0'): y_sym += ".SZ"
            elif len(y_sym)==5: y_sym += ".HK"
        
        ticker = yf.Ticker(y_sym)
        hist = ticker.history(period="1mo")
        if not hist.empty: df = hist[['Close']]
    except: pass

    # 4. 兜底画图
    if df is None and current_price > 0:
        df = pd.DataFrame({'Close': [current_price]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info_str

# --- 语音与 AI ---
async def generate_audio_edge(text, output_file):
    try:
        # 使用晓晓女声
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(output_file)
        return True
    except: return False

def save_audio_cloud(text, output_path):
    try: asyncio.run(generate_audio_edge(text, output_path)); return True
    except: return False

def transcribe_audio(audio_bytes):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio_data = r.record(source)
        return r.recognize_google(audio_data, language='zh-CN')
    except: return None

def get_spoken_response(text):
    if not text: return ""
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        response = model.generate_content(f"你是金鑫，转为口语(80字内)：\n{text}")
        return response.text
    except: return ""

# --- 配置 ---
current_date = datetime.now().strftime("%Y-%m-%d")
SYSTEM_INSTRUCTION = f"""
你叫“金鑫”，用户的专属私人财富合伙人。当前日期：{current_date}。
1. 查询价格必须调用 `get_stock_data_v10(ticker)`。
2. A股代码直接写数字。
3. 必须在最后画图。

代码模板：
df, info = get_stock_data_v10("300750")
if df is not None:
    print(info)
    plt.figure(figsize=(10, 4))
    plt.plot(df.index, df['Close'], color='#c2185b')
    plt.title("Trend")
    plt.grid(True)
else:
    print(f"数据失败: {{info}}")
"""

@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    return genai.GenerativeModel(model_name="gemini-3-pro-preview", system_instruction=SYSTEM_INSTRUCTION)

def execute_code(code_str):
    image_path = None; text_output = "无输出"; output_capture = io.StringIO()
    # 清洗代码
    lines = [l for l in code_str.split('\n') if not l.strip().startswith(('import ', 'from '))]
    safe_code = '\n'.join(lines)
    
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(10, 4))
        local_vars = {'get_stock_data_v10': get_stock_data_v10, 'plt': plt, 'pd': pd, 'yf': yf}
        with contextlib.redirect_stdout(output_capture):
            exec(safe_code, globals(), local_vars)
        text_output = output_capture.getvalue()
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            image_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(image_path, bbox_inches='tight'); plt.close()
    except Exception as e: text_output = f"执行错误: {str(e)}"
    return image_path, text_output

# --- 记忆管理 (防崩溃核心) ---
def load_memory_safe():
    data = []
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding='utf-8') as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict) and "role" in item: data.append(item)
        except: pass
    return data

def save_memory(data):
    try:
        with open(MEMORY_FILE, "w", encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
    except: pass

def create_doc(messages):
    doc = Document(); doc.add_heading("金鑫研报", 0)
    for m in messages:
        if isinstance(m, dict) and not m.get("hidden"):
            role = "金鑫" if m["role"]=="assistant" else "客户"
            doc.add_heading(f"{role} - {m.get('timestamp','')}", 2)
            doc.add_paragraph(m.get("content",""))
    bio = io.BytesIO(); doc.save(bio); bio.seek(0); return bio

# ================= 5. 界面逻辑 =================

# 样式
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stSidebar"] img { border-radius: 50%; border: 3px solid #4CAF50; }
    .stChatMessage { background-color: rgba(255, 255, 255, 0.05); }
    .code-output { background-color: #e8f5e9; color: black !important; padding: 10px; border-radius: 5px; }
    .monitor-box { border: 2px solid #ff5722; background-color: #fff3e0; padding: 10px; color: #d84315; text-align: center; }
</style>
""", unsafe_allow_html=True)

# 初始化
if "messages" not in st.session_state: st.session_state.messages = load_memory_safe()
if "last_audio_id" not in st.session_state: st.session_state.last_audio_id = None
if "monitor_active" not in st.session_state: st.session_state.monitor_active = False
if "chat_session" not in st.session_state:
    try:
        model = get_model()
        # 历史记录转文本，防止对象错误
        h_text = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [str(m["content"])]} for m in st.session_state.messages if not m.get("hidden")]
        st.session_state.chat_session = model.start_chat(history=h_text)
    except: pass

# 头像
ai_av = load_avatar("avatar", "👩‍💼")
user_av = load_avatar("user", "👨‍💼")
sb_img = ai_av if ai_av else "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin"

# --- 侧边栏 ---
with st.sidebar:
    st.image(sb_img, use_container_width=True, caption="👩‍💼 金鑫 - 智能顾问")
    
    # 盯盘
    with st.expander("🎯 盯盘雷达", expanded=False):
        m_tick = st.text_input("代码", "300750")
        m_tgt = st.number_input("目标", 200.0)
        m_type = st.selectbox("条件", ["跌破", "突破"])
        if st.button("🚀 启停"):
            st.session_state.monitor_active = not st.session_state.monitor_active
            st.rerun()
        if st.session_state.monitor_active:
            st.markdown("<div class='monitor-box'>📡 监控中...</div>", unsafe_allow_html=True)
            df, info = get_stock_data_v10(m_tick)
            if "现价" in info:
                try:
                    curr = float(re.search(r"现价: (\d+\.\d+)", info).group(1))
                    st.metric("现价", f"{curr}")
                    if (m_type=="跌破" and curr<m_tgt) or (m_type=="突破" and curr>m_tgt):
                        st.error("触发！"); st.session_state.monitor_active = False
                except: pass

    st.divider()
    
    # 搜索
    search = st.text_input("🔍 搜索", placeholder="...", label_visibility="collapsed")
    matches = [i for i, m in enumerate(st.session_state.messages) if isinstance(m, dict) and not m.get("hidden") and search and search in str(m.get("content"))]
    
    # 导出清空
    c1, c2
