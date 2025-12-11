import streamlit as st
import google.generativeai as genai
import os
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from docx import Document
from docx.shared import Inches
import re
import json
import time
import io
import uuid
import shutil
from datetime import datetime, timedelta
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
import asyncio
import edge_tts
import requests
import pandas as pd
import warnings
import contextlib
import sys
import yfinance as yf
from PIL import Image
import random

# ================= 1. 云端环境配置 =================
warnings.filterwarnings("ignore")

# API KEY 配置 (优先 Secrets)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.error("❌ 未检测到 API Key，请在 Streamlit Secrets 中配置 GEMINI_API_KEY")
    st.stop()

MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"

for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

st.set_page_config(page_title="金鑫 - 云端私人顾问", page_icon="👩‍💼", layout="wide")

# ================= 2. UI 美化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    /* 头像样式增强 */
    div[data-testid="stSidebar"] img {
        border-radius: 50%;
        border: 3px solid #4CAF50;
        box-shadow: 0 4px 10px rgba(0,0,0,0.5);
        object-fit: cover;
    }
    
    /* 顶部标题区头像 */
    div[data-testid="stImage"] img {
        border-radius: 12px;
    }

    .stChatMessage { background-color: rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 10px; margin-bottom: 10px; }
    mark { background-color: #ffeb3b; color: #000000 !important; border-radius: 4px; padding: 0.2em; font-weight: bold; }
    .code-output { background-color: #e8f5e9; color: #000000 !important; padding: 15px; border-radius: 8px; border-left: 6px solid #2e7d32; font-family: 'Consolas', monospace; margin-bottom: 10px; font-size: 0.95em; }
    .monitor-box { border: 2px solid #ff5722; background-color: #fff3e0; padding: 10px; border-radius: 10px; text-align: center; color: #d84315; font-weight: bold; font-size: 0.9em; margin-bottom: 10px; }
    
    div[data-testid="stButton"] button { white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; }
</style>
""", unsafe_allow_html=True)

# ================= 3. 核心功能函数 =================

# --- 图片智能加载 (修复白块问题) ---
def get_avatar_path(base_name):
    """
    智能查找图片路径 (解决Linux大小写敏感问题)
    """
    # 穷举所有可能的后缀组合
    extensions = ["png", "PNG", "jpg", "JPG", "jpeg", "JPEG"]
    
    # 1. 先找 base_name (比如 'avatar')
    for ext in extensions:
        path = f"{base_name}.{ext}"
        if os.path.exists(path): return path
        
    # 2. 如果没找到，尝试首字母大写 (比如 'Avatar')
    for ext in extensions:
        path = f"{base_name.capitalize()}.{ext}"
        if os.path.exists(path): return path
        
    return None

# --- 数据抓取 (新浪源救场) ---
def get_sina_code(symbol):
    """代码转换：通用 -> 新浪格式"""
    s = symbol.strip().upper().replace(".SS", "").replace(".SZ", "").replace(".HK", "")
    if s.isdigit():
        if len(s) == 5: return f"hk{s}" 
        if len(s) == 4: return f"hk0{s}" 
        if len(s) == 6:
            if s.startswith('6'): return f"sh{s}"
            if s.startswith('0') or s.startswith('3'): return f"sz{s}"
            if s.startswith('8') or s.startswith('4'): return f"bj{s}"
    return f"sh{s}" if s.isdigit() else s

def get_stock_data_cloud(ticker_symbol):
    """
    云端数据抓取策略：
    1. 优先用新浪接口 (hq.sinajs.cn) 获取实时价格，因为它不限流且速度极快。
    2. 如果需要历史数据画图，再尝试 Yahoo，但也加了重试机制。
    """
    sina_code = get_sina_code(ticker_symbol)
    
    # --- 步骤 1: 获取实时数据 (新浪) ---
    info_str = "暂无数据"
    current_price = 0.0
    
    try:
        url = f"http://hq.sinajs.cn/list={sina_code}"
        # 伪装 Headers
        headers = {'Referer': 'https://finance.sina.com.cn'}
        r = requests.get(url, headers=headers, timeout=2)
        
        if '=""' not in r.text and len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            name = parts[0]
            current_price = float(parts[3])
            prev_close = float(parts[2])
            
            # 计算涨跌
            change = current_price - prev_close
            pct = (change / prev_close) * 100 if prev_close != 0 else 0
            
            # 格式化日期
            date_str = parts[30] + " " + parts[31] if len(parts) > 30 else datetime.now().strftime("%Y-%m-%d")
            
            info_str = f"【{name}】 现价: {current_price:.2f} ({pct:+.2f}%) | 时间: {date_str}"
    except Exception as e:
        print(f"Sina Error: {e}")

    # --- 步骤 2: 获取历史数据画图 (Yahoo) ---
    # 如果新浪成功拿到了名字，我们还是尝试用 Yahoo 画个图，但如果不通也无所谓，至少有报价了
    df = None
    try:
        # Yahoo 代码转换
        y_sym = ticker_symbol
        if y_sym.isdigit():
            if y_sym.startswith('6'): y_sym += ".SS"
            elif y_sym.startswith('0') or y_sym.startswith('3'): y_sym += ".SZ"
            elif len(y_sym) == 5: y_sym += ".HK"
        
        # 尝试获取 (带 User-Agent 防止 429)
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        
        ticker = yf.Ticker(y_sym, session=session)
        hist = ticker.history(period="5d", interval="1d")
        
        if not hist.empty:
            df = hist[['Close']]
            # 如果新浪没拿到数据，用 Yahoo 的补救
            if current_price == 0:
                last = df['Close'].iloc[-1]
                info_str = f"【Yahoo数据】 收盘价: {last:.2f} (新浪接口暂不可用)"
    except:
        pass # 画图失败不影响报价

    if current_price != 0 or df is not None:
        return df, info_str
    
    return None, f"数据全线获取失败 ({ticker_symbol})，请检查代码是否正确"

# --- 语音合成 ---
async def generate_audio_edge(text, output_file):
    try:
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(output_file)
        return True
    except: return False

def save_audio_cloud(text, output_path):
    try:
        asyncio.run(generate_audio_edge(text, output_path))
        return True
    except: return False

def transcribe_audio(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source: audio_data = r.record(source)
        return r.recognize_google(audio_data, language='zh-CN')
    except: return None

def get_spoken_response(text_analysis):
    if not text_analysis: return ""
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        prompt = f"你是金鑫。请将此内容转为80字以内的口语，像真人一样交流：\n{text_analysis}"
        response = model.generate_content(prompt)
        return response.text
    except: return ""

# --- 模型配置 ---
current_time_str = datetime.now().strftime("%Y年%m月%d日")
SYSTEM_INSTRUCTION = f"""
你叫“金鑫”，用户的专属私人财富合伙人。当前日期：{current_time_str}。

【能力】
查询价格时，请编写代码调用 `get_stock_data_cloud(ticker)`。
A股代码直接写数字 (如 600309)，美股直接写代码 (如 AAPL)。

【代码模板】
ticker = "300750" # 宁德时代
df, info = get_stock_data_cloud(ticker)

if df is not None:
    print(info)  # 直接打印 info 字符串即可
    plt.figure(figsize=(10, 5))
    plt.plot(df.index, df['Close'], label='Close', color='#c2185b') 
    plt.title(f"{{ticker}} Trend")
    plt.grid(True, alpha=0.3)
else:
    print(f"数据不可用: {{info}}")
"""

@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    return genai.GenerativeModel(model_name="gemini-3-pro-preview", system_instruction=SYSTEM_INSTRUCTION)

# --- 基础 CRUD ---
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding='utf-8') as f: return json.load(f)
        except: pass
    return []

def save_memory(messages):
    try:
        with open(MEMORY_FILE, "w", encoding='utf-8') as f: json.dump(messages, f, ensure_ascii=False, indent=2)
    except: pass

def delete_message(msg_id):
    for i, msg in enumerate(st.session_state.messages):
        if msg["id"] == msg_id:
            del st.session_state.messages[i]; save_memory(st.session_state.messages); st.rerun(); break

def toggle_hidden(msg_id):
    for msg in st.session_state.messages:
        if msg["id"] == msg_id:
            msg["hidden"] = not msg.get("hidden", False); save_memory(st.session_state.messages); st.rerun(); break

def execute_local_code_and_save(code_str):
    image_path = None; text_output = ""; output_capture = io.StringIO()
    try:
        plt.clf(); plt.figure(figsize=(10, 5), dpi=100) 
        local_vars = {
            'get_stock_data_cloud': get_stock_data_cloud,
            'plt': plt, 'pd': pd, 'yf': yf
        }
        with contextlib.redirect_stdout(output_capture):
            exec(code_str, globals(), local_vars)
        text_output = output_capture.getvalue()
        if plt.get_fignums():
            fig = plt.gcf()
            filename = f"chart_{int(time.time())}.png"
            image_path = os.path.join(CHARTS_DIR, filename)
            fig.savefig(image_path, format="png", bbox_inches='tight'); plt.close(fig)
    except Exception as e: text_output = f"执行异常: {str(e)}"
    return image_path, text_output

def create_word_doc(messages):
    doc = Document(); doc.add_heading("金鑫财富报告", 0)
    for msg in messages:
        if msg.get("hidden", False): continue
        role = "金鑫" if msg["role"] == "assistant" else "客户"
        doc.add_heading(f"{role} - {msg.get('timestamp','')}", level=2)
        if msg.get("code_output"): doc.add_paragraph(f"【数据】\n{msg['code_output']}")
        if msg["content"]:
            clean = re.sub(r'```python.*?```', '', msg["content"], flags=re.DOTALL)
            doc.add_paragraph(clean.strip())
        if msg.get("image_path") and os.path.exists(msg["image_path"]):
            try: doc.add_picture(msg["image_path"], width=Inches(5))
            except: pass
    bio = io.BytesIO(); doc.save(bio); bio.seek(0); return bio

# ================= 4. 界面主逻辑 =================

if "messages" not in st.session_state: st.session_state.messages = load_memory()
if "chat_session" not in st.session_state or st.session_state.chat_session is None:
    try:
        model = get_model()
        history = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in st.session_state.messages if not m.get("hidden", False)]
        st.session_state.chat_session = model.start_chat(history=history)
    except: pass

# 状态初始化
if "search_idx" not in st.session_state: st.session_state.search_idx = 0
if "last_search_query" not in st.session_state: st.session_state.last_search_query = ""
if "trigger_scroll" not in st.session_state: st.session_state.trigger_scroll = False
if "monitor_active" not in st.session_state: st.session_state.monitor_active = False

# 智能加载头像 (不区分大小写)
ai_avatar = get_avatar_path("avatar") 
user_avatar = get_avatar_path("user")

# 默认网络备用图
DEFAULT_AI_URL = "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin&clothing=blazerAndShirt&hairColor=black&top=longHairStraight"

# --- 侧边栏 ---
with st.sidebar:
    # 头像显示区
    if ai_avatar:
        st.image(ai_avatar, use_container_width=True, caption="👩‍💼 金鑫 - 高级合伙人")
    else:
        st.image(DEFAULT_AI_URL, use_container_width=True, caption="👩‍💼 金鑫 (默认)")
        st.warning("⚠️ 未检测到 avatar.png，请检查 GitHub 文件名是否正确 (区分大小写)。")

    st.markdown("---")

    # 1. 盯盘
    with st.expander("🎯 价格雷达 (盯盘)", expanded=False):
        monitor_ticker = st.text_input("代码", value="300750", placeholder="如 300750")
        c_m1, c_m2 = st.columns(2)
        monitor_target = c_m1.number_input("目标", value=200.0, step=1.0)
        monitor_type = c_m2.selectbox("条件", ["跌破", "突破"])
        
        if st.button("🔴 启动" if not st.session_state.monitor_active else "⏹️ 停止", type="primary" if not st.session_state.monitor_active else "secondary"):
            st.session_state.monitor_active = not st.session_state
