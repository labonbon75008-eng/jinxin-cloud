import streamlit as st
import pandas as pd
import json
import time
import uuid
import re
import io
import base64
import requests
import warnings
import contextlib
import matplotlib
# 1. 强制后台绘图
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import yfinance as yf
from docx import Document
from datetime import datetime

# 尝试导入语音库
try:
    from streamlit_mic_recorder import mic_recorder
    import speech_recognition as sr
except ImportError:
    mic_recorder = None

import edge_tts
import google.generativeai as genai

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="📈", layout="wide")

# CSS: 手机端优化
st.markdown("""
<style>
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; }
    div[data-testid="stHorizontalBlock"] button { min-width: 60px !important; padding: 0px 5px !important; }
    .main-title { text-align: center; font-size: 26px; font-weight: bold; margin-bottom: 20px; }
    .avatar-img { width: 100px; height: 100px; border-radius: 50%; margin: 0 auto; display: block; object-fit: cover;}
    button[title="View fullscreen"] { display: none; }
</style>
""", unsafe_allow_html=True)

# 路径
MEMORY_FILE = "investment_memory_v21.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf" 

for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# API KEY
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    else:
        genai.configure(api_key="AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU")
except: pass

# ================= 2. 核心功能 =================

# 头像
DEFAULT_AVATAR = "https://api.dicebear.com/9.x/avataaars/png?seed=Jinxin&clothing=blazerAndShirt&hairColor=black&skinColor=light&accessories=glasses&top=longHairStraight"

def get_avatar():
    return DEFAULT_AVATAR

# 字体
def check_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get("https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf", timeout=5)
            with open(FONT_PATH, "wb") as f: f.write(r.content)
        except: pass
    if os.path.exists(FONT_PATH):
        fm.fontManager.addfont(FONT_PATH)
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
check_font()

# --- 数据引擎 ---
def get_stock_data(query):
    code_match = re.search(r"\d{6}", str(query))
    code = code_match.group() if code_match else "000001"
    
    info_str = f"代码: {code}"
    current_price = 0.0
    try:
        sina_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
        if len(code) == 5: sina_code = f"hk{code}"
        url = f"http://hq.sinajs.cn/list={sina_code}"
        r = requests.get(url, headers={'Referer':'https://finance.sina.com.cn'}, timeout=2)
        if len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            name = parts[0]
            if len(parts) > 3:
                val = parts[6] if "hk" in sina_code else parts[3]
                current_price = float(val)
                info_str = f"【{name}】 现价: {current_price}"
    except: pass

    df = None
    try:
        ticker = f"{code}.SS" if code.startswith('6') else (f"{code}.HK" if len(code)==5 else f"{code}.SZ")
        df = yf.Ticker(ticker).history(period="1mo")
        if df.empty: 
            idx = pd.date_range(end=datetime.now(), periods=5)
            df = pd.DataFrame({'Close': [current_price]*5}, index=idx)
    except: 
        idx = pd.date_range(end=datetime.now(), periods=5)
        df = pd.DataFrame({'Close': [100]*5}, index=idx)

    return df, info_str

# --- 代码执行 (带原生图表兜底) ---
def execute_code_safe(code_str, df_backup):
    img_path = None
    capture = io.StringIO()
    # 清洗
    code = code_str.replace("plt.show()", "")
    lines = [l for l in code.split('\n') if not l.strip().startswith(('import', 'from'))]
    safe_code = '\n'.join(lines)
    
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4))
        local_vars = {
            'get_stock_data': get_stock_data,
            'plt': plt, 'pd': pd, 'yf': yf, 'datetime': datetime, 
            'contextlib': contextlib
        }
        with contextlib.redirect_stdout(capture):
            exec(safe_code, globals(), local_vars)
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100); plt.close()
    except Exception as e:
        # 如果画图失败，返回 None，后面会用 st.line_chart 兜底
        print(f"绘图失败: {e}")
        pass
    
    return img_path

# --- AI ---
def get_ai_response(user_text):
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        _, real_info = get_stock_data(user_text)
        prompt = f"""
        你叫金鑫，投资顾问。当前时间：{datetime.now().strftime('%Y-%m-%d')}。
        用户问：{user_text}
        **参考数据**：{real_info}
        
        要求：
        1. 基于数据回答。
        2. 生成 Python 代码画图 (使用 df, info = get_stock_data("代码"))。
        3. 回答简练，像真人。
        """
        resp = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        return f"系统繁忙: {e}"

def transcribe(audio_bytes):
    if not audio_bytes: return None
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

# --- 记忆 ---
def load_mem():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f: return json.load(f)
        except: pass
    return []

def save_mem(msgs):
    serializable_msgs = []
    for m in msgs:
        temp = m.copy()
        if "chart_data" in temp: del temp["chart_data"] # 不存DataFrame
        serializable_msgs.append(temp)
    with open(MEMORY_FILE, "w") as f: json.dump(serializable_msgs, f)

def create_doc(msgs, idx=None):
    doc = Document(); doc.add_heading("金鑫研报", 0)
    targets = [msgs[idx]] if idx is not None else msgs
    for m in targets:
        if not m.get("hidden"):
            clean_t = re.sub(r'```.*?```', '', m.get("content",""), flags=re.DOTALL).strip()
            doc.add_heading(f"{m['role']}", 2); doc.add_paragraph(clean_t)
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 4. 界面布局 =================

if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "last_audio" not in st.session_state: st.session_state.last_audio = None

# --- 侧边栏 (语音放在这里！) ---
with st.sidebar:
    st.image(DEFAULT_AVATAR, width=100)
    st.markdown("<h3 style='text-align:center'>金鑫</h3>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("**🎙️ 语音输入**")
    # 语音组件放在 Sidebar，即使崩了也不影响主界面
    audio_text = None
    if mic_recorder:
        try:
            audio = mic_recorder(start_prompt="点击说话", stop_prompt="停止", key='mic_sidebar')
            if audio and audio['bytes']:
                if "last_audio_bytes" not in st.session_state or st.session_state.last_audio_bytes != audio['bytes']:
                    st.session_state.last_audio_bytes = audio['bytes']
                    with st.spinner("识别中..."):
                        audio_text = transcribe(audio['bytes'])
        except:
            st.error("语音组件加载失败")
    
    st.divider()
    if st.button("🗑️ 清空历史", use_container_width=True):
        st.session_state.messages = []
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    st.download_button("📥 导出记录", create_doc(st.session_state.messages), "all.docx", use_container_width=True)

# --- 主界面 ---
st.markdown("<div class='main-title'>您的全天候投资助理</div>", unsafe_allow_html=True)

# 1. 渲染消息
for i, msg in enumerate(st.session_state.messages):
    role = msg["role"]
    av = DEFAULT_AVATAR if role == "assistant" else "👨‍💼"
    if msg.get("hidden"): continue
    
    with st.chat_message(role, avatar=av):
        # 彻底移除代码显示
        clean_content = re.sub(r'```.*?```', '', msg["content"], flags=re.DOTALL).strip()
        st.write(clean_content)
        
        # 显示 Matplotlib 图片
        if msg.get("image_path") and os.path.exists(msg["image_path"]):
            st.image(msg["image_path"])
        # 显示原生图表 (兜底)
        elif "chart_data" in msg and msg["chart_data"] is not None:
            st.line_chart(msg["chart_data"])
            
        with st.expander("⋮ 操作"):
            c1, c2, c3, c4 = st.columns([1,1,1,1])
            if c1.button("📋", key=f"cp_{i}"): st.code(clean_content)
            if c2.button("🙈", key=f"hd_{i}"): 
                st.session_state.messages[i]["hidden"] = True; save_mem(st.session_state.messages); st.rerun()
            if c3.button("🗑️", key=f"del_{i}"): 
                del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()
            c4.download_button("📥", create_doc(st.session_state.messages, i), f"msg_{i}.docx", key=f"ex_{i}")

# 2. 输入处理
# 优先处理侧边栏传来的语音
new_prompt = None
if audio_text:
    new_prompt = audio_text

# 底部文字输入框 (永远显示)
text_input = st.chat_input("请输入股票代码或问题...")
if text_input:
    new_prompt = text_input

# 3. 响应逻辑
if new_prompt:
    st.session_state.messages.append({"role": "user", "content": new_prompt})
    save_mem(st.session_state.messages)
    
    with st.chat_message("assistant", avatar=DEFAULT_AVATAR):
        with st.spinner("分析中..."):
            full_response = get_ai_response(new_prompt)
            
            # 1. 尝试代码画图
            img_p = None
            df_backup = None # 备份数据用于原生画图
            
            # 提取数据做备份
            try:
                df_backup, _ = get_stock_data(new_prompt)
                if df_backup is not None: df_backup = df_backup['Close']
            except: pass

            code_match = re.findall(r'```python(.*?)```', full_response, re.DOTALL)
            if code_match:
                img_p = execute_code_safe(code_match[-1], None) # 尝试画图
            
            clean_display = re.sub(r'```.*?```', '', full_response, flags=re.DOTALL).strip()
            st.markdown(clean_display)
            
            if img_p:
                st.image(img_p)
            elif df_backup is not None:
                st.line_chart(df_backup) # Matplotlib 失败则用原生图表兜底
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": full_response,
                "image_path": img_p,
                "chart_data": df_backup if img_p is None else None # 只有没图时才存数据
            })
            save_mem(st.session_state.messages)
            
    st.rerun()
