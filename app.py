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
import edge_tts  # 云端语音库
import requests
import pandas as pd
import warnings
import contextlib # 【已修复】补回漏掉的库
import sys
import yfinance as yf
from PIL import Image

# ================= 1. 云端环境配置 =================
warnings.filterwarnings("ignore")

# ⚠️ 云端通常不需要代理，已移除 PROXY 设置
# 如果你在本地运行此版本且需要翻墙，请自行恢复 os.environ 设置

# API KEY (建议在 Streamlit Secrets 中配置，这里做兼容)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU" 

MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"

for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# 【UI修复】页面图标尝试使用本地图片（如果不支持则用 Emoji）
st.set_page_config(page_title="金鑫 - 云端私人顾问", page_icon="👩‍💼", layout="wide")

# ================= 2. UI 美化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stSidebar"] div[data-testid="stImage"] img {
        width: 100%; max-width: 100%; object-fit: cover; border-radius: 12px;
    }
    .stChatMessage { background-color: rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 10px; margin-bottom: 10px; }
    mark { background-color: #ffeb3b; color: #000000 !important; border-radius: 4px; padding: 0.2em; font-weight: bold; }
    .current-match { border: 2px solid #ff4b4b; padding: 10px; border-radius: 10px; background-color: rgba(255, 75, 75, 0.05); display: block; }
    .code-output { background-color: #e8f5e9; color: #000000 !important; padding: 15px; border-radius: 8px; border-left: 6px solid #2e7d32; font-family: 'Consolas', monospace; margin-bottom: 10px; font-size: 0.95em; }
    .monitor-box { border: 2px solid #ff5722; background-color: #fff3e0; padding: 10px; border-radius: 10px; text-align: center; color: #d84315; font-weight: bold; font-size: 0.9em; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ================= 3. 核心功能函数 =================

def load_avatar(filename, default_emoji):
    """加载本地头像"""
    extensions = ["png", "jpg", "jpeg"]
    base_name = filename.split('.')[0]
    for ext in extensions:
        path = f"{base_name}.{ext}"
        if os.path.exists(path):
            return path # 返回路径
    return default_emoji # 找不到文件则返回 Emoji

# --- 数据抓取 (云端策略：优先 Yahoo) ---
def fix_stock_symbol(symbol):
    s = symbol.strip().upper()
    if s.isdigit():
        if s.startswith('6'): return f"{s}.SS"
        if s.startswith('0') or s.startswith('3'): return f"{s}.SZ"
        if len(s) == 5: return f"{s}.HK"
        if len(s) == 4: return f"0{s}.HK"
    return s

def get_stock_data_cloud(ticker_symbol):
    """云端数据抓取：主要依赖 yfinance"""
    symbol = fix_stock_symbol(ticker_symbol)
    df = None
    info_str = "暂无数据"
    
    try:
        ticker = yf.Ticker(symbol)
        # 获取最近5天数据
        hist = ticker.history(period="5d", interval="1d")
        
        if not hist.empty:
            df = hist[['Close']]
            last_price = df['Close'].iloc[-1]
            last_date = df.index[-1].strftime("%Y-%m-%d")
            currency = ticker.info.get('currency', '?')
            
            # 尝试计算涨跌
            change_str = ""
            if len(df) >= 2:
                prev = df['Close'].iloc[-2]
                change = last_price - prev
                pct = (change / prev) * 100
                change_str = f" ({'+' if change>0 else ''}{change:.2f} / {pct:.2f}%)"
            
            info_str = f"日期: {last_date} | 最新价: {last_price:.2f} {currency}{change_str}"
            return df, info_str
    except Exception as e:
        print(f"Yahoo Error: {e}")

    return None, f"数据获取失败 ({symbol})，请检查代码或网络"

# --- 语音合成 (Edge-TTS) ---
async def generate_audio_edge(text, output_file):
    """微软 Edge 语音 (云端核心)"""
    try:
        # 使用晓晓 (Xiaoxiao) - 知性女声
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(output_file)
        return True
    except: return False

def save_audio_cloud(text, output_path):
    """同步包装器"""
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

# --- 系统配置 ---
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

# --- 侧边栏 (功能全回归) ---
with st.sidebar:
    # 1. 头像逻辑
    user_avatar = load_avatar("user", "👨‍💼")
    ai_avatar = load_avatar("avatar", "👩‍💼")
    
    # 金鑫头像展示
    c_av1, c_av2, c_av3 = st.columns([1, 2, 1])
    with c_av2:
        if os.path.exists(ai_avatar) and ai_avatar != "👩‍💼": 
            st.image(ai_avatar, use_container_width=True)
        else: 
            st.markdown("<div style='text-align: center; font-size: 60px;'>👩‍💼</div>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>金鑫 - 云端合伙人</h3>", unsafe_allow_html=True)

    # 2. 盯盘雷达 (回归!)
    with st.expander("🎯 价格雷达 (盯盘)", expanded=False):
        monitor_ticker = st.text_input("代码", value="300750", placeholder="如 300750")
        c_m1, c_m2 = st.columns(2)
        monitor_target = c_m1.number_input("目标", value=200.0, step=1.0)
        monitor_type = c_m2.selectbox("条件", ["跌破", "突破"])
        
        if st.button("🔴 启动" if not st.session_state.monitor_active else "⏹️ 停止", type="primary" if not st.session_state.monitor_active else "secondary"):
            st.session_state.monitor_active = not st.session_state.monitor_active
            st.rerun()
            
        if st.session_state.monitor_active:
            st.markdown("<div class='monitor-box'>📡 扫描中...</div>", unsafe_allow_html=True)
            # 云端盯盘逻辑
            df_m, info_m = get_stock_data_cloud(monitor_ticker)
            if df_m is not None:
                curr = df_m['Close'].iloc[-1]
                st.metric("实时价", f"{curr:.2f}")
                
                triggered = False
                if monitor_type == "跌破" and curr < monitor_target: triggered = True
                if monitor_type == "突破" and curr > monitor_target: triggered = True
                
                if triggered:
                    msg = f"注意！{monitor_ticker} 现价 {curr:.2f} 触发目标！"
                    st.error(msg)
                    st.session_state.monitor_active = False # 触发即停
            else:
                st.warning("获取失败")

    st.divider()
    
    # 3. 搜索 (回归!)
    search_query = st.text_input("🔍 搜索", placeholder="关键词...", label_visibility="collapsed")
    match_indices = [i for i, m in enumerate(st.session_state.messages) if not m.get("hidden", False) and search_query and search_query in m["content"]]
    if search_query != st.session_state.last_search_query:
        st.session_state.search_idx = 0; st.session_state.last_search_query = search_query; st.session_state.trigger_scroll = True

    if match_indices:
        c1, c2, c3 = st.columns([1, 2, 1])
        if c1.button("🔼"): st.session_state.search_idx = (st.session_state.search_idx - 1) % len(match_indices); st.session_state.trigger_scroll = True; st.rerun()
        if c3.button("🔽"): st.session_state.search_idx = (st.session_state.search_idx + 1) % len(match_indices); st.session_state.trigger_scroll = True; st.rerun()
        c2.markdown(f"<div style='text-align:center; padding-top:5px;'>{st.session_state.search_idx + 1}/{len(match_indices)}</div>", unsafe_allow_html=True)
        if st.session_state.trigger_scroll:
            tid = st.session_state.messages[match_indices[st.session_state.search_idx]]["id"]
            import streamlit.components.v1 as components
            components.html(f"<script>setTimeout(function(){{var e=window.parent.document.getElementById('{tid}');if(e)e.scrollIntoView({{behavior:'smooth',block:'center'}});}}, 500);</script>", height=0)
            st.session_state.trigger_scroll = False

    st.divider()
    
    # 4. 导出与清空 (回归!)
    c_btn1, c_btn2 = st.columns(2)
    if c_btn1.button("🗑️ 清空", type="primary", use_container_width=True):
        st.session_state.messages = []; st.session_state.chat_session = None
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    
    doc = create_word_doc(st.session_state.messages)
    c_btn2.download_button("📥 导出", doc, "报告.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    
    st.divider()
    text_voice = mic_recorder(start_prompt="🎙️ 语音", stop_prompt="⏹️ 停止", key='rec', format="wav", use_container_width=True)

# Main
st.markdown("<h2 style='text-align: center;'>👩‍💼 金鑫：云端财富合伙人</h2>", unsafe_allow_html=True)

for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden", False): continue
    st.markdown(f"<div id='{msg['id']}'></div>", unsafe_allow_html=True)
    
    is_curr = search_query and match_indices and i == match_indices[st.session_state.search_idx]
    
    # 头像逻辑：优先用图片
    current_avatar = ai_avatar if msg["role"] == "assistant" else user_avatar
    # 再次确认文件存在，否则用 emoji
    if current_avatar != "👩‍💼" and current_avatar != "👨‍💼" and not os.path.exists(current_avatar):
        current_avatar = "👩‍💼" if msg["role"] == "assistant" else "👨‍💼"

    with st.chat_message(msg["role"], avatar=current_avatar):
        st.caption(f"{msg.get('timestamp','')} {'| 📍' if is_curr else ''}")
        if msg.get("code_output"):
            st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        
        content = msg["content"]
        if search_query: content = re.compile(re.escape(search_query), re.IGNORECASE).sub(lambda m: f"<mark>{m.group()}</mark>", content)
        clean = re.sub(r'```python.*?```', '', content, flags=re.DOTALL)
        if is_curr: st.markdown(f"<div class='current-match'>{clean}</div>", unsafe_allow_html=True)
        else: st.markdown(clean, unsafe_allow_html=True)
        
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
    with st.chat_message("assistant", avatar=ai_avatar if os.path.exists(ai_avatar) else "👩‍💼"):
        ph = st.empty(); img = None; out = None; txt = ""
        if st.session_state.chat_session:
            with st.spinner("☁️ 云端运算中..."):
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
                # 云端语音生成
                if save_audio_cloud(spoken, ap): st.audio(ap, format="audio/wav"); af = ap
            except: pass
        st.session_state.messages.append({"id": str(uuid.uuid4()), "role": "assistant", "content": txt, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "hidden": False, "image_path": img, "audio_path": af, "code_output": out})
        save_memory(st.session_state.messages)

if st.session_state.monitor_active:
    time.sleep(5)
    st.rerun()
