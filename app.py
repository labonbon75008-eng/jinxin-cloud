import streamlit as st
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
# 1. 强制后台绘图
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import yfinance as yf
from docx import Document
from datetime import datetime

# 【防崩导入】语音组件
try:
    from streamlit_mic_recorder import mic_recorder
except ImportError:
    mic_recorder = None

import edge_tts
import speech_recognition as sr
import google.generativeai as genai
from PIL import Image

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# CSS: 强制手机按钮不换行 + 头像优化
st.markdown("""
<style>
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; }
    div[data-testid="stHorizontalBlock"] button { min-width: 60px !important; padding: 0px 5px !important; }
    .main-title { text-align: center; font-size: 26px; font-weight: bold; color: white; margin-bottom: 10px; }
    .avatar-img { 
        width: 120px; height: 120px; 
        border-radius: 50%; 
        border: 3px solid #4CAF50; 
        margin: 0 auto; display: block; 
        object-fit: cover; background-color: #eee;
    }
    button[title="View fullscreen"] { display: none; }
</style>
""", unsafe_allow_html=True)

# 核心路径
MEMORY_FILE = "investment_memory_v24.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf" 

for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# API KEY
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    else:
        genai.configure(api_key="AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU")
except: pass

# ================= 2. 资源管理 =================

def load_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get("https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf", timeout=5)
            with open(FONT_PATH, "wb") as f: f.write(r.content)
        except: pass
    try:
        if os.path.exists(FONT_PATH):
            fm.fontManager.addfont(FONT_PATH)
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False
    except: pass

load_font()

DEFAULT_AVATAR = "https://api.dicebear.com/9.x/avataaars/png?seed=Jinxin&clothing=blazerAndShirt&hairColor=black&skinColor=light&accessories=glasses&top=longHairStraight"

def get_avatar():
    if os.path.exists("avatar.png"): return "avatar.png"
    return DEFAULT_AVATAR

# ================= 3. 核心业务逻辑 =================

# --- A. 数据引擎 ---
def get_stock_data(query):
    s = str(query).strip().upper()
    match = re.search(r"[0-9]{4,6}", s)
    code = match.group() if match else "000001"
    
    info_str = "暂无数据"; curr = 0.0
    
    # 1. Sina
    try:
        sina_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
        if len(code) == 5: sina_code = f"hk{code}"
        
        url = f"http://hq.sinajs.cn/list={sina_code}"
        r = requests.get(url, headers={'Referer':'https://finance.sina.com.cn'}, timeout=2)
        if len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            name = parts[0]
            if len(parts) > 3:
                if "hk" in sina_code: curr = float(parts[6])
                else: curr = float(parts[3])
                info_str = f"【{name}】 现价: {curr}"
    except: pass

    # 2. Yahoo
    df = None
    try:
        ticker = f"{code}.SS" if code.startswith('6') else (f"{code}.HK" if len(code)==5 else f"{code}.SZ")
        df = yf.Ticker(ticker).history(period="1mo")
        if df.empty:
            idx = pd.date_range(end=datetime.now(), periods=5)
            df = pd.DataFrame({'Close': [curr if curr>0 else 100]*5}, index=idx)
    except: 
        idx = pd.date_range(end=datetime.now(), periods=5)
        df = pd.DataFrame({'Close': [100]*5}, index=idx)

    return df, info_str

# --- B. 代码执行 ---
def execute_code(code_str):
    img_path = None
    capture = io.StringIO()
    code = code_str.replace("plt.show()", "")
    lines = [l for l in code.split('\n') if not l.strip().startswith(('import', 'from'))]
    safe_code = '\n'.join(lines)
    
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4))
        local_vars = {
            'get_stock_data': get_stock_data,
            'plt': plt, 'pd': pd, 'yf': yf, 
            'datetime': datetime, 'contextlib': contextlib
        }
        with contextlib.redirect_stdout(capture):
            exec(safe_code, globals(), local_vars)
        
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100); plt.close()
    except: pass
    
    return img_path

# --- C. AI 思考 ---
def get_ai_response(user_text):
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        _, real_info = get_stock_data(user_text)
        
        prompt = f"""
        你叫金鑫，投资顾问。当前时间：{datetime.now().strftime('%Y-%m-%d')}。
        用户问：{user_text}
        **参考数据**：{real_info}
        
        要求：
        1. 基于数据回答。
        2. 生成 Python 代码画图 (使用 df, info = get_stock_data("代码"))。
        3. 回答简练，像真人。
        """
        resp = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        return f"系统繁忙: {e}"

# --- D. 语音/文本处理 ---
def transcribe(audio_bytes):
    if not audio_bytes: return None
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

def clean_text_display(text):
    return re.sub(r'```.*?```', '', text, flags=re.DOTALL).strip()

async def gen_voice(text, path):
    try: await edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(path); return True
    except: return False

# --- E. 记忆 ---
def load_mem():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f: return json.load(f)
        except: pass
    return []

def save_mem(msgs):
    clean_msgs = []
    for m in msgs:
        temp = m.copy()
        if "chart_buf" in temp: del temp["chart_buf"]
        clean_msgs.append(temp)
    with open(MEMORY_FILE, "w") as f: json.dump(clean_msgs, f)

def create_doc(msgs, idx=None):
    doc = Document(); doc.add_heading("金鑫研报", 0)
    targets = [msgs[idx]] if idx is not None else msgs
    for m in targets:
        if not m.get("hidden"):
            doc.add_heading(f"{m['role']}", 2); doc.add_paragraph(clean_text_display(m.get("content","")))
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 4. 界面布局 =================

if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "last_audio" not in st.session_state: st.session_state.last_audio = None
if "monitor" not in st.session_state: st.session_state.monitor = False

# --- 侧边栏 ---
with st.sidebar:
    st.image(get_avatar(), width=100)
    st.markdown("<h3 style='text-align:center'>金鑫</h3>", unsafe_allow_html=True)
    
    with st.expander("🎯 盯盘", expanded=True):
        m_code = st.text_input("代码", "300750")
        m_tgt = st.number_input("目标", 0.0)
        if st.button("🔴 启动/停止"):
            st.session_state.monitor = not st.session_state.monitor
            st.rerun()
        if st.session_state.monitor:
            st.info("📡 监控中...")
            df, info = get_stock_data(m_code)
            if "现价" in str(info):
                try:
                    curr = float(re.search(r"现价: (\d+\.\d+)", str(info)).group(1))
                    st.metric("实时价", curr)
                    if curr < m_tgt: st.error("触发目标价！"); st.session_state.monitor = False
                except: pass

    st.divider()
    search = st.text_input("🔍 搜索")
    
    c1, c2 = st.columns(2)
    if c1.button("🗑️ 清空", use_container_width=True):
        st.session_state.messages = []
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    c2.download_button("📥 导出", create_doc(st.session_state.messages), "all.docx", use_container_width=True)

# --- 主界面 ---
st.markdown("<div class='main-title'>您的全天候投资助理</div>", unsafe_allow_html=True)
st.markdown(f"<img src='{get_avatar()}' class='avatar-img'>", unsafe_allow_html=True)

# 1. 渲染消息
for i, msg in enumerate(st.session_state.messages):
    role = msg["role"]
    av = get_avatar() if role == "assistant" else "👨‍💼"
    
    if msg.get("hidden"): continue
    
    with st.chat_message(role, avatar=av):
        clean_txt = clean_text_display(msg["content"])
        st.write(clean_txt)
        
        if msg.get("image_path") and os.path.exists(msg["image_path"]):
            st.image(msg["image_path"])
        
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]):
            st.audio(msg["audio_path"])
            
        with st.expander("⋮ 操作"):
            c1, c2, c3, c4 = st.columns([1,1,1,1])
            if c1.button("📋", key=f"cp_{i}", help="复制"): st.code(clean_txt)
            if c2.button("🙈", key=f"hd_{i}", help="隐藏"): 
                st.session_state.messages[i]["hidden"] = True; save_mem(st.session_state.messages); st.rerun()
            if c3.button("🗑️", key=f"dl_{i}", help="删除"): 
                del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()
            c4.download_button("📥", create_doc(st.session_state.messages, i), f"msg_{i}.docx", key=f"ex_{i}", help="导出")

# 2. 输入处理 (放在外层，确保永远显示)
st.markdown("---")
c_voice, c_text = st.columns([1, 5])

# 语音组件 (防崩)
user_input = None
if mic_recorder:
    with c_voice:
        try:
            audio = mic_recorder(start_prompt="🎙️", stop_prompt="⏹️", key='mic')
            if audio and audio['bytes']:
                if "last_audio_bytes" not in st.session_state or st.session_state.last_audio_bytes != audio['bytes']:
                    st.session_state.last_audio_bytes = audio['bytes']
                    with st.spinner("识别中..."):
                        voice_text = transcribe(audio['bytes'])
                        if voice_text: user_input = voice_text
                        else: st.warning("未检测到语音")
        except: 
            st.caption("语音不可用")

# 文字组件
with c_text:
    text_input = st.chat_input("请输入股票代码或问题...")
    if text_input: user_input = text_input

# 3. 响应逻辑
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input, "id": str(uuid.uuid4())})
    save_mem(st.session_state.messages)
    
    with st.chat_message("assistant", avatar=get_avatar()):
        with st.spinner("分析中..."):
            full_response = get_ai_response(user_input)
            
            # 提取并执行代码
            img_p = None
            code_match = re.findall(r'```python(.*?)```', full_response, re.DOTALL)
            if code_match:
                img_p = execute_code(code_match[-1])
            
            # 语音生成
            af = None
            clean_txt = clean_text_display(full_response)
            try:
                af = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.mp3")
                asyncio.run(gen_voice(clean_txt[:300], af))
            except: pass
            
            st.markdown(clean_txt)
            if img_p: st.image(img_p)
            if af and os.path.exists(af): st.audio(af)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response, 
                "image_path": img_p,
                "audio_path": af
            })
            save_mem(st.session_state.messages)
            
    st.rerun()

if st.session_state.monitor:
    time.sleep(5); st.rerun()
