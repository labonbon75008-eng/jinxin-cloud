import streamlit as st
import google.generativeai as genai
import os
import time
import json
import uuid
import re
import io
import asyncio
import threading
import requests
import pandas as pd
import warnings
import contextlib
import sys
import matplotlib
# 1. 强制后台绘图，防止云端报错
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import yfinance as yf
from docx import Document
from docx.shared import Inches
from streamlit_mic_recorder import mic_recorder
from PIL import Image
import edge_tts
import speech_recognition as sr

# ================= 1. 系统核心配置 =================
warnings.filterwarnings("ignore")

st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# 路径初始化
MEMORY_FILE = "investment_memory_v12.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf" 

for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API KEY
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.error("🚨 请在 Streamlit Secrets 中配置 GEMINI_API_KEY")
    st.stop()

# ================= 2. 核心功能函数 =================

# --- A. 字体与头像 ---
def check_and_download_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get("https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf")
            with open(FONT_PATH, "wb") as f: f.write(r.content)
        except: pass
    if os.path.exists(FONT_PATH):
        fm.fontManager.addfont(FONT_PATH)
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False

check_and_download_font()

def get_avatar_image():
    """获取头像，优先本地，无则网络"""
    for ext in ["png", "jpg", "jpeg"]:
        if os.path.exists(f"avatar.{ext}"): return f"avatar.{ext}"
    return "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin&clothing=blazerAndShirt"

# --- B. 极速数据源 ---
def get_stock_data_v12(ticker_symbol):
    s = ticker_symbol.strip().upper().replace(".SS","").replace(".SZ","").replace(".HK","")
    
    # 代码适配
    sina_code = s; y_sym = s
    if s.isdigit():
        if len(s) == 5: sina_code = f"hk{s}"; y_sym = f"{s}.HK"
        elif len(s) == 4: sina_code = f"hk0{s}"; y_sym = f"0{s}.HK"
        elif s.startswith('6'): sina_code = f"sh{s}"; y_sym = f"{s}.SS"
        else: sina_code = f"sz{s}"; y_sym = f"{s}.SZ"
    else: sina_code = f"gb_{s.lower()}"

    info_str = "暂无数据"; current_price = 0.0
    
    # 新浪接口
    try:
        url = f"http://hq.sinajs.cn/list={sina_code}"
        r = requests.get(url, headers={'Referer':'https://finance.sina.com.cn'}, timeout=2, proxies={"http":None,"https":None})
        if len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            if len(parts) > 3:
                name = parts[0]
                if "hk" in sina_code: name = parts[1]; curr = float(parts[6]); prev = float(parts[3])
                else: curr = float(parts[3]); prev = float(parts[2])
                pct = ((curr - prev) / prev) * 100 if prev != 0 else 0
                info_str = f"【{name}】 现价: {curr:.2f} ({pct:+.2f}%)"
                current_price = curr
    except: pass

    # Yahoo K线
    df = None
    try:
        tk = yf.Ticker(y_sym)
        hist = tk.history(period="1mo")
        if not hist.empty: df = hist[['Close']]
    except: pass

    # 兜底画图
    if df is None and current_price > 0:
        df = pd.DataFrame({'Close': [current_price]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info_str

# --- C. AI 引擎 ---
@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    sys_prompt = f"""
    你叫“金鑫”，用户的投资助理。当前时间：{datetime.now().strftime('%Y-%m-%d')}。
    要求：
    1. 必须调用 `get_stock_data_v12(code)` 获取数据。
    2. 必须画图。
    3. 回答风格要像真人聊天，专业但亲切。
    
    代码模板：
    df, info = get_stock_data_v12("600309")
    if df is not None:
        print(info)
        plt.figure(figsize=(8, 4))
        plt.plot(df.index, df['Close'], color='#c2185b')
        plt.title("Trend")
        plt.grid(True)
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=sys_prompt)

def execute_code(code_str):
    img_path = None; output = ""; capture = io.StringIO()
    # 清洗代码
    safe_code = '\n'.join([l for l in code_str.split('\n') if not l.strip().startswith(('import','from'))])
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4))
        with contextlib.redirect_stdout(capture):
            exec(safe_code, globals(), {'get_stock_data_v12':get_stock_data_v12, 'plt':plt, 'pd':pd, 'yf':yf})
        output = capture.getvalue()
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100)
            plt.close()
    except Exception as e: output = f"执行错误: {e}"
    return img_path, output

# --- D. 语音 ---
async def gen_voice(text, path):
    try:
        await edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(path)
        return True
    except: return False

def get_voice_res(text):
    if not text: return ""
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        res = model.generate_content(f"你是金鑫。将此内容转为口语（80字内），像聊天一样：\n{text}")
        return res.text
    except: return ""

def transcribe(audio_bytes):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

# --- E. 记忆 ---
def load_mem():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                return [m for m in data if isinstance(m, dict) and "role" in m]
        except: pass
    return []

def save_mem(msgs):
    try:
        with open(MEMORY_FILE, "w", encoding='utf-8') as f: json.dump(msgs, f, ensure_ascii=False)
    except: pass

def create_doc(msgs):
    doc = Document(); doc.add_heading("金鑫研报", 0)
    for m in msgs:
        if not m.get("hidden"):
            doc.add_heading(f"{m['role']}", 2); doc.add_paragraph(m.get("content",""))
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 4. 界面逻辑 =================

# 样式优化
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    /* 侧边栏图片 */
    div[data-testid="stSidebar"] img { border-radius: 50%; border: 2px solid #4CAF50; }
    /* 主界面头像居中 */
    .avatar-container { display: flex; justify-content: center; margin-bottom: 20px; }
    .avatar-container img { border-radius: 15px; width: 150px; height: 150px; object-fit: cover; }
    /* 标题居中 */
    .main-title { text-align: center; font-size: 28px; font-weight: bold; margin-top: -20px; margin-bottom: 10px; }
    
    .stChatMessage { background-color: rgba(255,255,255,0.05); }
    .code-output { background-color: #e8f5e9; color: #000000 !important; padding: 10px; border-radius: 5px; font-family: monospace; }
    /* 按钮样式 */
    div[data-testid="stButton"] button { width: 100%; }
</style>
""", unsafe_allow_html=True)

# 状态
if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "monitor" not in st.session_state: st.session_state.monitor = False
# 语音防抖
if "last_audio" not in st.session_state: st.session_state.last_audio = None

if "sess" not in st.session_state:
    try:
        model = get_model()
        h = [{"role":("user" if m["role"]=="user" else "model"), "parts":[str(m["content"])]} for m in st.session_state.messages if not m.get("hidden")]
        st.session_state.sess = model.start_chat(history=h)
    except: pass

# --- 侧边栏 ---
with st.sidebar:
    st.image(get_avatar_image(), use_container_width=True, caption="👩‍💼 金鑫")
    
    # 盯盘
    with st.expander("🎯 盯盘", expanded=True):
        m_code = st.text_input("代码", "300750")
        m_price = st.number_input("目标", 0.0)
        m_type = st.selectbox("条件", ["跌破", "突破"])
        if st.button("🚀 启停"):
            st.session_state.monitor = not st.session_state.monitor
            st.rerun()
        if st.session_state.monitor:
            st.info("📡 监控中...")
            _, info = get_stock_data_v12(m_code)
            if "现价" in info:
                try:
                    curr = float(re.search(r"现价: (\d+\.\d+)", info).group(1))
                    st.metric("实时价", curr)
                    if (m_type=="跌破" and curr<m_price) or (m_type=="突破" and curr>m_price):
                        st.error("触发！"); st.session_state.monitor = False
                except: pass

    st.divider()
    search = st.text_input("🔍 搜索")
    
    # 按钮对齐
    c1, c2 = st.columns(2)
    if c1.button("🗑️ 清空"):
        st.session_state.messages = []; st.session_state.sess = None; save_mem([])
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    
    doc = create_doc(st.session_state.messages)
    c2.download_button("📥 导出", doc, "report.docx")
    
    st.divider()
    # 语音组件 (放在Sidebar防止挤占主界面)
    audio_data = mic_recorder(start_prompt="🎙️ 点击说话", stop_prompt="⏹️ 停止", key='mic')

# --- 主界面 ---
# 标题居中，图片在下 (修复 Req 7)
st.markdown("<div class='main-title'>你的投资助理</div>", unsafe_allow_html=True)
st.markdown(f"""
<div class='avatar-container'>
    <img src='{get_avatar_image()}' style='width:150px; border-radius:12px;'>
</div>
""", unsafe_allow_html=True)

# 渲染消息
for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden"): continue
    if search and search not in str(msg['content']): continue # 搜索过滤

    av = get_avatar_image() if msg["role"] == "assistant" else "👨‍💼"
    with st.chat_message(msg["role"], avatar=av):
        if msg.get("code_output"): st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        st.markdown(msg["content"])
        if msg.get("image_path") and os.path.exists(msg["image_path"]): st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]): st.audio(msg["audio_path"])
        
        # 操作栏 (修复 Req 6)
        c_op1, c_op2, c_op3 = st.columns([1,1,1])
        if c_op1.button("复制", key=f"cp_{i}"): st.code(msg["content"])
        if c_op2.button("隐藏", key=f"hd_{i}"): 
            st.session_state.messages[i]["hidden"] = True; save_mem(st.session_state.messages); st.rerun()
        if c_op3.button("删除", key=f"del_{i}"): 
            del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()

# --- 核心输入逻辑 (修复 Req 1 & 3 & 8) ---
user_input = None
text_input = st.chat_input("请输入问题...")

# 逻辑：优先响应文字，其次响应新的语音
if text_input:
    user_input = text_input
elif audio_data and audio_data['bytes'] != st.session_state.last_audio:
    st.session_state.last_audio = audio_data['bytes'] # 更新指纹防止死循环
    with st.spinner("👂 正在识别语音..."):
        user_input = transcribe(audio_data['bytes'])

# 执行回答
if user_input:
    # 1. 记录提问
    st.session_state.messages.append({"role": "user", "content": user_input, "id": str(uuid.uuid4())})
    save_mem(st.session_state.messages)
    
    # 2. 生成回答
    with st.chat_message("assistant", avatar=get_avatar_image()):
        with st.spinner("👩‍💼 金鑫正在分析..."):
            try:
                if not st.session_state.sess: st.rerun()
                resp = st.session_state.sess.send_message(user_input)
                txt = resp.text
                
                # 代码执行
                img_p = None; out_t = None
                codes = re.findall(r'```python(.*?)```', txt, re.DOTALL)
                if codes: img_p, out_t = execute_code(codes[-1])
                
                # 语音生成
                af = None
                spoken = get_voice_res(txt[:500])
                if spoken:
                    af = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.mp3")
                    asyncio.run(gen_voice(spoken, af))
                
                # 显示结果
                if out_t: st.markdown(f"<div class='code-output'>{out_t}</div>", unsafe_allow_html=True)
                st.markdown(txt)
                if img_p: st.image(img_p)
                if af: st.audio(af)
                
                # 保存
                st.session_state.messages.append({
                    "role": "assistant", "content": txt, "id": str(uuid.uuid4()),
                    "image_path": img_p, "audio_path": af, "code_output": out_t
                })
                save_mem(st.session_state.messages)
                
            except Exception as e:
                st.error(f"出错: {e}")
    st.rerun()

# 盯盘刷新
if st.session_state.monitor:
    time.sleep(5); st.rerun()
