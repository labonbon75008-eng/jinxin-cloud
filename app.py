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
import edge_tts  # 👈 换回了最好听的网络语音
import requests
import pandas as pd
import warnings
import yfinance as yf
from PIL import Image

# ================= 1. 云端环境配置 =================
warnings.filterwarnings("ignore")

# ⚠️ 云端不需要设置代理，直接直连 Google 和 Yahoo
# PROXY_PORT ... (已移除)

# 🔑 从 Streamlit Secrets 读取 Key (更安全)，或者暂时写死在这里
# 建议部署时在 Streamlit 后台填入，这里为了方便先写死，但在公开仓库请注意安全
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU" # 填入你的 Key

MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"

for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

st.set_page_config(page_title="金鑫 - 云端操盘手", page_icon="☁️", layout="wide")

# ================= 2. UI 美化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stSidebar"] div[data-testid="stImage"] img {
        width: 100%; max-width: 100%; object-fit: cover; border-radius: 12px;
    }
    .stChatMessage { background-color: rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 10px; margin-bottom: 10px; }
    .code-output { background-color: #e8f5e9; color: #000000 !important; padding: 15px; border-radius: 8px; border-left: 6px solid #2e7d32; font-family: 'Consolas', monospace; margin-bottom: 10px; font-size: 0.95em; }
    .monitor-box { border: 2px solid #ff5722; background-color: #fff3e0; padding: 10px; border-radius: 10px; text-align: center; color: #d84315; font-weight: bold; font-size: 0.9em; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ================= 3. 核心功能函数 =================

def load_avatar(filename, default_emoji):
    extensions = ["png", "jpg", "jpeg"]
    base_name = filename.split('.')[0]
    for ext in extensions:
        path = f"{base_name}.{ext}"
        if os.path.exists(path):
            try: Image.open(path); return path
            except: pass
    return default_emoji

# --- 云端数据抓取策略 ---
# 云服务器通常在海外，访问 Yahoo (yfinance) 极快且稳定，不需要任何 Hack
# 访问新浪反而可能被拦截，所以策略改为：优先 Yahoo，新浪辅助

def fix_stock_symbol(symbol):
    s = symbol.strip().upper()
    if s.isdigit():
        if s.startswith('6'): return f"{s}.SS"
        if s.startswith('0') or s.startswith('3'): return f"{s}.SZ"
        if len(s) == 5: return f"{s}.HK"
        if len(s) == 4: return f"0{s}.HK"
    return s

def get_stock_data_cloud(ticker_symbol):
    """云端优化版数据抓取"""
    symbol = fix_stock_symbol(ticker_symbol)
    df = None
    info_str = "暂无数据"
    
    # 优先使用 yfinance (在海外服务器极其稳定)
    try:
        ticker = yf.Ticker(symbol)
        # 获取最新即时数据
        hist = ticker.history(period="5d", interval="1d")
        
        if not hist.empty:
            df = hist[['Close']]
            last_price = df['Close'].iloc[-1]
            prev_price = df['Close'].iloc[-2] if len(df) > 1 else last_price
            
            currency = ticker.info.get('currency', '?')
            change_pct = ((last_price - prev_price) / prev_price) * 100
            
            info_str = f"最新价: {last_price:.2f} {currency} ({change_pct:+.2f}%)"
            return df, info_str
    except Exception as e:
        print(f"Yahoo 失败: {e}")

    return None, f"无法获取 {symbol} 数据，请检查代码是否正确"

# --- 语音合成 (Edge-TTS) ---
async def generate_audio_edge(text, output_file):
    """使用微软超逼真语音 (云端可用)"""
    try:
        # zh-CN-XiaoxiaoNeural (女声，知性)
        # zh-CN-YunxiNeural (男声，稳重)
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(output_file)
        return True
    except: return False

def save_audio_cloud(text, output_path):
    """同步包装异步函数"""
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
# 云端不需要手动配置中文字体，Streamlit Cloud 默认支持基本显示
# 如果乱码，通常需要上传字体文件，这里为了简化先忽略

current_time_str = datetime.now().strftime("%Y年%m月%d日")
SYSTEM_INSTRUCTION = f"""
你叫“金鑫”，用户的专属私人财富合伙人。当前日期：{current_time_str}。

【能力】
查询价格时，请编写代码调用 `get_stock_data_cloud(ticker)`。
A股代码直接写数字 (如 600309)，美股直接写代码 (如 AAPL)。

【代码模板】
ticker = "600309"
df, info = get_stock_data_cloud(ticker)

if df is not None:
    print(f"【金鑫云端实盘】{{info}}") 
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

# ================= 4. 界面主逻辑 =================

if "messages" not in st.session_state: st.session_state.messages = load_memory()
if "chat_session" not in st.session_state or st.session_state.chat_session is None:
    try:
        model = get_model()
        history = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in st.session_state.messages if not m.get("hidden", False)]
        st.session_state.chat_session = model.start_chat(history=history)
    except: pass

with st.sidebar:
    user_avatar = load_avatar("user", "👨‍💼")
    ai_avatar = load_avatar("avatar", "👩‍💼")
    
    c_av1, c_av2, c_av3 = st.columns([1, 2, 1])
    with c_av2:
        if os.path.exists("avatar.png"): st.image("avatar.png", use_container_width=True)
        else: st.markdown("<div style='text-align: center; font-size: 60px;'>☁️</div>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>金鑫 - 云端版</h3>", unsafe_allow_html=True)

    if st.button("🗑️ 清空记录", type="primary", use_container_width=True):
        st.session_state.messages = []; st.session_state.chat_session = None
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    
    st.divider()
    text_voice = mic_recorder(start_prompt="🎙️ 语音", stop_prompt="⏹️ 停止", key='rec', format="wav", use_container_width=True)

# Main
st.markdown("<h2 style='text-align: center;'>👩‍💼 金鑫：您的云端财富合伙人</h2>", unsafe_allow_html=True)

for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden", False): continue
    
    current_avatar = ai_avatar if msg["role"] == "assistant" else user_avatar
    with st.chat_message(msg["role"], avatar=current_avatar):
        if msg.get("code_output"):
            st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        
        content = msg["content"]
        clean = re.sub(r'```python.*?```', '', content, flags=re.DOTALL)
        st.markdown(clean, unsafe_allow_html=True)
        
        if msg.get("image_path") and os.path.exists(msg["image_path"]): st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg.get("audio_path")): st.audio(msg["audio_path"], format="audio/wav")

u_in_text = st.chat_input("请问金鑫...")
u_in = None
if text_voice and text_voice['bytes']:
    t = transcribe_audio(text_voice['bytes'])
    if t: u_in = t
elif u_in_text: u_in = u_in_text

if u_in:
    st.session_state.messages.append({"id": str(uuid.uuid4()), "role": "user", "content": u_in, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "hidden": False})
    save_memory(st.session_state.messages)
    st.rerun()

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last = st.session_state.messages[-1]
    with st.chat_message("assistant", avatar=ai_avatar):
        ph = st.empty(); img = None; out = None; txt = ""
        if st.session_state.chat_session:
            with st.spinner("☁️ 云端大脑运算中..."):
                try:
                    resp = st.session_state.chat_session.send_message(last["content"])
                    txt = resp.text
                    codes = re.findall(r'```python(.*?)```', txt, re.DOTALL)
                    if codes: img, out = execute_local_code_and_save(codes[-1])
                    if out: st.markdown(f"<div class='code-output'>{out}</div>", unsafe_allow_html=True)
                    clean = re.sub(r'```python.*?```', '', txt, flags=re.DOTALL)
                    ph.markdown(clean)
                    if img: st.image(img)
                except Exception as e: st.error(f"Error: {e}")
        af = None
        if "异常" not in (out or ""):
            try:
                spoken = get_spoken_response(txt)
                ap = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.wav")
                # 使用 Edge-TTS 生成
                if save_audio_cloud(spoken, ap): st.audio(ap, format="audio/wav"); af = ap
            except: pass
        st.session_state.messages.append({"id": str(uuid.uuid4()), "role": "assistant", "content": txt, "hidden": False, "image_path": img, "audio_path": af, "code_output": out})
        save_memory(st.session_state.messages)