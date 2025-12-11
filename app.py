import streamlit as st
import google.generativeai as genai
import os
import matplotlib
matplotlib.use('Agg') # 【核心修复】强制使用非交互式后端，防止云端画图卡死
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

# ================= 1. 系统核心配置 =================
warnings.filterwarnings("ignore")

st.set_page_config(page_title="金鑫 - 智能财富合伙人", page_icon="👩‍💼", layout="wide")

# 路径初始化
MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# API KEY
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.error("🚨 请在 Streamlit Secrets 中配置 GEMINI_API_KEY")
    st.stop()

# ================= 2. 核心功能函数 =================

def load_avatar(filename, default_emoji):
    extensions = ["png", "jpg", "jpeg", "PNG", "JPG"]
    base_name = filename.split('.')[0]
    for ext in extensions:
        path = f"{base_name}.{ext}"
        if os.path.exists(path): return path
    return None

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

def get_stock_data_v8(ticker_symbol):
    """极速数据引擎"""
    sina_code = get_sina_code(ticker_symbol)
    info_str = "暂无实时数据"
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
            date_time = datetime.now().strftime("%H:%M:%S")
            info_str = f"【{name}】 现价: {curr:.2f} ({pct:+.2f}%) | 时间: {date_time}"
            current_price = curr
    except Exception as e: print(f"Sina Error: {e}")

    # 2. Yahoo History (Chart)
    df = None
    try:
        y_sym = ticker_symbol.upper()
        if y_sym.isdigit():
            if y_sym.startswith('6'): y_sym += ".SS"
            elif y_sym.startswith('0'): y_sym += ".SZ"
            elif len(y_sym)==5: y_sym += ".HK"
        
        ticker = yf.Ticker(y_sym)
        # 尝试获取较长时间数据以保证画图美观
        hist = ticker.history(period="1mo") 
        if not hist.empty:
            df = hist[['Close']]
    except: pass

    # 兜底：如果Yahoo挂了但新浪活着，手动造一个点防止报错
    if df is None and current_price > 0:
        df = pd.DataFrame({'Close': [current_price]}, index=[datetime.now()])

    return df, info_str

# --- 语音与 AI ---
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
        prompt = f"你是金鑫。请将此内容转为80字以内的口语，不要念数据：\n{text_analysis}"
        response = model.generate_content(prompt)
        return response.text
    except: return ""

# --- 模型配置 ---
def configure_chinese_font():
    font_candidates = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]
    for path in font_candidates:
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            plt.rcParams['font.sans-serif'] = [fm.FontProperties(fname=path).get_name()]
            plt.rcParams['axes.unicode_minus'] = False
            break
configure_chinese_font()

current_time_str = datetime.now().strftime("%Y年%m月%d日")
SYSTEM_INSTRUCTION = f"""
你叫“金鑫”，用户的专属私人财富合伙人。当前日期：{current_time_str}。

【任务】
1. 必须调用 `get_stock_data_v8(ticker)` 获取数据。
2. A股代码直接写数字 (如 600309)。
3. 必须在最后画图。

【代码模板】
ticker = "300750" 
df, info = get_stock_data_v8(ticker)

if df is not None:
    print(info) # 打印实时信息
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

# --- E. 代码执行引擎 (核心修复：注入 plt) ---
def execute_local_code_and_save(code_str):
    image_path = None; text_output = ""; output_capture = io.StringIO()
    try:
        plt.clf(); plt.figure(figsize=(10, 5), dpi=100) 
        
        # 【关键修复】全局注入 plt, pd, yf, get_stock_data_v8
        # 这样 AI 写的代码里直接用 plt.plot() 就不会报错 "name 'plt' is not defined"
        local_vars = {
            'get_stock_data_v8': get_stock_data_v8,
            'plt': plt, 
            'pd': pd, 
            'yf': yf
        }
        
        with contextlib.redirect_stdout(output_capture):
            exec(code_str, globals(), local_vars)
            
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

# --- F. 记忆管理 (核心修复：数据清洗) ---
def load_memory():
    """读取并清洗记忆文件，防止 str 报错"""
    data = []
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding='utf-8') as f:
                raw_data = json.load(f)
                # 【数据清洗】只保留字典类型的数据，剔除损坏的字符串
                if isinstance(raw_data, list):
                    for item in raw_data:
                        if isinstance(item, dict):
                            data.append(item)
        except: pass # 如果文件彻底坏了，就返回空列表，相当于重置
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

# ================= 3. UI 布局 =================

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stSidebar"] img { border-radius: 50%; border: 3px solid #4CAF50; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
    .stChatMessage { background-color: rgba(255, 255, 255, 0.05); border-radius: 10px; }
    .code-output { background-color: #e8f5e9; color: #000000 !important; padding: 15px; border-radius: 8px; border-left: 6px solid #2e7d32; font-family: monospace; }
    .monitor-box { border: 2px solid #ff5722; background-color: #fff3e0; padding: 10px; border-radius: 10px; text-align: center; color: #d84315; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# 状态初始化
if "messages" not in st.session_state: st.session_state.messages = load_memory()
if "chat_session" not in st.session_state:
    try:
        model = get_model()
        # 过滤掉坏数据再传给模型
        valid_history = []
        for m in st.session_state.messages:
            if isinstance(m, dict) and not m.get("hidden", False):
                valid_history.append({"role": ("user" if m["role"]=="user" else "model"), "parts": [str(m["content"])]})
        st.session_state.chat_session = model.start_chat(history=valid_history)
    except: pass

if "search_idx" not in st.session_state: st.session_state.search_idx = 0
if "last_search_query" not in st.session_state: st.session_state.last_search_query = ""
if "trigger_scroll" not in st.session_state: st.session_state.trigger_scroll = False
if "monitor_active" not in st.session_state: st.session_state.monitor_active = False

# 头像加载
ai_avatar_path = load_avatar("avatar", "👩‍💼")
user_avatar_path = load_avatar("user", "👨‍💼")
sidebar_img = ai_avatar_path if ai_avatar_path else "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin&clothing=blazerAndShirt"

# --- 侧边栏 ---
with st.sidebar:
    st.image(sidebar_img, use_container_width=True, caption="👩‍💼 金鑫 - 高级合伙人")
    
    # 1. 盯盘雷达
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
            df_m, info_m = get_stock_data_v8(monitor_ticker)
            if df_m is not None:
                # 尝试解析价格
                try:
                    curr = df_m['Close'].iloc[-1]
                    st.metric("实时价", f"{curr:.2f}")
                    triggered = False
                    if monitor_type == "跌破" and curr < monitor_target: triggered = True
                    if monitor_type == "突破" and curr > monitor_target: triggered = True
                    if triggered:
                        msg = f"注意！{monitor_ticker} 现价 {curr:.2f} 触发目标！"
                        st.error(msg)
                        st.session_state.monitor_active = False 
                except: st.warning("数据解析中...")
            else:
                st.warning("获取失败")

    st.divider()
    
    # 2. 搜索
    search_query = st.text_input("🔍 搜索", placeholder="关键词...", label_visibility="collapsed")
    # 搜索前先过滤非字典项
    match_indices = [i for i, m in enumerate(st.session_state.messages) if isinstance(m, dict) and not m.get("hidden", False) and search_query and search_query in str(m.get("content"))]
    if search_query != st.session_state.last_search_query:
        st.session_state.search_idx = 0; st.session_state.last_search_query = search_query; st.session_state.trigger_scroll = True

    if match_indices:
        c1, c2, c3 = st.columns([1, 2, 1])
        if c1.button("🔼"): st.session_state.search_idx = (st.session_state.search_idx - 1) % len(match_indices); st.session_state.trigger_scroll = True; st.rerun()
        if c3.button("🔽"): st.session_state.search_idx = (st.session_state.search_idx + 1) % len(match_indices); st.session_state.trigger_scroll = True; st.rerun()
        c2.markdown(f"<div style='text-align:center; padding-top:5px;'>{st.session_state.search_idx + 1}/{len(match_indices)}</div>", unsafe_allow_html=True)
        if st.session_state.trigger_scroll:
            try:
                tid = st.session_state.messages[match_indices[st.session_state.search_idx]]["id"]
                import streamlit.components.v1 as components
                components.html(f"<script>setTimeout(function(){{var e=window.parent.document.getElementById('{tid}');if(e)e.scrollIntoView({{behavior:'smooth',block:'center'}});}}, 500);</script>", height=0)
            except: pass
            st.session_state.trigger_scroll = False

    st.divider()
    
    # 3. 导出与清空
    c_btn1, c_btn2 = st.columns(2)
    if c_btn1.button("🗑️ 清空", type="primary", use_container_width=True):
        st.session_state.messages = []; st.session_state.chat_session = None
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    
    doc = create_word_doc(st.session_state.messages)
    c_btn2.download_button("📥 导出", doc, "报告.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    
    st.divider()
    text_voice = mic_recorder(start_prompt="🎙️ 语音", stop_prompt="⏹️ 停止", key='rec', format="wav", use_container_width=True)

# --- 主界面 ---
c_h1, c_h2 = st.columns([1, 6])
with c_h1:
    if ai_avatar_path: st.image(ai_avatar_path, width=80)
    else: st.markdown("## 👩‍💼")
with c_h2:
    st.title("金鑫：云端财富合伙人")

# 渲染消息流 (带容错)
for i, msg in enumerate(st.session_state.messages):
    # 容错：如果 msg 不是字典，跳过
    if not isinstance(msg, dict): continue
    if msg.get("hidden", False): continue
    
    st.markdown(f"<div id='{msg.get('id', '')}'></div>", unsafe_allow_html=True)
    is_curr = search_query and match_indices and i == match_indices[st.session_state.search_idx]

    current_avatar = ai_avatar_path if msg["role"] == "assistant" else user_avatar_path
    if not current_avatar: 
        current_avatar = "👩‍💼" if msg["role"] == "assistant" else "👨‍💼"

    with st.chat_message(msg["role"], avatar=current_avatar):
        st.caption(f"{msg.get('timestamp','')} {'| 📍' if is_curr else ''}")
        if msg.get("code_output"):
            st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        
        content = msg.get("content", "")
        if search_query: content = re.compile(re.escape(search_query), re.IGNORECASE).sub(lambda m: f"<mark>{m.group()}</mark>", content)
        clean = re.sub(r'```python.*?```', '', content, flags=re.DOTALL)
        if is_curr: st.markdown(f"<div class='current-match'>{clean}</div>", unsafe_allow_html=True)
        else: st.markdown(clean, unsafe_allow_html=True)
        
        if msg.get("image_path") and os.path.exists(msg["image_path"]): st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg.get("audio_path")): st.audio(msg["audio_path"], format="audio/wav")
        
        with st.expander("🛠️ 更多操作", expanded=False):
            c1, c2, c3 = st.columns([1,1,3])
            if c1.button("🚫 隐藏", key=f"h_{msg.get('id')}"): toggle_hidden(msg.get("id"))
            if c2.button("🗑️ 删除", key=f"d_{msg.get('id')}"): delete_message(msg.get("id"))
            st.code(clean, language="text")

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
    # 容错：确保last是字典
    if isinstance(last, dict):
        with st.chat_message("assistant", avatar=ai_avatar_path if ai_avatar_path else "👩‍💼"):
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
                    if save_audio_cloud(spoken, ap): st.audio(ap, format="audio/wav"); af = ap
                except: pass
            st.session_state.messages.append({"id": str(uuid.uuid4()), "role": "assistant", "content": txt, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "hidden": False, "image_path": img, "audio_path": af, "code_output": out})
            save_memory(st.session_state.messages)

if st.session_state.monitor_active:
    time.sleep(5)
    st.rerun()
