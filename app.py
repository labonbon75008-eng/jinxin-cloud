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
from PIL import Image

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# 核心路径
MEMORY_FILE = "investment_memory_v18.json"
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

# ================= 2. 静态资源 (Base64 内嵌 - 绝不白板) =================

# 金鑫头像 (职业女性 SVG)
ASSISTANT_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="48" fill="#e0f2f1" stroke="#009688" stroke-width="2"/><path d="M50 25c-15 0-28 12-28 28s13 35 28 35 28-19 28-35-13-28-28-28zm0 10c8 0 15 7 15 15s-7 15-15 15-15-7-15-15 7-15 15-15zm0 50c-12 0-22-8-22-18 0-5 10-8 22-8s22 3 22 8c0 10-10 18-22 18z" fill="#00695c"/></svg>
"""

# 用户头像 (男士 SVG)
USER_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="48" fill="#e3f2fd" stroke="#2196f3" stroke-width="2"/><circle cx="50" cy="40" r="18" fill="#1565c0"/><path d="M25 80c0-15 10-25 25-25s25 10 25 25" fill="#1565c0"/></svg>
"""

def get_avatar_uri(role):
    """获取头像 Data URI：优先用户上传，否则用内嵌"""
    # 1. 检查 Session 中是否有临时上传的头像
    if role == "assistant" and st.session_state.get("uploaded_assistant"):
        return st.session_state.uploaded_assistant
    if role == "user" and st.session_state.get("uploaded_user"):
        return st.session_state.uploaded_user
    
    # 2. 检查本地文件
    filename = "avatar.png" if role == "assistant" else "user.png"
    if os.path.exists(filename):
        try:
            with open(filename, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return f"data:image/png;base64,{b64}"
        except: pass
    
    # 3. 使用内嵌 SVG (兜底)
    svg = ASSISTANT_SVG if role == "assistant" else USER_SVG
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"

# 字体下载
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

# ================= 3. 核心逻辑 =================

def clean_text(text):
    """【核心修复】剔除代码块，只保留文字"""
    # 移除 ```python ... ``` 块
    text = re.sub(r'```python.*?```', '', text, flags=re.DOTALL)
    # 移除行内代码
    return text.strip()

def get_stock_data(user_input):
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
    
    【铁律】
    1. 函数 `get_stock_data` 返回 `df` 和 `info`。必须写成 `df, info = ...`。
    2. `info` 是字符串，直接 print。
    3. 必须画图。
    4. 回答要亲切自然。
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=prompt)

def execute_code(code_str):
    img_path = None; capture = io.StringIO()
    safe_code = code_str.replace("plt.show()", "# plt.show()")
    lines = [l for l in safe_code.split('\n') if not l.strip().startswith(('import','from'))]
    safe_code = '\n'.join(lines)

    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4))
        with contextlib.redirect_stdout(capture):
            exec(safe_code, globals(), {
                'get_stock_data':get_stock_data, 
                'plt':plt, 'pd':pd, 'yf':yf, 'datetime':datetime,
                'contextlib': contextlib
            })
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100); plt.close()
    except Exception as e: pass
    return img_path

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

def load_mem():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f: return [m for m in json.load(f) if isinstance(m, dict) and "role" in m]
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
            doc.add_heading(f"{m['role']}", 2); doc.add_paragraph(clean_text(m.get("content","")))
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 4. 界面布局 =================

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    /* 强制手机端按钮不换行 */
    @media (max-width: 640px) {
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; }
        div[data-testid="stHorizontalBlock"] button { white-space: nowrap !important; padding: 0px 5px !important; min-width: 60px !important; }
    }
    .main-title { text-align: center; font-size: 28px; font-weight: bold; margin-bottom: 5px; color: white; }
    div[data-testid="stSidebar"] button { width: 100%; }
</style>
""", unsafe_allow_html=True)

# 状态
if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "monitor" not in st.session_state: st.session_state.monitor = False
if "last_audio" not in st.session_state: st.session_state.last_audio = None

# Session
if "sess" not in st.session_state or st.session_state.sess is None:
    try:
        model = get_model()
        h = [{"role":("user" if m["role"]=="user" else "model"), "parts":[str(m["content"])]} for m in st.session_state.messages if not m.get("hidden")]
        st.session_state.sess = model.start_chat(history=h)
    except: pass

# --- 侧边栏 ---
with st.sidebar:
    # 动态显示头像
    st.image(get_avatar_uri("assistant"), width=120)
    st.markdown("<h3 style='text-align:center'>金鑫</h3>", unsafe_allow_html=True)
    
    # 增加上传功能
    with st.expander("🖼️ 更换头像"):
        up_ai = st.file_uploader("助理头像", type=["png","jpg"])
        if up_ai:
            b64 = base64.b64encode(up_ai.read()).decode()
            st.session_state.uploaded_assistant = f"data:image/png;base64,{b64}"
            st.rerun()
        
        up_user = st.file_uploader("您的头像", type=["png","jpg"])
        if up_user:
            b64 = base64.b64encode(up_user.read()).decode()
            st.session_state.uploaded_user = f"data:image/png;base64,{b64}"
            st.rerun()

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
st.markdown(f"""
<div style="display:flex; justify-content:center; margin-bottom:20px;">
    <img src="{get_avatar_uri('assistant')}" style="width:120px; height:120px; border-radius:50%; border:3px solid #4CAF50; object-fit:cover;">
</div>
""", unsafe_allow_html=True)

# --- 消息渲染 ---
for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden"): continue
    if search and search not in str(msg['content']): continue

    av = get_avatar_uri("assistant") if msg["role"] == "assistant" else get_avatar_uri("user")
    
    with st.chat_message(msg["role"], avatar=av):
        # 1. 隐藏了 code_output 的显示，只保留结果
        
        # 2. 文本 (清洗掉代码块)
        clean_content = clean_text(msg["content"])
        st.markdown(clean_content)
        
        # 3. 图片
        if msg.get("image_path") and os.path.exists(msg["image_path"]):
            st.image(msg["image_path"])
        
        # 4. 语音
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]):
            st.audio(msg["audio_path"])
            
        with st.expander("⋮ 操作"):
            c1, c2, c3, c4 = st.columns([1,1,1,1])
            if c1.button("📋", key=f"cp_{i}"): st.code(clean_content)
            if c2.button("🙈", key=f"hd_{i}"): 
                st.session_state.messages[i]["hidden"] = True; save_mem(st.session_state.messages); st.rerun()
            if c3.button("🗑️", key=f"dl_{i}"): 
                del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()
            c4.download_button("📥", create_doc(st.session_state.messages, i), f"msg_{i}.docx", key=f"ex_{i}", help="导出")

# --- 输入处理 ---
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
        with st.spinner("语音识别中..."):
            user_input = transcribe(audio_val['bytes'])
            if not user_input:
                st.warning("⚠️ 未检测到语音，请大声一点重试")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input, "id": str(uuid.uuid4())})
    save_mem(st.session_state.messages)
    st.rerun()

# 触发回答
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_msg = st.session_state.messages[-1]
    
    with st.chat_message("assistant", avatar=get_avatar_uri("assistant")):
        with st.spinner("👩‍💼 正在分析..."):
            try:
                if not st.session_state.sess: st.rerun()
                
                resp = st.session_state.sess.send_message(last_msg["content"])
                txt = resp.text
                
                img_p = None; out_t = None
                codes = re.findall(r'```python(.*?)```', txt, re.DOTALL)
                if codes: img_p = execute_code(codes[-1])
                
                af = None
                spoken = get_voice_res(clean_text(txt)[:500])
                if spoken:
                    af = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.mp3")
                    asyncio.run(gen_voice(spoken, af))
                
                st.session_state.messages.append({
                    "role": "assistant", "content": txt, "id": str(uuid.uuid4()),
                    "image_path": img_p, "audio_path": af, "code_output": "Hidden" # 不再保存冗余代码
                })
                save_mem(st.session_state.messages)
                st.rerun()
            except Exception as e:
                st.error(f"出错: {e}")
                st.session_state.sess = None

if st.session_state.monitor:
    time.sleep(5); st.rerun()
