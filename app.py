import streamlit as st
import os
import sys
import time
import json
import uuid
import re
import io
import warnings
import asyncio
from datetime import datetime, timedelta

# ================= 1. 启动配置 =================
st.set_page_config(page_title="金鑫 - 智能财富合伙人", page_icon="👩‍💼", layout="wide")
warnings.filterwarnings("ignore")

# ================= 2. 环境安全加载 =================
try:
    import matplotlib
    matplotlib.use('Agg') # 强制后台画图
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    from docx import Document
    from docx.shared import Inches
    from streamlit_mic_recorder import mic_recorder
    import speech_recognition as sr
    import edge_tts
    import requests
    import pandas as pd
    import yfinance as yf
    from PIL import Image
    import google.generativeai as genai
    import contextlib
except ImportError as e:
    st.error(f"🚨 环境缺失: {e}")
    st.stop()

# ================= 3. 核心变量初始化 =================
MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"

for d in [CHARTS_DIR, AUDIO_DIR]:
    try: os.makedirs(d, exist_ok=True)
    except: pass

# API KEY
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU"

# ================= 4. 核心功能函数 =================

def load_avatar(filename):
    """加载头像"""
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
        p = f"{filename}.{ext}"
        if os.path.exists(p): return p
    return None

def get_stock_data_v11(ticker_symbol):
    """V11 数据引擎：增强港股识别"""
    s = ticker_symbol.strip().upper().replace(".SS","").replace(".SZ","").replace(".HK","")
    
    # 智能识别后缀
    sina_code = ""
    y_sym = ""
    
    if s.isdigit():
        if len(s) == 3: # 输入 700 -> 00700
            sina_code = f"hk00{s}"
            y_sym = f"00{s}.HK"
        elif len(s) == 5: # 00700
            sina_code = f"hk{s}"
            y_sym = f"{s}.HK"
        elif len(s) == 4:
            sina_code = f"hk0{s}"
            y_sym = f"0{s}.HK"
        elif s.startswith('6'):
            sina_code = f"sh{s}"
            y_sym = f"{s}.SS"
        elif s.startswith('0') or s.startswith('3'):
            sina_code = f"sz{s}"
            y_sym = f"{s}.SZ"
        elif s.startswith('8') or s.startswith('4'):
            sina_code = f"bj{s}"
            y_sym = f"{s}.SS" # 临时处理
    else:
        # 美股
        sina_code = f"gb_{s.lower()}"
        y_sym = s

    info = "暂无数据"; price = 0.0
    
    # 1. Sina (极速)
    try:
        url = f"http://hq.sinajs.cn/list={sina_code}"
        r = requests.get(url, timeout=2, proxies={"http":None,"https":None})
        # 港股返回格式略有不同，做个兼容
        if len(r.text) > 20:
            content = r.text.split('"')[1]
            parts = content.split(',')
            
            if "hk" in sina_code: # 港股格式
                # 英文名, 英文名, 开盘, 昨收, 最高, 最低, 当前...
                name = parts[1]
                curr = float(parts[6])
                prev = float(parts[3])
            else: # A股格式
                name = parts[0]
                curr = float(parts[3])
                prev = float(parts[2])
                
            pct = ((curr-prev)/prev)*100 if prev!=0 else 0
            info = f"【{name}】 现价: {curr:.2f} ({pct:+.2f}%)"
            price = curr
    except: pass

    # 2. Yahoo Chart (画图)
    df = None
    try:
        tk = yf.Ticker(y_sym)
        hist = tk.history(period="1mo")
        if not hist.empty: df = hist[['Close']]
    except: pass

    # 3. 兜底画图 (防止无图报错)
    if df is None and price > 0:
        df = pd.DataFrame({'Close': [price]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info

# --- 语音 ---
async def generate_audio(text, path):
    try:
        await edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(path)
        return True
    except: return False

def save_audio(text, path):
    try: asyncio.run(generate_audio(text, path)); return True
    except: return False

def transcribe(bytes_data):
    try:
        r = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(bytes_data)) as source:
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

# --- AI (核心修正：严禁 seaborn) ---
@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    
    # 铁律指令
    sys_prompt = f"""
    你叫“金鑫”，私人财富顾问。当前日期:{datetime.now().strftime('%Y-%m-%d')}。
    
    【技术铁律 - 绝对遵守】
    1. 获取数据必须且只能调用 `get_stock_data_v11(ticker)`。
    2. **严禁使用 seaborn (sns)**！只允许使用 `matplotlib.pyplot` (plt) 画图。
    3. 画图代码不要包含 `plt.show()`，不要包含中文注释（防止乱码）。
    4. 必须画图。
    
    【代码模板】
    df, info = get_stock_data_v11("00700") # 腾讯
    if df is not None:
        print(info)
        plt.figure(figsize=(10, 4))
        plt.plot(df.index, df['Close'], color='#c2185b')
        plt.title("Price Trend")
        plt.grid(True)
    else:
        print(f"Error: {{info}}")
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=sys_prompt)

def run_code(code):
    img = None; out = "运行完成"
    # 清洗代码：移除 import，防止 AI 再次引入 seaborn
    safe_code = '\n'.join([l for l in code.split('\n') if not l.strip().startswith(('import','from'))])
    
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(10, 4))
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            # 注入变量
            exec(safe_code, globals(), {'get_stock_data_v11':get_stock_data_v11,'plt':plt,'pd':pd,'yf':yf})
        out = capture.getvalue()
        if plt.get_fignums():
            fn = f"chart_{int(time.time())}.png"
            img = os.path.join(CHARTS_DIR, fn)
            plt.savefig(img, bbox_inches='tight'); plt.close()
    except Exception as e: out = f"代码执行错误: {e}"
    return img, out

# --- 记忆 ---
def load_mem():
    data = []
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE,"r") as f:
                raw = json.load(f)
                if isinstance(raw, list): 
                    data = [x for x in raw if isinstance(x, dict) and "role" in x]
        except: pass
    return data

def save_mem(data):
    try:
        with open(MEMORY_FILE,"w") as f: json.dump(data, f)
    except: pass

def get_docx(msgs):
    doc = Document(); doc.add_heading("研报",0)
    for m in msgs:
        if not m.get("hidden"):
            doc.add_heading(f"{m['role']}",2); doc.add_paragraph(m.get("content",""))
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 5. 界面逻辑 =================

# 样式
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stSidebar"] img { border-radius: 50%; border: 3px solid #4CAF50; }
    .stChatMessage { background-color: rgba(255,255,255,0.05); }
    .code-output { background-color: #e8f5e9; color: black !important; padding: 10px; border-radius: 5px; }
    .monitor-box { background:#e3f2fd; color:#1565c0; padding:10px; border-radius:5px; text-align:center; }
</style>
""", unsafe_allow_html=True)

# 状态
if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "audio_id" not in st.session_state: st.session_state.audio_id = None
if "monitor" not in st.session_state: st.session_state.monitor = False

# Session
if "sess" not in st.session_state:
    try:
        h = [{"role":("user" if m["role"]=="user" else "model"),"parts":[str(m["content"])]} for m in st.session_state.messages if not m.get("hidden")]
        st.session_state.sess = get_model().start_chat(history=h)
    except: pass

# 头像
av_ai = load_avatar("avatar")
av_user = load_avatar("user")
def_img = "https://api.dicebear.com/9.x/avataaars/svg?seed=Jin"

# --- 侧边栏 ---
with st.sidebar:
    if av_ai: st.image(av_ai, use_container_width=True)
    else: st.image(def_img, width=100)
    st.title("金鑫 - 控制台")

    # 盯盘
    with st.expander("🎯 盯盘", expanded=False):
        m_code = st.text_input("代码", "300750")
        m_price = st.number_input("价格", 0.0)
        if st.button("🚀 启停"):
            st.session_state.monitor = not st.session_state.monitor
            st.rerun()
        if st.session_state.monitor:
            st.markdown(f"<div class='monitor-box'>监控中...</div>", unsafe_allow_html=True)
            _, info = get_stock_data_v11(m_code)
            if "现价" in info:
                try:
                    curr = float(re.search(r"现价: (\d+\.\d+)", info).group(1))
                    st.metric("现价", curr)
                    if m_price > 0 and curr < m_price: st.error("触发跌破！")
                except: pass

    # 功能
    col_clr, col_exp = st.columns(2)
    if col_clr.button("🗑️ 清空"):
        st.session_state.messages = []; st.session_state.sess = None
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    
    docx = get_docx(st.session_state.messages)
    col_exp.download_button("📥 导出", docx, "report.docx")
    
    st.divider()
    audio_val = mic_recorder(start_prompt="🎙️", stop_prompt="⏹️", key='mic')

# --- 主区 ---
c_title_1, c_title_2 = st.columns([1, 6])
with c_title_1:
    if av_ai: st.image(av_ai, width=60)
    else: st.write("👩‍💼")
with c_title_2: st.subheader("金鑫：云端财富合伙人")

# 消息
for i, m in enumerate(st.session_state.messages):
    if not isinstance(m, dict) or m.get("hidden"): continue
    
    # 头像选择
    cur_av = av_ai if m["role"]=="assistant" else av_user
    if not cur_av: cur_av = "👩‍💼" if m["role"]=="assistant" else "👨‍💼"
    
    with st.chat_message(m["role"], avatar=cur_av):
        if m.get("code_output"): st.code(m["code_output"], language="text")
        st.markdown(re.sub(r'```python.*?```', '', m.get("content",""), flags=re.DOTALL))
        if m.get("image_path") and os.path.exists(m["image_path"]): st.image(m["image_path"])
        if m.get("audio_path") and os.path.exists(m["audio_path"]): st.audio(m["audio_path"])
        
        # 操作区 (使用唯一Key防止冲突)
        c_h, c_d = st.columns([1, 10])
        if c_h.button("🗑️", key=f"del_{i}"):
            del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()

# 输入
user_txt = st.chat_input("输入问题...")
final_in = None

if audio_val and audio_val['bytes']:
    if audio_val['id'] != st.session_state.audio_id:
        st.session_state.audio_id = audio_val['id']
        final_in = transcribe(audio_val['bytes'])
elif user_txt:
    final_in = user_txt

if final_in:
    st.session_state.messages.append({"role":"user", "content":final_in, "id":str(uuid.uuid4())})
    save_mem(st.session_state.messages)
    st.rerun()

# 响应
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last = st.session_state.messages[-1]
    with st.chat_message("assistant", avatar=av_ai if av_ai else "👩‍💼"):
        with st.spinner("思考中..."):
            try:
                if not st.session_state.sess: st.rerun()
                resp = st.session_state.sess.send_message(last["content"])
                txt = resp.text
                
                # 代码执行
                img_p = None; out_t = None
                codes = re.findall(r'```python(.*?)```', txt, re.DOTALL)
                if codes: img_p, out_t = run_code(codes[-1])
                
                if out_t: st.code(out_t)
                st.markdown(re.sub(r'```python.*?```', '', txt, flags=re.DOTALL))
                if img_p: st.image(img_p)
                
                # 语音
                af = None
                try:
                    spoken = get_spoken_response(txt[:500]) 
                    if spoken:
                        fn = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.mp3")
                        if save_audio(spoken, fn): 
                            st.audio(fn)
                            af = fn
                except: pass
                
                st.session_state.messages.append({
                    "role":"assistant", "content":txt, "id":str(uuid.uuid4()),
                    "image_path":img_p, "audio_path":af, "code_output":out_t
                })
                save_mem(st.session_state.messages)
            except Exception as e: st.error(f"出错: {e}")

if st.session_state.monitor:
    time.sleep(5); st.rerun()
