import streamlit as st
import google.generativeai as genai
import os
import time
import json
import uuid
import re
from datetime import datetime
import threading
import requests
import pandas as pd
import warnings
import io
from PIL import Image
import speech_recognition as sr
import edge_tts
import asyncio
import yfinance as yf
from docx import Document
from docx.shared import Inches
from streamlit_mic_recorder import mic_recorder

# ================= 1. 基础配置 (最简稳健模式) =================
warnings.filterwarnings("ignore")

# 必须是第一个 Streamlit 命令
st.set_page_config(page_title="金鑫 - 智能投资顾问", page_icon="👩‍💼", layout="wide")

# 路径初始化
MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# API KEY (带容错机制，防止黑屏)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    # 如果没有 Secrets，使用默认或者空，保证界面能加载出来
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU" 

# ================= 2. 核心功能函数 =================

# --- 1. 极速数据抓取 (新浪源) ---
def get_sina_code(symbol):
    s = symbol.strip().upper()
    if s.isdigit():
        if s.startswith('6'): return f"sh{s}"
        if s.startswith('0') or s.startswith('3'): return f"sz{s}"
        if s.startswith('8') or s.startswith('4'): return f"bj{s}"
        if len(s) == 5: return f"hk{s}"
    return s

def get_stock_data_cloud(ticker_symbol):
    """优先使用新浪接口获取实时数据，失败则返回空"""
    sina_code = get_sina_code(ticker_symbol)
    url = f"http://hq.sinajs.cn/list={sina_code}"
    
    # 结果容器
    price_info = "暂无数据"
    df = None
    
    try:
        # 强制不使用代理，直连新浪
        r = requests.get(url, timeout=2, proxies={"http": None, "https": None})
        if '=""' not in r.text and len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            name = parts[0]
            curr = float(parts[3])
            date = datetime.now().strftime("%H:%M:%S")
            price_info = f"【{name}】 现价: {curr:.2f} | 时间: {date}"
            
            # 造一个简单的数据用于画图 (因为新浪不给历史K线)
            df = pd.DataFrame({'Close': [curr]}, index=[datetime.now()])
            return df, price_info
    except:
        pass
    
    # 备用：Yahoo (只用于画图，不强求)
    try:
        y_sym = ticker_symbol
        if y_sym.isdigit():
            if y_sym.startswith('6'): y_sym += ".SS"
            elif y_sym.startswith('0'): y_sym += ".SZ"
        ticker = yf.Ticker(y_sym)
        hist = ticker.history(period="5d")
        if not hist.empty:
            df = hist[['Close']]
            last = df['Close'].iloc[-1]
            if price_info == "暂无数据":
                price_info = f"【Yahoo延迟数据】收盘价: {last:.2f}"
            return df, price_info
    except:
        pass

    return None, f"无法获取 {ticker_symbol} 数据"

# --- 2. 语音与 AI ---
def get_spoken_response(text):
    if not text: return ""
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        response = model.generate_content(f"我是金鑫，请将此内容转为口语(80字内)：\n{text}")
        return response.text
    except: return ""

def save_audio_cloud(text, path):
    try:
        asyncio.run(edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(path))
        return True
    except: return False

def transcribe_audio(audio_bytes):
    r = sr.Recognizer()
    try:
        audio_io = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_io) as source: audio_data = r.record(source)
        return r.recognize_google(audio_data, language='zh-CN')
    except: return None

# --- 3. 模型配置 ---
SYSTEM_INSTRUCTION = f"""
你叫“金鑫”，用户的专属财富合伙人。当前时间：{datetime.now().strftime("%Y-%m-%d")}。
查询价格时，请编写代码调用 `get_stock_data_cloud(ticker)`。
代码模板：
ticker = "600309"
df, info = get_stock_data_cloud(ticker)
if df is not None:
    print(info)
    plt.figure(figsize=(10, 4)) # 尺寸调小一点，防止黑屏
    plt.plot(df.index, df['Close'], color='#c2185b')
    plt.title(ticker)
    plt.grid(True, alpha=0.3)
else:
    print(f"数据失败: {{info}}")
"""

@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    return genai.GenerativeModel(model_name="gemini-3-pro-preview", system_instruction=SYSTEM_INSTRUCTION)

def execute_local_code_and_save(code_str):
    image_path = None; text_output = ""; output_capture = io.StringIO()
    try:
        plt.clf(); plt.figure(figsize=(8, 4), dpi=100) 
        local_vars = {'get_stock_data_cloud': get_stock_data_cloud, 'plt': plt, 'pd': pd, 'yf': yf}
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

# ================= 3. UI 布局 (稳健版) =================

st.markdown("""
<style>
    /* 简单粗暴的 CSS，防止冲突 */
    .stApp { background-color: #0e1117; }
    div[data-testid="stSidebar"] img { border-radius: 50%; border: 3px solid #4CAF50; }
    .stChatMessage { background-color: rgba(255, 255, 255, 0.05); }
    .code-output { background-color: #e8f5e9; color: black !important; padding: 10px; border-radius: 5px; }
    .monitor-box { border: 2px solid #ff5722; background-color: #fff3e0; padding: 10px; border-radius: 5px; text-align: center; color: #d84315; }
</style>
""", unsafe_allow_html=True)

# 状态管理
if "messages" not in st.session_state: 
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f: st.session_state.messages = json.load(f)
    else:
        st.session_state.messages = []

if "chat_session" not in st.session_state:
    try:
        model = get_model()
        history = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in st.session_state.messages if not m.get("hidden", False)]
        st.session_state.chat_session = model.start_chat(history=history)
    except: pass

if "monitor_active" not in st.session_state: st.session_state.monitor_active = False

# --- 侧边栏 ---
with st.sidebar:
    # 稳健的图片加载：直接读文件，不搞花哨的函数
    if os.path.exists("avatar.png"):
        st.image("avatar.png", use_container_width=True, caption="👩‍💼 金鑫")
    else:
        st.markdown("# 👩‍💼")
        st.caption("金鑫 (未找到 avatar.png)")

    st.markdown("### 控制台")
    
    # 盯盘
    with st.expander("🎯 盯盘雷达", expanded=False):
        m_ticker = st.text_input("代码", "300750")
        m_target = st.number_input("目标价", 200.0)
        m_cond = st.selectbox("条件", ["跌破", "突破"])
        if st.button("🚀 启动/停止"):
            st.session_state.monitor_active = not st.session_state.monitor_active
            st.rerun()
        
        if st.session_state.monitor_active:
            st.markdown(f"<div class='monitor-box'>📡 监控中...<br>{m_ticker} @ {m_target}</div>", unsafe_allow_html=True)
            # 简单刷新逻辑
            df_m, info_m = get_stock_data_cloud(m_ticker)
            if df_m is not None:
                curr = df_m['Close'].iloc[-1]
                st.metric("现价", f"{curr:.2f}")
                if (m_cond=="跌破" and curr<m_target) or (m_cond=="突破" and curr>m_target):
                    st.error(f"触发！现价 {curr}")
                    st.session_state.monitor_active = False

    # 功能按钮
    c1, c2 = st.columns(2)
    if c1.button("🗑️ 清空"):
        st.session_state.messages = []
        st.session_state.chat_session = None
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    
    # 导出逻辑
    doc = Document()
    doc.add_heading("研报", 0)
    for m in st.session_state.messages:
        if not m.get("hidden"): doc.add_paragraph(f"{m['role']}: {m['content']}")
    bio = io.BytesIO(); doc.save(bio); bio.seek(0)
    c2.download_button("📥 导出", bio, "report.docx")

    st.divider()
    audio_val = mic_recorder(start_prompt="🎙️ 语音", stop_prompt="⏹️ 停止", key='mic')

# --- 主界面 ---
# 简单的标题，避免布局崩溃
c_t1, c_t2 = st.columns([1, 6])
with c_t1:
    if os.path.exists("avatar.png"): st.image("avatar.png", width=60)
    else: st.write("👩‍💼")
with c_t2: st.title("金鑫：云端财富合伙人")

# 渲染消息
for msg in st.session_state.messages:
    if msg.get("hidden"): continue
    
    # 简单的头像逻辑
    av = "avatar.png" if msg["role"] == "assistant" and os.path.exists("avatar.png") else None
    if msg["role"] == "user" and os.path.exists("user.png"): av = "user.png"
    
    with st.chat_message(msg["role"], avatar=av):
        if msg.get("code_output"): st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        st.markdown(re.sub(r'```python.*?```', '', msg["content"], flags=re.DOTALL))
        if msg.get("image_path") and os.path.exists(msg["image_path"]): st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]): st.audio(msg["audio_path"])

# 输入处理
prompt = st.chat_input("输入问题...")
user_in = None
if audio_val and audio_val['bytes']: user_in = transcribe_audio(audio_val['bytes'])
elif prompt: user_in = prompt

if user_in:
    st.session_state.messages.append({"role": "user", "content": user_in, "id": str(uuid.uuid4()), "timestamp": str(datetime.now())})
    # 保存
    with open(MEMORY_FILE, "w") as f: json.dump(st.session_state.messages, f)
    st.rerun()

# AI 响应
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with st.chat_message("assistant", avatar="avatar.png" if os.path.exists("avatar.png") else None):
        with st.spinner("思考中..."):
            try:
                if not st.session_state.chat_session: 
                    st.session_state.chat_session = get_model().start_chat()
                
                resp = st.session_state.chat_session.send_message(st.session_state.messages[-1]["content"])
                full_text = resp.text
                
                # 执行代码
                img_path = None; out_text = None
                codes = re.findall(r'```python(.*?)```', full_text, re.DOTALL)
                if codes: img_path, out_text = execute_local_code_and_save(codes[-1])
                
                # 显示
                if out_text: st.markdown(f"<div class='code-output'>{out_text}</div>", unsafe_allow_html=True)
                st.markdown(re.sub(r'```python.*?```', '', full_text, flags=re.DOTALL))
                if img_path: st.image(img_path)
                
                # 语音
                af = None
                spoken = get_spoken_response(full_text)
                if spoken:
                    ap = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.wav")
                    if save_audio_cloud(spoken, ap): 
                        st.audio(ap)
                        af = ap
                
                # 保存
                st.session_state.messages.append({
                    "role": "assistant", "content": full_text, "id": str(uuid.uuid4()),
                    "image_path": img_path, "audio_path": af, "code_output": out_text,
                    "timestamp": str(datetime.now())
                })
                with open(MEMORY_FILE, "w") as f: json.dump(st.session_state.messages, f)
                
            except Exception as e:
                st.error(f"发生错误: {e}")

# 盯盘刷新
if st.session_state.monitor_active:
    time.sleep(5)
    st.rerun()
