import streamlit as st
import google.generativeai as genai
import os
# 【核心 1】强制后端，防止云端画图崩溃
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from docx import Document
from docx.shared import Inches
import re
import json
import time
import io
import uuid
import shutil
from datetime import datetime, timedelta
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
import asyncio
import edge_tts
import requests
import pandas as pd
import warnings
import contextlib
import sys
import yfinance as yf
from PIL import Image

# ================= 1. 系统配置 =================
warnings.filterwarnings("ignore")

st.set_page_config(page_title="金鑫 - 智能财富合伙人", page_icon="👩‍💼", layout="wide")

# 路径初始化
MEMORY_FILE = "investment_memory_cloud.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"

# 【核心修复】增加 exist_ok=True，防止 FileExistsError
for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API KEY (安全读取)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.warning("⚠️ 检测到未配置 Secrets，尝试使用临时 Key (可能不稳定)")
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU"

# ================= 2. 核心功能：数据与逻辑 =================

def load_avatar(filename, default_emoji):
    """加载头像，找不到就返回None"""
    extensions = ["png", "jpg", "jpeg", "PNG", "JPG"]
    base = filename.split('.')[0]
    for ext in extensions:
        p = f"{base}.{ext}"
        if os.path.exists(p): return p
    return None

# --- 数据引擎 (新浪 + Yahoo) ---
def get_sina_code(symbol):
    s = symbol.strip().upper().replace(".SS", "").replace(".SZ", "").replace(".HK", "")
    if s.isdigit():
        if len(s) == 5: return f"hk{s}" 
        if len(s) == 4: return f"hk0{s}" 
        if len(s) == 6:
            if s.startswith('6'): return f"sh{s}"
            if s.startswith('0') or s.startswith('3'): return f"sz{s}"
            if s.startswith('8') or s.startswith('4'): return f"bj{s}"
    return f"sh{s}" if s.isdigit() else s

def get_stock_data_v9(ticker_symbol):
    """V9 引擎：保证返回 df 和 info，绝不报错"""
    sina_code = get_sina_code(ticker_symbol)
    info_str = "暂无数据"
    current_price = 0.0
    
    # 1. Sina Realtime
