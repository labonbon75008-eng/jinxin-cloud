import streamlit as st
import os  # 【核心修复】补回了漏掉的 os 库
import json
import time
import uuid
import re
import io
import base64
import requests
import pandas as pd
import warnings
import contextlib
import matplotlib
# 1. 强制后台绘图，防止云端卡死
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import yfinance as yf
from docx import Document
from datetime import datetime, timedelta

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
st.set_page_config(page_title="金鑫 - 智能投资助理", page_icon="📈", layout="wide")

# CSS: 强制手机按钮不换行 + 隐藏代码块容器
st.markdown("""
<style>
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; }
    div[data-testid="stHorizontalBlock"] button { min-width: 60px !important; padding: 0px 5px !important; }
    .avatar-img { width: 120px; height: 120px; border-radius: 50%; border: 3px solid #4CAF50; margin: 0 auto; display: block; }
    button[title="View fullscreen"] { display: none; }
</style>
""", unsafe_allow_html=True)

# 核心变量
MEMORY_FILE = "investment_memory_v23.json"
FONT_PATH = "SimHei.ttf" 
AUDIO_DIR = "audio_cache"
CHARTS_DIR = "charts"

# 自动创建目录
for d in [CHARTS_DIR, AUDIO_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# API KEY
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    else:
        genai.configure(api_key="AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU")
except: pass

# ================= 2. 核心资源 (内嵌防丢) =================

# 金鑫头像 (Base64 SVG)
AVATAR_B64 = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMjAgMTIwIiBmaWxsPSJub25lIj48Y2lyY2xlIGN4PSI2MCIgY3k9IjYwIiByPSI2MCIgZmlsbD0iI2UzZjJmZCIvPjxwYXRoIGQ9Ik02MCAyNWMtMTkuMyAwLTM1IDE1LjctMzUgMzVzMTUuNyAzNSAzNSAzNSAzNS0xNS43IDM1LTM1LTE1LjctMzUtMzUtMzV6bTAgMTBjMTMuOCAwIDI1IDExLjIgMjUgMjVzLTExLjIgMjUtMjUgMjUtMjUtMTEuMi0yNS0yNXExMS4yLTI1IDI1LTI1eiIgZmlsbD0iIzE1NjVjMCIvPjxwYXRoIGQ9Ik02MCA4MGMtMTYuNiAwLTMwIDEzLjQtMzAgMzBoNjBjMC0xNi42LTEzLjQtMzAtMzAtMzB6IiBmaWxsPSIjNDU1YTY0Ii8+PC9zdmc+"

def check_font():
    # 自动下载字体
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

# ================= 3. 业务逻辑 =================

def get_stock_data(query):
    code_match = re.search(r"\d{6}", str(query))
    code = code_match.group() if code_match else "000001"
    
    info_str = f"代码: {code}"
    current_price = 0.0
    try:
        sina_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
        url = f"http://hq.sinajs.cn/list={sina_code}"
        r = requests.get(url, headers={'Referer':'https://finance.sina.com.cn'}, timeout=2)
        if len(r.text) > 20:
            parts = r.text.split('"')[1].split(',')
            name = parts[0]
            current_price = float(parts[3])
            info_str = f"【{name}】 现价: {current_price}"
    except: pass

    df = None
    try:
        ticker = f"{code}.SS" if code.startswith('6') else f"{code}.SZ"
        df = yf.Ticker(ticker).history(period="1mo")
        if df.empty: 
            idx = pd.date_range(end=datetime.now(), periods=5)
            df = pd.DataFrame({'Close': [current_price]*5}, index=idx)
    except: 
        idx = pd.date_range(end=datetime.now(), periods=5)
        df = pd.DataFrame({'Close': [100,101,102,101,103]}, index=idx)

    return df, info_str

def execute_code_in_memory(code_str):
    code = code_str.replace("plt.show()", "")
    lines = [l for l in code.split('\n') if not l.strip().startswith(('import', 'from'))]
    safe_code = '\n'.join(lines)
    
    buf = io.BytesIO()
    try:
        plt.close('all'); plt.figure(figsize=(8, 4))
        local_vars = {
            'get_stock_data': get_stock_data,
            'plt': plt, 'pd': pd, 'yf': yf, 'datetime': datetime
        }
        with contextlib.redirect_stdout(io.StringIO()):
            exec(safe_code, globals(), local_vars)
        if plt.get_fignums():
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            return buf
    except Exception as e: pass
    return None

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
        return f"系统繁忙，请稍后再试: {e}"

def transcribe(audio_bytes):
    if not audio_bytes: return None
    r = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            return r.recognize_google(r.record(source), language='zh-CN')
    except: return None

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
        if "chart_buf" in temp: del temp["chart_buf"] 
        serial
