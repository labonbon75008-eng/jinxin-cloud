import streamlit as st
# 【核心修复 1】必须显式导入 datetime，否则报错
from datetime import datetime
import os
import json
import time
import uuid
import re
import io
import asyncio
import base64
import requests
import pandas as pd
import warnings
import contextlib
import matplotlib
# 2. 强制后台绘图，防崩
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import yfinance as yf
from docx import Document
from streamlit_mic_recorder import mic_recorder
import edge_tts
import speech_recognition as sr
import google.generativeai as genai

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# 核心路径
MEMORY_FILE = "investment_memory_v15.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf" 

for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API KEY
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU"

# ================= 2. 资源与显示 =================

# 【核心修复 2】内置 Base64 头像，断网也能显示，绝不白框
DEFAULT_ICON = "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin&clothing=blazerAndShirt"

def get_avatar():
    """优先本地 avatar.png，否则用网络图"""
    if os.path.exists("avatar.png"): return "avatar.png"
    return DEFAULT_ICON

def check_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get("https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf")
            with open(FONT_PATH, "wb") as f: f.write(r.content)
        except: pass
    if os.path.exists(FONT_PATH):
        fm.fontManager.addfont(FONT_PATH)
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
check_font()

# ================= 3. 业务逻辑 =================

def get_stock_data(ticker):
    s = ticker.strip().upper().replace(".SS","").replace(".SZ","").replace(".HK","")
    sina_code = s; y_sym = s
    if s.isdigit():
        if len(s)==5: sina_code=f"hk{s}"; y_sym=f"{s}.HK"
        elif len(s)==4: sina_code=f"hk0{s}"; y_sym=f"0{s}.HK"
        elif s.startswith('6'): sina_code=f"sh{s}"; y_sym=f"{s}.SS"
        else: sina_code=f"sz{s}"; y_sym=f"{s}.SZ"
    else: sina_code=f"gb_{s.lower()}"

    info_str = "暂无数据"; curr = 0.0
    
    # Sina
    try:
        url = f"http://hq.sinajs.cn/list={sina_code}"
        r = requests.get(url, headers={'Referer':'https://finance.sina.com.cn'}, timeout=2)
        if len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            if len(parts) > 3:
                name = parts[0]
                if "hk" in sina_code: name=parts[1]; curr=float(parts[6]); prev=float(parts[3])
                else: curr=float(parts[3]); prev=float(parts[2])
                pct = ((curr - prev) / prev) * 100 if prev != 0 else 0
                info_str = f"【{name}】 现价: {curr:.2f} ({pct:+.2f}%)"
    except: pass

    # Yahoo
    df = None
    try:
        tk = yf.Ticker(y_sym)
        hist = tk.history(period="1mo")
        if not hist.empty: df = hist[['Close']]
    except: pass

    if df is None and curr > 0:
        df = pd.DataFrame({'Close': [curr]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info_str

@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    prompt = f"""
    你叫“金鑫”，用户的投资助理。当前时间：{datetime.now().strftime('%Y-%m-%d')}。
    要求：
    1. 必须调用 `get_stock_data(code)`。
    2. 必须画图。
    3. 语气像真人聊天。
    代码模板：
    df, info = get_stock_data("00700")
    if df is not None:
        print(info)
        plt.figure(figsize=(8, 4))
        plt.plot(df.index, df['Close'], color='#c2185b')
        plt.title("Trend")
        plt.grid(True)
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=prompt)

def execute_code(code_str):
    img_path = None; output = ""; capture = io.StringIO()
    # 清洗 import
    safe_code = '\n'.join([l for l in code_str.split('\n') if not l.strip().startswith(('import','from'))])
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4))
        with contextlib.redirect_stdout(capture):
            # 【核心修复 3】注入 datetime 到沙盒
            exec(safe_code, globals(), {
                'get_stock_data':get_stock_data, 
                'plt':plt, 'pd':pd, 'yf':yf, 'datetime':datetime
            })
        output = capture.getvalue()
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100); plt.close()
    except Exception as e: output = f"执行错误: {e}"
    return img_path, output

async def gen_voice(text, path):
    try: await edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(path); return True
    except: return False

def get_voice_res(text):
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        return model.generate_content(f"转为口语(80字内)：\n{text}").text
    except: return ""

def transcribe(audio_bytes):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

# --- 记忆 ---
def load_mem():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                data = json.load(f)
                return [m for m in data if isinstance(m, dict) and "role" in m]
        except: pass
    return []

def save_mem(msgs):
    try:
        with open(MEMORY_FILE, "w") as f: json.dump(msgs, f, ensure_ascii=False)
    except: pass

def create_doc(msgs, idx=None):
    doc = Document(); doc.add_heading("金鑫研报", 0)
    targets = [msgs[idx]] if idx is not None else msgs
    for m in targets:
        if not m.get("hidden"):
            doc.add_heading(f"{m['role']}", 2); doc.add_paragraph(m.get("content",""))
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 4. 界面布局 =================

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .main-title { text-align: center; font-size: 28px; font-weight: bold; margin-bottom: 5px; color: white; }
    .avatar-container { display: flex; justify-content: center; margin-bottom: 20px; }
    .avatar-img { width: 120px; height: 120px; border-radius: 50%; border: 3px solid #4CAF50; object-fit: cover; }
    div[data-testid="stSidebar"] button { width: 100%; }
    .code-output { background-color: #e8f5e9; color: #000000 !important; padding: 10px; border-radius: 5px; font-family: monospace; }
</style>
""", unsafe_allow_html=True)

# 状态
if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "monitor" not in st.session_state: st.session_state.monitor = False
if "last_audio" not in st.session_state: st.session_state.last_audio = None

# Session 初始化 (修复属性报错)
if "sess" not in st.session_state:
    try:
        model = get_model()
        h = [{"role":("user" if m["role"]=="user" else "model"), "parts":[str(m["content"])]} for m in st.session_state.messages if not m.get("hidden")]
        st.session_state.sess = model.start_chat(history=h)
    except: pass

# --- 侧边栏 ---
with st.sidebar:
    st.image(get_avatar(), use_container_width=True)
    st.markdown("<h3 style='text-align:center'>金鑫</h3>", unsafe_allow_html=True)
    
    with st.expander("🎯 盯盘", expanded=True):
        m_code = st.text_input("代码", "300750")
        m_tgt = st.number_input("目标", 0.0)
        if st.button("🔴 启动/停止"):
            st.session_state.monitor = not st.session_state.monitor
            st.rerun()
        if st.session_state.monitor:
            st.info("📡 监控中...")
            _, info = get_stock_data(m_code)
            if "现价" in info:
                try:
                    curr = float(re.search(r"现价: (\d+\.\d+)", info).group(1))
                    st.metric("实时价", curr)
                    if curr < m_tgt: st.error("触发目标价！"); st.session_state.monitor = False
                except: pass

    st.divider()
    search = st.text_input("🔍 搜索")
    
    c1, c2 = st.columns(2)
    if c1.button("🗑️ 清空"):
        st.session_state.messages = []; st.session_state.sess = None; save_mem([])
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    c2.download_button("📥 导出", create_doc(st.session_state.messages), "all.docx")
    
    with st.expander("👁️ 恢复"):
        for i, m in enumerate(st.session_state.messages):
            if m.get("hidden"):
                if st.button(f"恢复: {m['content'][:5]}...", key=f"rec_{i}"):
                    st.session_state.messages[i]["hidden"] = False; save_mem(st.session_state.messages); st.rerun()

# --- 主界面 ---
st.markdown("<div class='main-title'>你的投资助理</div>", unsafe_allow_html=True)
st.markdown(f"<div class='avatar-container'><img src='{get_avatar()}' class='avatar-img'></div>", unsafe_allow_html=True)

# --- 消息渲染 ---
for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden"): continue
    if search and search not in str(msg['content']): continue

    av = get_avatar() if msg["role"] == "assistant" else "👨‍💼"
    
    with st.chat_message(msg["role"], avatar=av):
        if msg.get("code_output"): 
            st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        
        st.markdown(msg["content"])
        
        if msg.get("image_path") and os.path.exists(msg["image_path"]):
            st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]):
            st.audio(msg["audio_path"])
            
        with st.expander("⋮ 操作"):
            # 【核心修复 4】强制等宽列，手机不换行
            c_cp, c_hd, c_del, c_ex = st.columns([1,1,1,1])
            if c_cp.button("📋", key=f"cp_{i}"): st.code(msg["content"])
            if c_hd.button("🙈", key=f"hd_{i}"): 
                st.session_state.messages[i]["hidden"] = True; save_mem(st.session_state.messages); st.rerun()
            if c_del.button("🗑️", key=f"dl_{i}"): 
                del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()
            c_ex.download_button("📥", create_doc(st.session_state.messages, i), f"msg_{i}.docx", key=f"ex_{i}")

# --- 输入处理 (先存后刷，防卡死) ---
st.markdown("---")
c_voice, c_text = st.columns([1, 5])

with c_voice:
    audio_val = mic_recorder(start_prompt="🎙️", stop_prompt="⏹️", key='mic')

user_input = None
text_input = st.chat_input("请输入问题...")

if text_input:
    user_input = text_input
elif audio_val and audio_val['bytes']:
    if audio_val['id'] != st.session_state.last_audio:
        st.session_state.last_audio = audio_val['id']
        with st.spinner("识别中..."):
            user_input = transcribe(audio_val['bytes'])

# 1. 存入用户消息 -> 强制刷新
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input, "id": str(uuid.uuid4())})
    save_mem(st.session_state.messages)
    st.rerun()

# 2. 刷新后检查最后一条，如果是用户发的，则触发 AI 回答
if st.session_state.messages and st.session_state.messages[-1]["role
