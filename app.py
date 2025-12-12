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
# 1. 强制后台绘图，防止云端崩溃
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import yfinance as yf
from docx import Document
from streamlit_mic_recorder import mic_recorder
import edge_tts
import speech_recognition as sr
import google.generativeai as genai
from datetime import datetime

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# CSS 强制手机端优化 (针对截图问题的修复)
st.markdown("""
<style>
    /* 强制操作区不换行，支持横向滑动 */
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
    }
    div[data-testid="stHorizontalBlock"] button {
        min-width: 60px !important;
        padding: 0px 5px !important;
    }
    /* 隐藏不必要的全屏按钮 */
    button[title="View fullscreen"] { display: none; }
    
    .main-title { text-align: center; font-size: 26px; font-weight: bold; color: white; margin-bottom: 10px; }
    .avatar-img { width: 120px; height: 120px; border-radius: 50%; border: 3px solid #4CAF50; margin: 0 auto; display: block; object-fit: cover; }
    .code-output { background-color: #f0f2f6; padding: 10px; border-radius: 5px; font-size: 0.9em; color: #333; }
</style>
""", unsafe_allow_html=True)

# 核心路径
MEMORY_FILE = "investment_memory_v19.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf" 

for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API KEY
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU" # 备用

# ================= 2. 核心功能函数 =================

# --- A. 字体下载与加载 (修复 RuntimeError) ---
def setup_font():
    # 1. 下载
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get("https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf")
            with open(FONT_PATH, "wb") as f: f.write(r.content)
        except: pass
    
    # 2. 尝试加载，失败则忽略 (防止程序崩溃)
    try:
        if os.path.exists(FONT_PATH):
            fm.fontManager.addfont(FONT_PATH)
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False
        else:
            plt.rcParams['font.sans-serif'] = ['Arial'] # 兜底
    except Exception:
        plt.rcParams['font.sans-serif'] = ['Arial'] # 再次兜底

setup_font()

# --- B. 头像 ---
DEFAULT_AVATAR = "https://api.dicebear.com/9.x/avataaars/png?seed=Jinxin&clothing=blazerAndShirt&hairColor=black&skinColor=light&accessories=glasses&top=longHairStraight"

def get_avatar():
    if os.path.exists("avatar.png"): return "avatar.png"
    return DEFAULT_AVATAR

# --- C. 数据引擎 ---
def get_stock_data(user_input):
    # 智能提取代码
    s = str(user_input).strip().upper()
    match = re.search(r"[0-9]{4,6}", s)
    if match: s = match.group()
    else: s = re.sub(r'[^A-Z0-9]', '', s)

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

    # 兜底数据 (防止无图)
    if df is None and curr > 0:
        df = pd.DataFrame({'Close': [curr]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info_str

# --- D. AI 引擎 (修复 sess 丢失) ---
@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    prompt = f"""
    你叫“金鑫”，投资助理。当前时间：{datetime.now().strftime('%Y-%m-%d')}。
    
    【任务】
    1. 用户问股价/走势时，**必须**写 Python 代码。
    2. 代码必须调用 `get_stock_data("代码")`。
    3. 代码必须用 `plt` 画图。
    
    【模板】
    ```python
    df, info = get_stock_data("300750")
    if df is not None:
        print(info)
        plt.figure(figsize=(8, 4))
        plt.plot(df.index, df['Close'], color='#c2185b')
        plt.title("Trend")
        plt.grid(True)
    ```
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=prompt)

def get_session():
    """每次调用强制检查 Session"""
    if "sess" not in st.session_state or st.session_state.sess is None:
        model = get_model()
        h = []
        for m in st.session_state.get("messages", []):
            if not m.get("hidden"):
                h.append({"role":("user" if m["role"]=="user" else "model"), "parts":[str(m["content"])]})
        st.session_state.sess = model.start_chat(history=h)
    return st.session_state.sess

def execute_code(code_str):
    img_path = None; output = ""; capture = io.StringIO()
    safe_code = code_str.replace("plt.show()", "# plt.show()")
    lines = [l for l in safe_code.split('\n') if not l.strip().startswith(('import','from'))]
    safe_code = '\n'.join(lines)

    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4))
        # 注入所有可能用到的库，防止 NameError
        with contextlib.redirect_stdout(capture):
            exec(safe_code, globals(), {
                'get_stock_data':get_stock_data, 
                'plt':plt, 'pd':pd, 'yf':yf, 'datetime':datetime,
                'contextlib': contextlib
            })
        output = capture.getvalue()
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100); plt.close()
    except Exception as e: output = f"绘图错误: {e}" # 捕获但不崩
    return img_path, output

# --- E. 语音 ---
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
            # 增加超时处理
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

# --- F. 记忆管理 ---
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

# 状态
if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "monitor" not in st.session_state: st.session_state.monitor = False
if "last_audio" not in st.session_state: st.session_state.last_audio = None

# --- 侧边栏 ---
with st.sidebar:
    st.image(get_avatar(), width=120)
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
st.markdown(f"<div style='display:flex;justify-content:center;margin-bottom:20px;'><img src='{get_avatar()}' class='avatar-img'></div>", unsafe_allow_html=True)

# --- 消息渲染 ---
for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden"): continue
    if search and search not in str(msg['content']): continue

    av = get_avatar() if msg["role"] == "assistant" else "👨‍💼"
    
    with st.chat_message(msg["role"], avatar=av):
        # 1. 结果框 (只显示结果，不显示代码文本)
        if msg.get("code_output"): 
            st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        
        # 2. 文本内容
        st.markdown(msg["content"])
        
        # 3. 图片
        if msg.get("image_path") and os.path.exists(msg["image_path"]):
            st.image(msg["image_path"])
