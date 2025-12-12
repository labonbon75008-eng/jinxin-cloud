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
import contextlib # 1. 核心修复：确保必须导入
import sys
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

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# 强制手机端按钮不换行 (CSS 黑科技)
st.markdown("""
<style>
    /* 强制操作区的列不换行 */
    div[data-testid="column"] {
        display: flex;
        flex-direction: column;
    }
    /* 针对手机端优化，强制水平排列 */
    @media (max-width: 640px) {
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            overflow-x: auto;
        }
        div[data-testid="stHorizontalBlock"] button {
            padding: 0px 5px !important;
            font-size: 12px !important;
        }
    }
    .stApp { background-color: #0e1117; }
    .avatar-img { width: 120px; height: 120px; border-radius: 50%; border: 3px solid #4CAF50; margin: 0 auto; display: block; }
    .main-title { text-align: center; font-size: 24px; font-weight: bold; color: white; margin-bottom: 10px; }
    .code-output { background-color: #e8f5e9; color: black !important; padding: 10px; border-radius: 5px; font-family: monospace; }
</style>
""", unsafe_allow_html=True)

# 核心路径
MEMORY_FILE = "investment_memory_v14.json"
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

# ================= 2. 静态资源内嵌 =================

# 2. 核心修复：内嵌 SVG 头像 (彻底解决黑屏/白框)
AVATAR_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<circle cx="50" cy="50" r="48" fill="#e0f2f1" stroke="#4CAF50" stroke-width="3"/>
<path d="M50 25 C35 25 25 35 25 50 C25 65 35 75 50 75 C65 75 75 65 75 50 C75 35 65 25 50 25 Z" fill="#b2dfdb"/>
<path d="M35 50 Q50 65 65 50" stroke="#004d40" stroke-width="3" fill="none"/>
<circle cx="40" cy="40" r="4" fill="#004d40"/>
<circle cx="60" cy="40" r="4" fill="#004d40"/>
<text x="50" y="90" font-size="10" text-anchor="middle" fill="#004d40">JIN XIN</text>
</svg>
"""
# 转为 Data URI 供 st.markdown 使用
AVATAR_DATA_URI = f"data:image/svg+xml;base64,{base64.b64encode(AVATAR_SVG.encode()).decode()}"

# ================= 3. 核心功能函数 =================

# --- A. 字体下载 ---
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

# --- B. 数据引擎 (极速版) ---
def get_stock_data_v14(ticker):
    """获取数据"""
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

    # Yahoo Chart
    df = None
    try:
        tk = yf.Ticker(y_sym)
        hist = tk.history(period="1mo")
        if not hist.empty: df = hist[['Close']]
    except: pass

    # 兜底
    if df is None and curr > 0:
        df = pd.DataFrame({'Close': [curr]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info_str

# --- C. AI 引擎 ---
@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    prompt = f"""
    你叫“金鑫”，用户的投资助理。当前时间：{datetime.now().strftime('%Y-%m-%d')}。
    要求：
    1. 必须调用 `get_stock_data_v14(code)`。
    2. 必须画图。
    3. 语气像真人聊天，亲切、有观点。
    代码模板：
    df, info = get_stock_data_v14("600309")
    if df is not None:
        print(info)
        plt.figure(figsize=(8, 4))
        plt.plot(df.index, df['Close'], color='#c2185b')
        plt.title("Trend")
        plt.grid(True)
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=prompt)

def execute_code(code_str):
    """3. 核心修复：确保 contextlib 可用"""
    img_path = None; output = ""; capture = io.StringIO()
    safe_code = '\n'.join([l for l in code_str.split('\n') if not l.strip().startswith(('import','from'))])
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4))
        # 强制使用全局的 contextlib
        with contextlib.redirect_stdout(capture):
            exec(safe_code, globals(), {'get_stock_data_v14':get_stock_data_v14, 'plt':plt, 'pd':pd, 'yf':yf})
        output = capture.getvalue()
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100); plt.close()
    except Exception as e: output = f"执行错误: {e}"
    return img_path, output

# --- D. 语音 ---
async def gen_voice(text, path):
    try: await edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(path); return True
    except: return False

def get_voice_res(text):
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        return model.generate_content(f"你是金鑫，将此内容转为聊天口语(80字内)：\n{text}").text
    except: return ""

def transcribe(audio_bytes):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

# --- E. 记忆与文件 ---
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

def create_doc(msgs, single_index=None):
    doc = Document(); doc.add_heading("金鑫研报", 0)
    target_msgs = [msgs[single_index]] if single_index is not None else msgs
    for m in target_msgs:
        if not m.get("hidden"):
            doc.add_heading(f"{m['role']}", 2); doc.add_paragraph(m.get("content",""))
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 4. 界面布局 (修复按钮) =================

# 状态
if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "monitor" not in st.session_state: st.session_state.monitor = False

if "sess" not in st.session_state:
    try:
        model = get_model()
        h = [{"role":("user" if m["role"]=="user" else "model"), "parts":[str(m["content"])]} for m in st.session_state.messages if not m.get("hidden")]
        st.session_state.sess = model.start_chat(history=h)
    except: pass

# --- 侧边栏 ---
with st.sidebar:
    st.markdown(f"<img src='{AVATAR_DATA_URI}' style='width:100px; display:block; margin:0 auto; border-radius:50%;'>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center'>金鑫</h3>", unsafe_allow_html=True)
    
    # 盯盘
    with st.expander("🎯 盯盘", expanded=True):
        m_code = st.text_input("代码", "300750")
        m_tgt = st.number_input("目标", 0.0)
        if st.button("🔴 启动/停止"):
            st.session_state.monitor = not st.session_state.monitor
            st.rerun()
        if st.session_state.monitor:
            st.info("📡 监控运行中...")
            _, info = get_stock_data_v14(m_code)
            if "现价" in info:
                try:
                    curr = float(re.search(r"现价: (\d+\.\d+)", info).group(1))
                    st.metric("实时价", curr)
                    if curr < m_tgt:
                        st.error("触发目标价！"); st.session_state.monitor = False
                except: pass

    st.divider()
    search = st.text_input("🔍 搜索")
    
    c1, c2 = st.columns(2)
    if c1.button("🗑️ 清空"):
        st.session_state.messages = []; st.session_state.sess = None; save_mem([])
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    c2.download_button("📥 导出", create_doc(st.session_state.messages), "all.docx")
    
    # 恢复隐藏
    with st.expander("👁️ 恢复"):
        for i, m in enumerate(st.session_state.messages):
            if m.get("hidden"):
                if st.button(f"恢复: {m['content'][:5]}...", key=f"rec_{i}"):
                    st.session_state.messages[i]["hidden"] = False; save_mem(st.session_state.messages); st.rerun()

# --- 主界面 ---
st.markdown("<div class='main-title'>你的投资助理</div>", unsafe_allow_html=True)
# 强制使用内嵌头像，绝不黑屏
st.markdown(f"<img src='{AVATAR_DATA_URI}' class='avatar-img'>", unsafe_allow_html=True)

# --- 消息渲染 ---
for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden"): continue
    if search and search not in str(msg['content']): continue

    av = AVATAR_DATA_URI if msg["role"] == "assistant" else "👨‍💼"
    
    with st.chat_message(msg["role"], avatar=av):
        if msg.get("code_output"): 
            st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        
        st.markdown(msg["content"])
        
        if msg.get("image_path") and os.path.exists(msg["image_path"]):
            st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]):
            st.audio(msg["audio_path"])
            
        # 操作区：折叠菜单 -> 强制4列
        with st.expander("⋮ 操作"):
            c_cp, c_hd, c_del, c_ex = st.columns(4)
            if c_cp.button("📋", key=f"cp_{i}"): st.code(msg["content"])
            if c_hd.button("🙈", key=f"hd_{i}"): 
                st.session_state.messages[i]["hidden"] = True; save_mem(st.session_state.messages); st.rerun()
            if c_del.button("🗑️", key=f"dl_{i}"): 
                del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()
            c_ex.download_button("📤", create_doc(st.session_state.messages, i), f"msg_{i}.docx", key=f"ex_{i}")

# --- 统一输入处理 (4. 核心修复：简化逻辑，保证响应) ---
st.markdown("---")
c_voice, c_text = st.columns([1, 5])

# 1. 语音
with c_voice:
    audio_val = mic_recorder(start_prompt="🎙️", stop_prompt="⏹️", key='mic')

# 2. 文字
text_input = st.chat_input("请输入问题...")

user_input = None
# 简单的互斥逻辑：有字先发字，没字看语音
if text_input:
    user_input = text_input
elif audio_val and audio_val['bytes']:
    # 每次录音只要有数据就识别，不搞ID锁了，防止锁死
    user_input = transcribe(audio_val['bytes'])

# 3. 执行
if user_input:
    # 记录
    st.session_state.messages.append({"role": "user", "content": user_input, "id": str(uuid.uuid4())})
    save_mem(st.session_state.messages)
    
    # 回答
    with st.chat_message("assistant", avatar=AVATAR_DATA_URI):
        with st.spinner("👩‍💼 思考中..."):
            try:
                if not st.session_state.sess: st.rerun()
                resp = st.session_state.sess.send_message(user_input)
                txt = resp.text
                
                # 代码图表
                img_p = None; out_t = None
                codes = re.findall(r'```python(.*?)```', txt, re.DOTALL)
                if codes: img_p, out_t = execute_code(codes[-1])
                
                # 语音生成
                af = None
                spoken = get_voice_res(txt[:500])
                if spoken:
                    af = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.mp3")
                    asyncio.run(gen_voice(spoken, af))
                
                # 保存
                st.session_state.messages.append({
                    "role": "assistant", "content": txt, "id": str(uuid.uuid4()),
                    "image_path": img_p, "audio_path": af, "code_output": out_t
                })
                save_mem(st.session_state.messages)
                st.rerun()
            except Exception as e:
                st.error(f"出错: {e}")

if st.session_state.monitor:
    time.sleep(5); st.rerun()
