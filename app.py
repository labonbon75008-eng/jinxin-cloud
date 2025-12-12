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

# 【核心修复1】语音组件防崩导入：如果环境不支持，直接跳过，绝不报错卡死
try:
    from streamlit_mic_recorder import mic_recorder
except ImportError:
    mic_recorder = None

import edge_tts
import speech_recognition as sr
import google.generativeai as genai
from datetime import datetime
from PIL import Image

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# CSS 强制手机端优化 (针对截图问题的修复)
st.markdown("""
<style>
    /* 强制操作区不换行，允许横向滑动 */
    div[data-testid="stHorizontalBlock"] { 
        flex-wrap: nowrap !important; 
        overflow-x: auto !important; 
    }
    div[data-testid="stHorizontalBlock"] button { 
        min-width: 60px !important; 
        padding: 0px 5px !important; 
        white-space: nowrap !important;
    }
    .main-title { text-align: center; font-size: 26px; font-weight: bold; color: white; margin-bottom: 10px; }
    .avatar-img { width: 120px; height: 120px; border-radius: 50%; border: 3px solid #4CAF50; margin: 0 auto; display: block; object-fit: cover; }
    /* 隐藏不必要的全屏按钮 */
    button[title="View fullscreen"] { display: none; }
</style>
""", unsafe_allow_html=True)

# 核心路径
MEMORY_FILE = "investment_memory_v20.json"
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

# ================= 2. 静态资源 =================

# 【核心修复2】头像硬编码，防止 NameError，防止白板
DEFAULT_AVATAR = "[https://api.dicebear.com/9.x/avataaars/png?seed=Jinxin&clothing=blazerAndShirt&hairColor=black&skinColor=light&accessories=glasses&top=longHairStraight](https://api.dicebear.com/9.x/avataaars/png?seed=Jinxin&clothing=blazerAndShirt&hairColor=black&skinColor=light&accessories=glasses&top=longHairStraight)"

def get_avatar():
    return DEFAULT_AVATAR

def check_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get("[https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf](https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf)")
            with open(FONT_PATH, "wb") as f: f.write(r.content)
        except: pass
    if os.path.exists(FONT_PATH):
        fm.fontManager.addfont(FONT_PATH)
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
check_font()

# ================= 3. 核心业务逻辑 =================

def clean_text_display(text):
    """【核心修复3】彻底删除代码块，只留文字"""
    # 删除 ``` ... ``` 之间的所有内容 (包括换行)
    # 无论有无 python 标签，统统删掉
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    return text.strip()

# --- A. 数据引擎 ---
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
    
    # Sina
    try:
        url = f"[http://hq.sinajs.cn/list=](http://hq.sinajs.cn/list=){sina_code}"
        r = requests.get(url, headers={'Referer':'[https://finance.sina.com.cn](https://finance.sina.com.cn)'}, timeout=2)
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

    if df is None and curr > 0:
        df = pd.DataFrame({'Close': [curr]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info_str

# --- B. AI 引擎 ---
@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    prompt = f"""
    你叫“金鑫”，用户的投资助理。当前时间：{datetime.now().strftime('%Y-%m-%d')}。
    【铁律】
    1. 必须调用 `get_stock_data(code)` 获取数据。
    2. 必须用 `plt` 画图。
    3. 回答要亲切、自然。
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=prompt)

def execute_code(code_str):
    img_path = None; capture = io.StringIO()
    # 强制不显示图表弹窗
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

# --- C. 语音 ---
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

# --- D. 记忆管理 ---
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
            doc.add_heading(f"{m['role']}", 2); doc.add_paragraph(clean_text_display(m.get("content","")))
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 4. 界面布局 =================

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
                if st.button(f"恢复: {clean_text_display(m['content'])[:5]}...", key=f"rec_{i}"):
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
        # 1. 文本 (已清洗，不显示代码)
        st.markdown(clean_text_display(msg["content"]))
        
        # 2. 图片
        if msg.get("image_path") and os.path.exists(msg.get("image_path")):
            st.image(msg["image_path"])
        
        # 3. 语音
        if msg.get("audio_path") and os.path.exists(msg.get("audio_path")):
            st.audio(msg["audio_path"])
            
        with st.expander("⋮ 操作"):
            # 强制等宽布局
            c1, c2, c3, c4 = st.columns([1,1,1,1])
            if c1.button("📋", key=f"cp_{i}", help="复制"): st.code(clean_text_display(msg["content"]))
            if c2.button("🙈", key=f"hd_{i}", help="隐藏"): 
                st.session_state.messages[i]["hidden"] = True; save_mem(st.session_state.messages); st.rerun()
            if c3.button("🗑️", key=f"dl_{i}", help="删除"): 
                del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()
            c4.download_button("📥", create_doc(st.session_state.messages, i), f"msg_{i}.docx", key=f"ex_{i}", help="导出")

# --- 输入处理 (防崩核心) ---
st.markdown("---")
c_voice, c_text = st.columns([1, 5])

# 语音组件 (加防爆盾：如果 mic_recorder 没加载成功，直接跳过，不崩)
user_input = None
if mic_recorder:
    with c_voice:
        try:
            audio_val = mic_recorder(start_prompt="🎙️", stop_prompt="⏹️", key='mic')
            if audio_val and audio_val['bytes']:
                if audio_val['id'] != st.session_state.last_audio:
                    st.session_state.last_audio = audio_val['id']
                    with st.spinner("识别中..."):
                        user_input = transcribe(audio_val['bytes'])
                        if not user_input: st.toast("未检测到语音")
        except: 
            st.caption("语音不可用") # 降级处理

# 文字组件 (放在外层，确保永远显示)
text_input = st.chat_input("请输入问题...")
if text_input: user_input = text_input

if user_input:
    # 记录
    st.session_state.messages.append({"role": "user", "content": user_input, "id": str(uuid.uuid4())})
    save_mem(st.session_state.messages)
    
    # 回答
    with st.chat_message("assistant", avatar=get_avatar()):
        with st.spinner("思考中..."):
            try:
                if not st.session_state.sess: st.rerun()
                
                # 提示词注入
                _, real_info = get_stock_data(user_input[:10])
                sys_prompt = f"""
                当前时间：{datetime.now().strftime('%Y-%m-%d')}。
                用户查询：{user_input}。
                **真实数据(必须参考)**：{real_info}。
                要求：
                1. 必须基于上述真实数据回答。
                2. 必须生成 Python 代码画图。
                """
                
                resp = st.session_state.sess.send_message(sys_prompt)
                txt = resp.text
                
                # 执行代码 + 清洗
                img_p = None
                codes = re.findall(r'```python(.*?)```', txt, re.DOTALL)
                if codes: img_p = execute_code(codes[-1])
                
                # 清洗后的文本 (不含代码)
                clean_txt = clean_text_display(txt)
                
                # 语音生成
                af = None
                spoken = get_voice_res(clean_txt[:500])
                if spoken:
                    af = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.mp3")
                    asyncio.run(gen_voice(spoken, af))
                
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": clean_txt, # 只存清洗后的文本
                    "id": str(uuid.uuid4()),
                    "image_path": img_p, 
                    "audio_path": af
                })
                save_mem(st.session_state.messages)
                st.rerun()
            except Exception as e:
                st.error(f"出错: {e}")
                st.session_state.sess = None

if st.session_state.monitor:
    time.sleep(5); st.rerun()
