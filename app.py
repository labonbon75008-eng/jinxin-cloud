import streamlit as st
import os
import json
import time
import uuid
import re
import io
import asyncio
import requests
import pandas as pd
import warnings
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
from PIL import Image

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")
st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# 核心路径
MEMORY_FILE = "investment_memory_v13.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf" 

# 自动修复文件夹
for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API KEY 读取
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.error("🚨 严重错误：未配置 API Key！请去 Streamlit Secrets 填写。")
    st.stop()

# ================= 2. 核心功能函数 =================

# --- A. 字体下载 (解决乱码) ---
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

# --- B. 头像加载 (解决白框) ---
def get_avatar_image():
    """尝试加载本地，失败则用网络图兜底"""
    # 穷举所有可能的后缀
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
        if os.path.exists(f"avatar.{ext}"): return f"avatar.{ext}"
    # 兜底图
    return "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin&clothing=blazerAndShirt&hairColor=black"

# --- C. 数据引擎 ---
def get_stock_data_v13(ticker):
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
    
    # Sina 实时
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

    # Yahoo K线
    df = None
    try:
        tk = yf.Ticker(y_sym)
        hist = tk.history(period="1mo")
        if not hist.empty: df = hist[['Close']]
    except: pass

    # 兜底数据
    if df is None and curr > 0:
        df = pd.DataFrame({'Close': [curr]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info_str

# --- D. AI 引擎 ---
@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    prompt = f"""
    你叫“金鑫”，用户的投资助理。当前时间：{datetime.now().strftime('%Y-%m-%d')}。
    要求：
    1. 必须调用 `get_stock_data_v13(code)`。
    2. 必须画图。
    3. 语气像真人聊天，亲切、有观点，不要机械读数据。
    代码模板：
    df, info = get_stock_data_v13("600309")
    if df is not None:
        print(info)
        plt.figure(figsize=(8, 4))
        plt.plot(df.index, df['Close'], color='#c2185b')
        plt.title("Trend")
        plt.grid(True)
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=prompt)

def execute_code(code_str):
    img_path = None; output = ""; capture = io.StringIO()
    safe_code = '\n'.join([l for l in code_str.split('\n') if not l.strip().startswith(('import','from'))])
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4))
        with contextlib.redirect_stdout(capture):
            exec(safe_code, globals(), {'get_stock_data_v13':get_stock_data_v13, 'plt':plt, 'pd':pd, 'yf':yf})
        output = capture.getvalue()
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100); plt.close()
    except Exception as e: output = f"执行错误: {e}"
    return img_path, output

# --- E. 语音 ---
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

# --- F. 记忆与文件 ---
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

def create_doc(content):
    doc = Document(); doc.add_paragraph(content)
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

def create_full_doc(msgs):
    doc = Document(); doc.add_heading("金鑫研报", 0)
    for m in msgs:
        if not m.get("hidden"):
            doc.add_heading(f"{m['role']}", 2); doc.add_paragraph(m.get("content",""))
    b = io.BytesIO(); doc.save(b); b.seek(0); return b

# ================= 4. 界面布局 (严格按要求重构) =================

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    /* 标题居中 */
    .main-title { 
        text-align: center; font-size: 28px; font-weight: bold; margin-bottom: 5px; color: white;
    }
    
    /* 头像居中 */
    .avatar-container {
        display: flex; justify-content: center; margin-bottom: 20px;
    }
    .avatar-img {
        width: 150px; height: 150px; border-radius: 50%; border: 3px solid #4CAF50; object-fit: cover;
    }
    
    /* 侧边栏按钮等宽 */
    div[data-testid="stSidebar"] button { width: 100%; }
    
    /* 绿色数据框 */
    .code-output { background-color: #e8f5e9; color: #000000 !important; padding: 10px; border-radius: 5px; font-family: monospace; }
</style>
""", unsafe_allow_html=True)

# 状态
if "messages" not in st.session_state: st.session_state.messages = load_mem()
if "monitor" not in st.session_state: st.session_state.monitor = False
# 语音标记
if "last_voice_id" not in st.session_state: st.session_state.last_voice_id = None

if "sess" not in st.session_state:
    try:
        model = get_model()
        h = [{"role":("user" if m["role"]=="user" else "model"), "parts":[str(m["content"])]} for m in st.session_state.messages if not m.get("hidden")]
        st.session_state.sess = model.start_chat(history=h)
    except: pass

# --- 侧边栏 ---
with st.sidebar:
    st.image(get_avatar_image(), use_container_width=True)
    st.markdown("<h3 style='text-align:center'>金鑫</h3>", unsafe_allow_html=True)
    
    # 盯盘
    with st.expander("🎯 价格雷达 (盯盘)", expanded=True):
        m_code = st.text_input("代码", "300750")
        m_tgt = st.number_input("目标", 0.0)
        m_type = st.selectbox("条件", ["跌破", "突破"])
        if st.button("🔴 启动盯盘" if not st.session_state.monitor else "⏹️ 停止盯盘"):
            st.session_state.monitor = not st.session_state.monitor
            st.rerun()
        if st.session_state.monitor:
            st.info("📡 监控运行中...")
            _, info = get_stock_data_v13(m_code)
            if "现价" in info:
                try:
                    curr = float(re.search(r"现价: (\d+\.\d+)", info).group(1))
                    st.metric("实时价", curr)
                    if (m_type=="跌破" and curr<m_tgt) or (m_type=="突破" and curr>m_tgt):
                        st.error("触发目标价！")
                        st.session_state.monitor = False
                except: pass

    st.divider()
    
    # 搜索
    search = st.text_input("🔍 搜索记录")
    
    # 清空与导出 (等宽)
    c1, c2 = st.columns(2)
    if c1.button("🗑️ 清空"):
        st.session_state.messages = []; st.session_state.sess = None; save_mem([])
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
    
    c2.download_button("📥 导出", create_full_doc(st.session_state.messages), "report.docx")
    
    # 恢复隐藏
    with st.expander("👁️ 恢复消息"):
        for i, m in enumerate(st.session_state.messages):
            if m.get("hidden"):
                if st.button(f"恢复: {m['content'][:8]}...", key=f"rec_{i}"):
                    st.session_state.messages[i]["hidden"] = False; save_mem(st.session_state.messages); st.rerun()

# --- 主界面标题区 ---
st.markdown("<div class='main-title'>你的投资助理</div>", unsafe_allow_html=True)
st.markdown(f"""
<div class='avatar-container'>
    <img src='{get_avatar_image()}' class='avatar-img'>
</div>
""", unsafe_allow_html=True)

# --- 消息渲染 ---
for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden"): continue
    if search and search not in str(msg['content']): continue

    av = get_avatar_image() if msg["role"] == "assistant" else "👨‍💼"
    
    with st.chat_message(msg["role"], avatar=av):
        if msg.get("code_output"): 
            st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        
        st.markdown(msg["content"])
        
        if msg.get("image_path") and os.path.exists(msg["image_path"]):
            st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]):
            st.audio(msg["audio_path"])
            
        # 操作区：折叠菜单 -> 点击展开 -> 一行排列 (完美解决手机端堆叠)
        with st.expander("⋮ 操作菜单"):
            c_cp, c_hd, c_del, c_exp = st.columns(4)
            if c_cp.button("复制", key=f"cp_{i}"): st.code(msg["content"])
            if c_hd.button("隐藏", key=f"hd_{i}"): 
                st.session_state.messages[i]["hidden"] = True; save_mem(st.session_state.messages); st.rerun()
            if c_del.button("删除", key=f"dl_{i}"): 
                del st.session_state.messages[i]; save_mem(st.session_state.messages); st.rerun()
            # 单条导出
            c_exp.download_button("导出", create_doc(msg["content"]), f"msg_{i}.docx", key=f"ex_{i}")

# --- 核心交互逻辑 (修复不响应) ---

# 1. 语音按钮
c_voice, _ = st.columns([1, 4])
with c_voice:
    audio_data = mic_recorder(start_prompt="🎙️ 语音提问", stop_prompt="⏹️ 停止", key='mic')

# 2. 文字输入
text_input = st.chat_input("请输入问题...")

# 3. 逻辑判断
user_input = None

# 优先处理文字，其次处理新的语音
if text_input:
    user_input = text_input
elif audio_data and audio_data['bytes']:
    if audio_data['id'] != st.session_state.last_voice_id:
        st.session_state.last_voice_id = audio_data['id']
        with st.spinner("👂 正在识别..."):
            user_input = transcribe(audio_data['bytes'])

# 4. 执行
if user_input:
    # 记录
    st.session_state.messages.append({"role": "user", "content": user_input, "id": str(uuid.uuid4())})
    save_mem(st.session_state.messages)
    
    # 回答
    with st.chat_message("assistant", avatar=get_avatar_image()):
        with st.spinner("👩‍💼 思考中..."):
            try:
                if not st.session_state.sess: st.rerun()
                resp = st.session_state.sess.send_message(user_input)
                txt = resp.text
                
                # 图表
                img_p = None; out_t = None
                codes = re.findall(r'```python(.*?)```', txt, re.DOTALL)
                if codes: img_p, out_t = execute_code(codes[-1])
                
                # 语音
                af = None
                spoken = get_voice_res(txt[:500])
                if spoken:
                    af = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.mp3")
                    asyncio.run(gen_voice(spoken, af))
                
                # 存入
                st.session_state.messages.append({
                    "role": "assistant", "content": txt, "id": str(uuid.uuid4()),
                    "image_path": img_p, "audio_path": af, "code_output": out_t
                })
                save_mem(st.session_state.messages)
                st.rerun()
            except Exception as e:
                st.error(f"出错: {e}")

# 盯盘自动刷新
if st.session_state.monitor:
    time.sleep(5); st.rerun()
