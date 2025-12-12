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
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import yfinance as yf
from docx import Document
from docx.shared import Inches
from streamlit_mic_recorder import mic_recorder
from PIL import Image
import edge_tts
import speech_recognition as sr

# ================= 1. 系统底层配置 =================
warnings.filterwarnings("ignore")
matplotlib.use('Agg') # 强制后台绘图，防崩

st.set_page_config(page_title="金鑫 - 投资助理", page_icon="👩‍💼", layout="wide")

# 核心路径
MEMORY_FILE = "investment_memory_v11.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf" # 中文字体文件

for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API KEY
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.error("🚨 请在 Streamlit Secrets 中配置 GEMINI_API_KEY")
    st.stop()

# ================= 2. 基础设施建设 =================

# --- A. 字体自动修复 (解决图表乱码) ---
def check_and_download_font():
    """检测并下载中文字体，确保云端图表显示正常"""
    if not os.path.exists(FONT_PATH):
        # 下载开源的中文字体 (文泉驿微米黑)
        font_url = "https://github.com/StellarCN/scp_zh/raw/master/fonts/SimHei.ttf"
        try:
            r = requests.get(font_url)
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
        except: pass
    
    if os.path.exists(FONT_PATH):
        fm.fontManager.addfont(FONT_PATH)
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False

check_and_download_font()

# --- B. 头像加载 ---
def get_avatar_image():
    """获取金鑫头像，优先本地，否则网络"""
    for ext in ["png", "jpg", "jpeg"]:
        if os.path.exists(f"avatar.{ext}"): return f"avatar.{ext}"
    return "https://api.dicebear.com/9.x/avataaars/svg?seed=Jinxin&clothing=blazerAndShirt"

# --- C. 记忆管理 (同步核心) ---
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
                return [m for m in data if isinstance(m, dict) and "role" in m]
        except: pass
    return []

def save_memory(messages):
    try:
        with open(MEMORY_FILE, "w", encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    except: pass

# ================= 3. 数据与AI引擎 =================

# --- 极速数据源 ---
def get_stock_data_v11(ticker_symbol):
    """
    V11数据引擎：
    1. 自动识别 A股/港股/美股
    2. 新浪获取实时报价 (毫秒级)
    3. Yahoo 获取 K线数据 (画图用)
    """
    s = ticker_symbol.strip().upper().replace(".SS","").replace(".SZ","").replace(".HK","")
    
    # 1. 构造代码
    sina_code = s
    y_sym = s
    if s.isdigit():
        if len(s) == 5: sina_code = f"hk{s}"; y_sym = f"{s}.HK"
        elif len(s) == 4: sina_code = f"hk0{s}"; y_sym = f"0{s}.HK"
        elif s.startswith('6'): sina_code = f"sh{s}"; y_sym = f"{s}.SS"
        else: sina_code = f"sz{s}"; y_sym = f"{s}.SZ"
    else: sina_code = f"gb_{s.lower()}" # 美股

    info_str = "暂无数据"
    current_price = 0.0
    
    # 2. 新浪实时
    try:
        url = f"http://hq.sinajs.cn/list={sina_code}"
        r = requests.get(url, headers={'Referer':'https://finance.sina.com.cn'}, timeout=2, proxies={"http":None,"https":None})
        if len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            if len(parts) > 3:
                name = parts[0]
                if "hk" in sina_code: # 港股格式
                    name = parts[1]; curr = float(parts[6]); prev = float(parts[3])
                else: # A股格式
                    curr = float(parts[3]); prev = float(parts[2])
                
                pct = ((curr - prev) / prev) * 100 if prev != 0 else 0
                info_str = f"【{name}】 现价: {curr:.2f} ({pct:+.2f}%)"
                current_price = curr
    except: pass

    # 3. Yahoo 历史
    df = None
    try:
        tk = yf.Ticker(y_sym)
        hist = tk.history(period="1mo")
        if not hist.empty: df = hist[['Close']]
    except: pass

    # 4. 兜底画图
    if df is None and current_price > 0:
        df = pd.DataFrame({'Close': [current_price]*5}, index=pd.date_range(end=datetime.now(), periods=5))
    
    return df, info_str

# --- AI 生成 ---
@st.cache_resource
def get_model():
    genai.configure(api_key=API_KEY)
    sys_prompt = f"""
    你叫“金鑫”，用户的投资助理。当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}。
    
    【指令】
    1. 必须调用 `get_stock_data_v11(code)` 获取数据。
    2. A股代码直接写数字。
    3. 必须在最后画图。
    
    【模板】
    df, info = get_stock_data_v11("600309")
    if df is not None:
        print(info)
        plt.figure(figsize=(8, 4)) # 图片不用很大
        plt.plot(df.index, df['Close'], color='#c2185b')
        plt.title("Trend")
        plt.grid(True)
    else:
        print(f"Error: {{info}}")
    """
    return genai.GenerativeModel("gemini-3-pro-preview", system_instruction=sys_prompt)

def execute_code(code_str):
    """沙盒执行代码，确保画图"""
    img_path = None; output = "执行完毕"; capture = io.StringIO()
    # 清洗：移除 import
    safe_code = '\n'.join([l for l in code_str.split('\n') if not l.strip().startswith(('import','from'))])
    
    try:
        plt.close('all'); plt.clf(); plt.figure(figsize=(8, 4)) # 控制图片大小
        with contextlib.redirect_stdout(capture):
            exec(safe_code, globals(), {'get_stock_data_v11':get_stock_data_v11, 'plt':plt, 'pd':pd, 'yf':yf})
        output = capture.getvalue()
        
        if plt.get_fignums():
            fname = f"chart_{int(time.time())}.png"
            img_path = os.path.join(CHARTS_DIR, fname)
            plt.savefig(img_path, bbox_inches='tight', dpi=100) # dpi=100 保证清晰且不大
            plt.close()
    except Exception as e: output = f"执行错误: {e}"
    return img_path, output

# --- 语音服务 ---
async def gen_voice(text, path):
    try:
        # 使用晓晓，更像真人聊天
        await edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural").save(path)
        return True
    except: return False

def get_voice_response(text):
    """生成口语化回复"""
    if not text: return ""
    try:
        model = genai.GenerativeModel("gemini-3-pro-preview")
        res = model.generate_content(f"你是金鑫。请将这段分析转化为像朋友聊天一样的口语回复（80字以内），不要念枯燥的数据：\n{text}")
        return res.text
    except: return ""

def transcribe_audio(audio_bytes):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

# ================= 4. 页面布局与逻辑 =================

# CSS 深度定制 (满足按钮宽度、文字居中等要求)
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    /* 侧边栏按钮等宽 */
    div[data-testid="stSidebar"] button { 
        width: 100% !important; 
    }
    
    /* 启动界面文字居中 */
    .title-text {
        text-align: center;
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 20px;
    }
    
    /* 图片圆角 */
    img { border-radius: 10px; }
    
    /* 消息卡片 */
    .stChatMessage { background-color: rgba(255,255,255,0.05); }
    
    /* 绿色数据框 */
    .code-output { 
        background-color: #e8f5e9; color: #000000 !important; 
        padding: 10px; border-radius: 5px; font-family: monospace; 
    }
</style>
""", unsafe_allow_html=True)

# 状态初始化
if "messages" not in st.session_state: st.session_state.messages = load_memory()
if "monitor_active" not in st.session_state: st.session_state.monitor_active = False
if "chat_session" not in st.session_state:
    try:
        model = get_model()
        h = [{"role":("user" if m["role"]=="user" else "model"), "parts":[str(m["content"])]} for m in st.session_state.messages if not m.get("hidden")]
        st.session_state.chat_session = model.start_chat(history=h)
    except: pass

# --- 侧边栏 ---
with st.sidebar:
    # 1. 盯盘
    with st.expander("🎯 价格雷达 (盯盘)", expanded=True):
        m_code = st.text_input("代码", "300750")
        m_price = st.number_input("目标", 0.0)
        m_cond = st.selectbox("条件", ["跌破", "突破"])
        
        # 按钮样式统一
        if st.button("🔴 启动盯盘" if not st.session_state.monitor_active else "⏹️ 停止盯盘", type="primary" if not st.session_state.monitor_active else "secondary"):
            st.session_state.monitor_active = not st.session_state.monitor_active
            st.rerun()
            
        if st.session_state.monitor_active:
            st.info("📡 监控中...")
            _, info = get_stock_data_v11(m_code)
            if "现价" in info:
                try:
                    curr = float(re.search(r"现价: (\d+\.\d+)", info).group(1))
                    st.metric("实时价", curr)
                    if (m_cond=="跌破" and curr<m_price) or (m_cond=="突破" and curr>m_price):
                        st.error("触发！"); st.session_state.monitor_active = False
                except: pass

    st.divider()
    
    # 2. 搜索
    search = st.text_input("🔍 搜索记录")
    
    # 3. 按钮组 (等宽)
    c1, c2 = st.columns(2)
    if c1.button("🗑️ 清空"):
        st.session_state.messages = []; st.session_state.chat_session = None
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.rerun()
        
    # 导出 Word
    doc = Document()
    doc.add_heading("投资研报", 0)
    for m in st.session_state.messages:
        if not m.get("hidden"):
            doc.add_heading(f"{m['role']}:", 2)
            doc.add_paragraph(m['content'])
    b = io.BytesIO(); doc.save(b); b.seek(0)
    c2.download_button("📥 导出", b, "report.docx")

# --- 主界面 (Req 7) ---
# 文字居中，图片在下
st.markdown("<div class='title-text'>你的投资助理</div>", unsafe_allow_html=True)
c_img1, c_img2, c_img3 = st.columns([1, 1, 1])
with c_img2:
    st.image(get_avatar_image(), use_container_width=True)

# 渲染消息 (Req 6 & 9)
for i, msg in enumerate(st.session_state.messages):
    if msg.get("hidden"): continue
    
    # 搜索过滤
    if search and search not in str(msg['content']): continue

    av = get_avatar_image() if msg["role"] == "assistant" else "👨‍💼"
    with st.chat_message(msg["role"], avatar=av):
        if msg.get("code_output"): st.markdown(f"<div class='code-output'>{msg['code_output']}</div>", unsafe_allow_html=True)
        st.markdown(msg["content"])
        if msg.get("image_path") and os.path.exists(msg["image_path"]): st.image(msg["image_path"])
        if msg.get("audio_path") and os.path.exists(msg["audio_path"]): st.audio(msg["audio_path"])
        
        # 操作栏
        col_op1, col_op2, col_op3, col_op4 = st.columns([1, 1, 1, 5])
        if col_op1.button("复制", key=f"cp_{i}"): st.code(msg["content"]) # 变通实现复制
        if col_op2.button("隐藏", key=f"hd_{i}"): 
            st.session_state.messages[i]["hidden"] = True; save_memory(st.session_state.messages); st.rerun()
        if col_op3.button("删除", key=f"del_{i}"): 
            del st.session_state.messages[i]; save_memory(st.session_state.messages); st.rerun()

# 恢复隐藏消息的功能
if st.sidebar.checkbox("显示已隐藏的消息"):
    for i, msg in enumerate(st.session_state.messages):
        if msg.get("hidden"):
            st.warning(f"已隐藏: {msg['content'][:20]}...")
            if st.button("恢复", key=f"rec_{i}"):
                st.session_state.messages[i]["hidden"] = False; save_memory(st.session_state.messages); st.rerun()

# --- 输入处理 (Req 1, 3, 8) ---
# 语音与文字统一处理
user_input = None

# 语音按钮 (横向长度与上方一致)
audio_val = mic_recorder(start_prompt="🎙️ 点击说话 (语音提问)", stop_prompt="⏹️ 停止", key='mic')

# 文字输入
text_val = st.chat_input("请输入问题...")

if audio_val and audio_val['bytes']:
    # 使用 ID 防止死循环
    if audio_val['id'] != st.session_state.get('last_audio_id'):
        st.session_state.last_audio_id = audio_val['id']
        user_input = transcribe_audio(audio_val['bytes'])
elif text_val:
    user_input = text_val

# 执行逻辑
if user_input:
    # 1. 记录用户提问
    st.session_state.messages.append({"role": "user", "content": user_input, "id": str(uuid.uuid4())})
    save_memory(st.session_state.messages)
    
    # 2. 生成回答
    with st.chat_message("assistant", avatar=get_avatar_image()):
        with st.spinner("思考中..."):
            try:
                if not st.session_state.chat_session: st.rerun()
                
                # LLM 生成
                resp = st.session_state.chat_session.send_message(user_input)
                full_text = resp.text
                
                # 代码执行 (Req 2)
                img_path = None; out_text = None
                codes = re.findall(r'```python(.*?)```', full_text, re.DOTALL)
                if codes: 
                    img_path, out_text = execute_code(codes[-1])
                
                # 语音生成 (Req 4 - 聊天式)
                af_path = None
                spoken_text = get_spoken_response(full_text)
                if spoken_text:
                    af_path = os.path.join(AUDIO_DIR, f"v_{int(time.time())}.mp3")
                    asyncio.run(gen_voice(spoken_text, af_path))
                
                # 保存结果
                msg_data = {
                    "role": "assistant", "content": full_text, "id": str(uuid.uuid4()),
                    "image_path": img_path, "audio_path": af_path, "code_output": out_text
                }
                st.session_state.messages.append(msg_data)
                save_memory(st.session_state.messages)
                st.rerun() # 强制刷新显示
                
            except Exception as e:
                st.error(f"发生错误: {e}")

# 盯盘自动刷新
if st.session_state.monitor_active:
    time.sleep(5); st.rerun()
