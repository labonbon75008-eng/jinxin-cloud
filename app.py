import streamlit as st
import google.generativeai as genai
import os
# 【核心 1】强制后端，防止云端画图崩溃
import matplotlib
matplotlib.use('Agg') 
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

# ================= 1. 坚如磐石的初始化 =================
warnings.filterwarnings("ignore")

st.set_page_config(page_title="金鑫 - 智能财富合伙人", page_icon="👩‍💼", layout="wide")

# 路径配置
MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# API KEY (最后一次确认：请确保 Secrets 里填了)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    # 避免直接报错退出，给个提示
    st.warning("⚠️ 检测到未配置 Secrets，尝试使用临时 Key (可能不稳定)")
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU"

# ================= 2. 核心功能：数据与逻辑 =================

def load_avatar(filename, default_emoji):
    """加载头像，找不到就返回None"""
    extensions = ["png", "jpg", "jpeg", "PNG", "JPG"]
    base = filename.split('.')[0]
    for ext in extensions:
        p = f"{base}.{ext}"
        if os.path.exists(p): return p
    return None

# --- 数据引擎 (新浪 + Yahoo) ---
def get_sina_code(symbol):
    s = symbol.strip().upper().replace(".SS", "").replace(".SZ", "").replace(".HK", "")
    if s.isdigit():
        if len(s) == 5: return f"hk{s}" 
        if len(s) == 4: return f"hk0{s}" 
        if len(s) == 6:
            if s.startswith('6'): return f"sh{s}"
            if s.startswith('0') or s.startswith('3'): return f"sz{s}"
            if s.startswith('8') or s.startswith('4'): return f"bj{s}"
    return f"sh{s}" if s.isdigit() else s

def get_stock_data_v9(ticker_symbol):
    """V9 引擎：保证返回 df 和 info，绝不报错"""
    sina_code = get_sina_code(ticker_symbol)
    info_str = "暂无数据"
    current_price = 0.0
    
    # 1. Sina Realtime
    try:
        url = f"http://hq.sinajs.cn/list={sina_code}"
        headers = {'Referer': 'https://finance.sina.com.cn'}
        r = requests.get(url, headers=headers, timeout=2, proxies={"http": None, "https": None})
        if '=""' not in r.text and len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            name = parts[0]
            curr = float(parts[3])
            prev = float(parts[2])
            pct = ((curr - prev) / prev) * 100 if prev != 0 else 0
            t_str = datetime.now().strftime("%H:%M:%S")
            info_str = f"【{name}】 现价: {curr:.2f} ({pct:+.2f}%) | 时间: {t_str}"
            current_price = curr
    except: pass

    # 2. Yahoo History
    df = None
    try:
        y_sym = ticker_symbol.upper()
        if y_sym.isdigit():
            if y_sym.startswith('6'): y_sym += ".SS"
            elif y_sym.startswith('0'): y_sym += ".SZ"
            elif len(y_sym)==5: y_sym += ".HK"
        
        ticker = yf.Ticker(y_sym)
        hist = ticker.history(period="1mo") 
        if not hist.empty:
            df = hist[['Close']]
    except: pass

    # 3. 强制兜底 (防止 AI 画图报错)
    if df is None and current_price > 0:
        # 造2个点的数据，让线能画出来
        df = pd.DataFrame({'Close': [current_price, current_price]}, 
                          index=[datetime.now()-timedelta(days=1), datetime.now()])
    
    return df, info_str

# --- 语音 ---
async def generate_audio_edge(text, output_file):
    try:
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
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source: audio_data = r.record(source)
        return r.recognize_google(audio_data, language='zh-CN')
    except: return None

def get_spoken_response(text_analysis):
    if not text_analysis: return ""
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        prompt = f"你是金鑫。请将此内容转为80字以内的口语：\n{text_analysis}"
        response = model.generate_content(prompt)
        return response.text
    except: return ""

# --- 模型 ---
current_time_str = datetime.now().strftime("%Y-%m-%d")
SYSTEM_INSTRUCTION = f"""
你叫“金鑫”，用户的专属私人财富合伙人。当前日期：{current_time_str}。

【任务】
1. 必须调用 `get_stock_data_v9(ticker)` 获取数据。
2. A股代码直接写数字 (如 600309)。
3. 必须在最后画图。

【代码模板】
ticker = "300750" 
df, info = get_stock_data_v9(ticker)

if df is not None:
    print(info)
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

# --- 核心：代码执行 (防崩设计) ---
def execute_local_code_and_save(code_str):
    image_path = None; text_output = ""; output_capture = io.StringIO()
    
    # 清洗代码：移除 import
    lines = [l for l in code_str.split('\n') if not l.strip().startswith(('import ', 'from '))]
    safe_code = '\n'.join(lines)

    try:
        plt.close('all'); plt.clf()
        plt.figure(figsize=(10, 5), dpi=100) 
        
        local_vars = {
            'get_stock_data_v9': get_stock_data_v9,
            'plt': plt, 'pd': pd, 'yf': yf
        }
        
        with contextlib.redirect_stdout(output_capture):
            exec(safe_code, globals(), local_vars)
            
        text_output = output_capture.getvalue()
        
        if plt.get_fignums():
            fig = plt.gcf()
            filename = f"chart_{int(time.time())}.png"
            image_path = os.path.join(CHARTS_DIR, filename)
            fig.savefig(image_path, format="png", bbox_inches='tight')
            plt.close(fig)
    except Exception as e: 
        text_output = f"执行异常: {str(e)}"
    
    return image_path, text_output

# --- 核心：记忆清洗 (解决 'string indices' 报错) ---
def load_memory_safe():
    data = []
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding='utf-8') as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    for item in raw:
                        # 【核心修复】只留正常的字典，坏数据统统扔掉
                        if isinstance(item, dict) and "role" in item and "content" in item:
                            data.append(item)
        except: pass
    return data

def save_memory(messages):
    try:
        with open(MEMORY_FILE, "w", encoding='utf-8') as f: json.dump(messages, f, ensure_ascii=False, indent=2)
    except: pass

def delete_message(msg_id):
    for i, msg in enumerate(st.session_state.messages):
        if msg.get("id") == msg_id:
            del st.session_state.messages[i]; save_memory(st.session_state.messages); st.rerun(); break

def toggle_hidden(msg_id):
    for msg in st.session_state.messages:
        if msg.get("id") == msg_id:
            msg["hidden"] = not msg.get("hidden", False); save_memory(st.session_state.messages); st.rerun(); break

def create_word_doc(messages):
    doc = Document(); doc.add_heading("金鑫财富报告", 0)
    for msg in messages:
        if isinstance(msg, dict) and not msg.get("hidden"):
            role = "金鑫" if msg.get("role") == "assistant" else "客户"
            doc.add_heading(f"{role} - {msg.get('timestamp','')}", level=2)
            if msg.get("code_output"): doc.add_paragraph(f"【数据】\n{msg['code_output']}")
            clean = re.sub(r'```python.*?```', '', msg.get("content",""), flags=re.DOTALL)
            doc.add_paragraph(clean.strip())
            if msg.get("image_path") and os.path.exists(msg["image_path"]):
                try: doc.add_picture(msg["image_path"], width=Inches(5))
                except: pass
    bio = io.BytesIO(); doc.save(bio); bio.seek(0); return bio

# ================= 3. 界面逻辑 =================

# 状态初始化
if "messages" not in st.session_state: st.session_state.messages = load_memory_safe()
if "last_audio_id" not in st.session_state: st.session_state.last_audio_id = None # 【防死循环锁】
if "monitor_active" not in st.session_state: st.session_state.monitor_active = False
if "search_idx" not in st.session_state: st.session_state.search_idx = 0

# 模型初始化
if "chat_session" not in st.session_state:
    try:
        model = get_model()
        # 历史记录清洗
        valid_history = []
        for m in st.session_state.messages:
            if isinstance(m, dict) and not m.get("hidden"):
                valid_history.append({"role": ("user" if m["role"]=="user" else "model"), "parts": [str(m["content"])]})
        st.session_state.chat_session = model.start_chat(history=valid_history)
    except: pass

# 界面 CSS
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stSidebar"] img { border-radius: 50%; border: 3px solid #4CAF50; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
    .stChatMessage { background-color: rgba(255, 255, 255, 0.05); border-radius: 10px; }
    .code-output { background-color: #e8f5e9; color: #000000 !important; padding: 15px; border-radius: 8px; font-family: monospace; }
    .monitor-box { border: 2px solid #ff5722; background-color: #fff3e0; padding: 10px; border-radius: 10px; text-align: center; color: #d84315; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# 头像
ai_avatar = load_avatar("avatar", "👩‍💼")
user_avatar = load_avatar("user", "👨‍💼")
sidebar_img = ai_avatar if ai_avatar else "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin"

# --- 侧边栏 ---
with st.sidebar:
    st.image(sidebar_img, use_container_width=True, caption="👩‍💼 金鑫 - 高级合伙人")
    
    # 盯盘
    with st.expander("🎯 价格雷达", expanded=False):
        m_tick = st.text_input("代码", "300750")
        m_tgt = st.number_input("目标", 200.0)
        m_type = st.selectbox("条件", ["跌破", "突破"])
        if st.button("🚀 启停盯盘"):
            st.session_state.monitor_active = not st.session_state.monitor_active
            st.rerun()
        if st.session_state.monitor_active:
            st.markdown("<div class='monitor-box'>📡 运行中...</div>", unsafe_allow_html=True)
            df_m, info_m = get_stock_data_v9(m_tick)
            if df_m is not None:
                try:
                    curr = df_m['Close'].iloc[-1]
                    st.metric("现价", f"{curr:.2f}")
                    if (m_type=="跌破" and curr<m_tgt) or (m_type=="突破" and curr>m_tgt):
                        st.error("触发！"); st.session_state.monitor_active = False
                except: pass

    st.divider()
    
    # 搜索
    search = st.text_input("🔍 搜索", placeholder="...", label_visibility="collapsed")
    matches = [i for i, m in enumerate(st.session_state.messages) if isinstance(m,dict) and not m.get("hidden") and search and search in str(m.get("content"))]
    if matches:
        c1, c2 = st.columns(2)
        if c1.button("🔼"): st.session_state.search_idx = (st.session_state.search_idx - 1) % len(matches); st.rerun()
        if c2.button("🔽"): st.session_state.search_idx = (st.session_state.search_idx + 1) % len(matches); st.rerun()
        if st.session_state.search_idx < len(matches):
            try:
                tid = st.session_state.messages[matches[st.session_state.search_idx]].get("id")
                import streamlit.components.v1 as components
                components.html(f"<script>setTimeout(function(){{document.getElementById('{tid}').scrollIntoView();}},500);</script>", height=0)
            except: pass

    # 导出
    c_btn1, c_btn2 = st.columns(2)
    if c_btn1.button("🗑️ 清空"):
        st.session_state.messages = []
        st.session_state.chat_session = None
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    
    doc = create_word_doc(st.session_state.messages)
    c_btn2.download_button("📥 导出", doc, "report.docx")
    
    st.divider()
    audio_val = mic_recorder(start_prompt="🎙️ 语音", stop_prompt="⏹️ 停止", key='mic')

# --- 主界面 ---
c_h1, c_h2 = st.columns([1, 6])
with c_h1: 
    if ai_avatar: st.image(ai_avatar, width=80)
    else: st.markdown("## 👩‍💼")
with c_h2: st.title("金鑫：云端财富合伙人")

# 消息流
for i, msg in enumerate(st.session_state.messages):
    if not isinstance(msg, dict) or msg.get("hidden"): continue
    
    st.markdown(f"<div id='{msg.get('id')}'></div>", unsafe_allow_html=True)
    is_curr = matches and st.session_state.search_idx < len(matches) and i == matches[st.session_state.search_idx]
    
    av = ai_avatar if msg["role"] == "assistant" else user_avatar
    if not av: av = "👩‍💼" if msg["role"] == "assistant" else "👨‍💼"

    with st.chat_message(msg["role"], avatar=av):
        if msg.get("code_output"): st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        content = msg.get("content", "")
        if search: content = re.sub(re.escape(search), f"<mark>{search}</mark>", content, flags=re.I)
        st.markdown(re.sub(r'```python.*?```', '', content, flags=re.DOTALL), unsafe_allow_html=True)
        if msg.get("image_path") and os.path.exists(msg["image_path"]): st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]): st.audio(msg["audio_path"])
        
        with st.expander("🛠️ 操作"):
            c1, c2 = st.columns(2)
            if c1.button("🚫 隐藏", key=f"h_{msg.get('id')}"): toggle_hidden(msg.get("id"))
            if c2.button("🗑️ 删除", key=f"d_{msg.get('id')}"): delete_message(msg.get("id"))

# 输入处理
u_text = st.chat_input("请问金鑫...")
u_final = None

# 【核心修复】语音防死循环
if audio_val and audio_val['bytes']:
    if audio_val['id'] != st.session_state.last_audio_id:
        st.session_state.last_audio_id = audio_val['id']
        u_final = transcribe_audio(audio_val['bytes'])
elif u_text:
    u_final = u_text

if u_final:
    st.session_state.messages.append({"id": str(uuid.uuid4()), "role": "user", "content": u_final, "timestamp": str(datetime.now())})
    save_memory(st.session_state.messages)
    st.rerun()

# AI 响应
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last = st.session_state.messages[-1]
    if isinstance(last, dict):
        with st.chat_message("assistant", avatar=ai_avatar if ai_avatar else "👩‍💼"):
            with st.spinner("☁️ 分析中..."):
                try:
                    if not st.session_state.chat_session: st.rerun()
                    resp = st.session_state.chat_session.send_message(last["content"])
                    txt = resp.text
                    
                    img_p = None; out_t = None
                    codes = re.findall(r'```python(.*?)```', txt, re.DOTALL)
                    if codes: img_p, out_t = execute_local_code_and_save(codes[-1])
                    
                    if out_t: st.markdown(f"<div class='code-output'>{out_t}</div>", unsafe_allow_html=True)
                    st.markdown(re.sub(r'```python.*?```', '', txt, flags=re.DOTALL))
                    if img_p: st.image(img_p)
                    
                    af = None
                    # 语音生成
                    spoken = get_spoken_response(txt)
                    if spoken:
                        ap = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.wav")
                        if save_audio_cloud(spoken, ap): 
                            st.audio(ap)
                            af = ap
                            
                    st.session_state.messages.append({
                        "id": str(uuid.uuid4()), "role": "assistant", "content": txt,
                        "image_path": img_p, "audio_path": af, "code_output": out_t,
                        "timestamp": str(datetime.now())
                    })
                    save_memory(st.session_state.messages)
                except Exception as e: st.error(f"Error: {e}")

if st.session_state.monitor_active:
    time.sleep(5)
    st.rerun()
