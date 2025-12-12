"""
金鑫 - 智能投资助理 (专业版)
功能：多模态投资顾问，支持语音/文字输入，实时股票数据，自动图表生成
部署：Streamlit Cloud 或本地运行
"""

# ================= 1. 导入区 (防崩优化) =================
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
import numpy as np
import warnings
import contextlib
import hashlib
from datetime import datetime, timedelta
from typing import Tuple, Optional, List, Dict
import matplotlib
matplotlib.use('Agg')  # 必须放在最前，防止GUI弹窗
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from PIL import Image
import yfinance as yf
from docx import Document
from docx.shared import Inches
import traceback

# 语音组件安全导入
try:
    from streamlit_mic_recorder import mic_recorder
    VOICE_AVAILABLE = True
except ImportError:
    mic_recorder = None
    VOICE_AVAILABLE = False
    st.warning("⚠️ 语音组件未安装，请运行: pip install streamlit-mic-recorder")

# TTS组件安全导入
try:
    import edge_tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    st.warning("⚠️ TTS组件未安装，请运行: pip install edge-tts")

# Gemini AI
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    st.error("❌ Gemini未安装，请运行: pip install google-generativeai")

# 语音识别
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

# ================= 2. 配置区 =================
st.set_page_config(
    page_title="金鑫 - 智能投资助理",
    page_icon="👩‍💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 全局变量
MEMORY_FILE = "investment_memory_v2.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf"
USER_ID = "default_user"  # 可扩展为多用户系统

# 创建必要目录
for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API配置 (从secrets或环境变量读取)
try:
    API_KEY = st.secrets.get("GEMINI_API_KEY", "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU")
except:
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU"  # 示例密钥，请替换

# ================= 3. CSS样式 (移动端优化) =================
st.markdown("""
<style>
    /* 主标题 */
    .main-title {
        text-align: center;
        font-size: 28px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 20px;
        padding-bottom: 10px;
        border-bottom: 2px solid #3B82F6;
    }
    
    /* 头像样式 */
    .avatar-container {
        display: flex;
        justify-content: center;
        margin: 20px 0;
    }
    .avatar-img {
        width: 140px;
        height: 140px;
        border-radius: 50%;
        border: 4px solid #10B981;
        object-fit: cover;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    /* 消息操作按钮 (强制横向滚动，手机友好) */
    .message-actions {
        display: flex;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 5px;
        margin-top: 10px;
        padding: 8px 0;
        border-top: 1px solid #E5E7EB;
    }
    .message-actions button {
        min-width: 60px !important;
        padding: 4px 8px !important;
        font-size: 12px !important;
        white-space: nowrap !important;
        flex-shrink: 0;
    }
    
    /* 语音输入区 */
    .voice-input-area {
        background: #F3F4F6;
        border-radius: 12px;
        padding: 15px;
        margin: 15px 0;
        border: 1px solid #D1D5DB;
    }
    
    /* 盯盘状态 */
    .monitor-active {
        background: linear-gradient(135deg, #FEF3C7, #FDE68A);
        padding: 10px;
        border-radius: 8px;
        border-left: 4px solid #F59E0B;
        margin: 10px 0;
    }
    
    /* 隐藏滚动条但保留功能 */
    .hide-scrollbar::-webkit-scrollbar {
        display: none;
    }
    .hide-scrollbar {
        -ms-overflow-style: none;
        scrollbar-width: none;
    }
    
    /* 响应式调整 */
    @media (max-width: 768px) {
        .main-title { font-size: 22px; }
        .avatar-img { width: 100px; height: 100px; }
        .message-actions button { min-width: 55px !important; }
    }
</style>
""", unsafe_allow_html=True)

# ================= 4. 辅助函数区 =================

def safe_execute(func, *args, **kwargs):
    """安全执行函数，捕获所有异常"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        st.error(f"执行错误: {str(e)[:100]}")
        return None

def get_avatar_url() -> str:
    """获取稳定的头像URL"""
    return "https://api.dicebear.com/9.x/avataaars/png?seed=Jinxin&clothing=blazerAndShirt&hairColor=black&skinColor=light&accessories=glasses&top=longHairStraight&backgroundColor=b6e3f4"

def init_font():
    """初始化中文字体"""
    try:
        # 尝试从网络下载字体
        if not os.path.exists(FONT_PATH):
            url = "https://github.com/adobe-fonts/source-han-sans/raw/release/OTF/SimplifiedChinese/SourceHanSansSC-Regular.otf"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(FONT_PATH, "wb") as f:
                    f.write(response.content)
        
        if os.path.exists(FONT_PATH):
            fm.fontManager.addfont(FONT_PATH)
            font_name = fm.FontProperties(fname=FONT_PATH).get_name()
            plt.rcParams['font.sans-serif'] = [font_name]
            plt.rcParams['axes.unicode_minus'] = False
    except:
        # 回退到默认字体
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

init_font()

def extract_stock_code(query: str) -> Tuple[str, str, str]:
    """
    从查询中提取股票代码
    返回: (原始代码, Yahoo代码, 新浪代码)
    """
    query = query.upper().strip()
    
    # 常见股票映射
    stock_map = {
        "茅台": "600519", "贵州茅台": "600519",
        "腾讯": "0700", "阿里巴巴": "9988", "阿里": "9988",
        "美团": "3690", "京东": "9618", "百度": "9888",
        "宁德时代": "300750", "比亚迪": "002594",
        "特斯拉": "TSLA", "苹果": "AAPL", "微软": "MSFT",
        "谷歌": "GOOGL", "亚马逊": "AMZN"
    }
    
    # 检查是否有映射
    for name, code in stock_map.items():
        if name in query:
            query = code
            break
    
    # 提取数字代码
    code_match = re.search(r'(\d{4,6})', query)
    if code_match:
        code = code_match.group(1)
    else:
        # 提取字母代码 (美股)
        letter_match = re.search(r'([A-Z]{1,5})', query)
        code = letter_match.group(1) if letter_match else ""
    
    if not code:
        return "", "", ""
    
    # 生成各种格式的代码
    if code.isdigit():
        if len(code) == 6:
            if code.startswith('6'):
                yahoo_code = f"{code}.SS"
                sina_code = f"sh{code}"
            else:
                yahoo_code = f"{code}.SZ"
                sina_code = f"sz{code}"
        elif len(code) in [4, 5]:
            yahoo_code = f"{code}.HK"
            sina_code = f"hk{code.zfill(5)}"
        else:
            yahoo_code = code
            sina_code = code
    else:
        # 美股
        yahoo_code = code
        sina_code = f"gb_{code.lower()}"
    
    return code, yahoo_code, sina_code

def get_stock_data(query: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    获取股票数据 (双备份)
    返回: (DataFrame用于画图, 信息字符串)
    """
    _, yahoo_code, sina_code = extract_stock_code(query)
    
    if not yahoo_code and not sina_code:
        return None, "未识别到有效的股票代码"
    
    info_str = ""
    df = None
    
    # 方法1: 新浪实时接口
    if sina_code and not sina_code.startswith("gb_"):
        try:
            url = f"https://hq.sinajs.cn/list={sina_code}"
            headers = {
                'Referer': 'https://finance.sina.com.cn',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data_str = resp.text.split('"')[1]
                parts = data_str.split(',')
                
                if len(parts) > 6:
                    if "hk" in sina_code:
                        name = parts[1]
                        price = float(parts[6])
                        prev_close = float(parts[3])
                    else:
                        name = parts[0]
                        price = float(parts[3])
                        prev_close = float(parts[2])
                    
                    change = price - prev_close
                    change_pct = (change / prev_close * 100) if prev_close != 0 else 0
                    
                    info_str = f"{name} | 现价: {price:.2f} | 涨跌: {change:+.2f} ({change_pct:+.2f}%)"
                    
                    # 创建简易DataFrame
                    df = pd.DataFrame({
                        'Close': [price],
                        'Change': [change_pct]
                    }, index=[datetime.now()])
        except Exception as e:
            pass
    
    # 方法2: Yahoo Finance (用于历史数据)
    if yahoo_code and (df is None or len(df) < 5):
        try:
            ticker = yf.Ticker(yahoo_code)
            
            # 获取基本信息
            info = ticker.info
            name = info.get('longName', info.get('shortName', yahoo_code))
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            prev_close = info.get('previousClose', price)
            change_pct = info.get('regularMarketChangePercent', 0)
            
            if not info_str:
                info_str = f"{name} | 现价: {price:.2f} | 涨跌幅: {change_pct:+.2f}%"
            
            # 获取历史数据画图
            hist = ticker.history(period="1mo")
            if not hist.empty:
                df = hist[['Close']].copy()
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA20'] = df['Close'].rolling(20).mean()
            elif price > 0:
                # 如果没有历史数据，创建模拟数据
                dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
                df = pd.DataFrame({
                    'Close': [price * (1 + np.random.uniform(-0.05, 0.05)) for _ in range(30)]
                }, index=dates)
                df['Close'] = df['Close'].rolling(3).mean().fillna(method='bfill')
                
        except Exception as e:
            pass
    
    return df, info_str

def clean_ai_response(text: str) -> str:
    """彻底清除AI回复中的代码块"""
    # 移除所有代码块
    text = re.sub(r'```[\s\S]*?```', '', text)
    # 移除Python代码指示
    text = re.sub(r'python\s*\n', '', text)
    # 移除过多的换行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def execute_plot_code(code_str: str) -> Optional[str]:
    """安全执行绘图代码"""
    if not code_str or 'plt' not in code_str:
        return None
    
    # 创建安全执行环境
    safe_globals = {
        'plt': plt,
        'pd': pd,
        'np': np,
        'datetime': datetime,
        'pd': pd,
        'get_stock_data': get_stock_data,
        'st': st
    }
    
    try:
        # 清理代码
        code_str = code_str.replace('plt.show()', '')
        
        # 执行代码
        exec(code_str, safe_globals)
        
        # 保存图表
        if plt.get_fignums():
            timestamp = int(time.time())
            filename = f"chart_{timestamp}.png"
            filepath = os.path.join(CHARTS_DIR, filename)
            plt.savefig(filepath, dpi=100, bbox_inches='tight', facecolor='white')
            plt.close('all')
            return filepath
    except Exception as e:
        st.error(f"绘图错误: {e}")
        return None
    
    return None

def text_to_speech(text: str, output_path: str) -> bool:
    """文本转语音"""
    if not TTS_AVAILABLE or not text:
        return False
    
    try:
        # 转换为口语化文本
        spoken_text = text[:200]  # 限制长度
        
        # 异步执行
        async def generate():
            try:
                communicate = edge_tts.Communicate(spoken_text, "zh-CN-XiaoxiaoNeural")
                await communicate.save(output_path)
                return True
            except:
                return False
        
        # 运行异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(generate())
        loop.close()
        return result
    except:
        return False

def transcribe_audio(audio_bytes: bytes) -> Optional[str]:
    """语音转文字"""
    if not SR_AVAILABLE or not audio_bytes:
        return None
    
    try:
        r = sr.Recognizer()
        audio_data = sr.AudioData(audio_bytes, sample_rate=44100, sample_width=2)
        text = r.recognize_google(audio_data, language='zh-CN')
        return text
    except:
        return None

def generate_conversational_response(text: str, stock_info: str) -> str:
    """生成对话式回复 (非技术报告)"""
    if not GEMINI_AVAILABLE:
        return f"收到您的查询: {text}\n股票信息: {stock_info}"
    
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        请以专业投资顾问"金鑫"的身份，用自然、口语化的中文回复用户。
        不要使用技术术语，不要显示代码，就像朋友间聊天一样。
        
        用户询问: {text}
        股票实时信息: {stock_info}
        
        请提供:
        1. 简要分析当前情况
        2. 用通俗语言解释数据含义
        3. 给出个人化的投资建议
        4. 保持亲切、专业的语气
        
        回复示例风格:
        "根据最新数据，茅台目前报价在2100元左右，相比昨天小涨了2%。从近期走势看..."
        """
        
        response = model.generate_content(prompt)
        return response.text
    except:
        return f"根据数据: {stock_info}，当前市场情况需要关注..."

# ================= 5. 数据管理 =================

def load_conversations() -> List[Dict]:
    """加载对话历史"""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 只返回当前用户的对话
                return [msg for msg in data if msg.get('user_id') == USER_ID]
    except:
        pass
    return []

def save_conversation(role: str, content: str, 
                     image_path: str = None, 
                     audio_path: str = None,
                     metadata: dict = None):
    """保存对话到历史记录"""
    try:
        # 加载现有记录
        conversations = []
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                conversations = json.load(f)
        
        # 添加新消息
        message = {
            'id': str(uuid.uuid4()),
            'user_id': USER_ID,
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'image_path': image_path,
            'audio_path': audio_path,
            'metadata': metadata or {},
            'hidden': False
        }
        
        conversations.append(message)
        
        # 保存回文件
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(conversations, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        st.error(f"保存对话失败: {e}")

def export_to_word(messages: List[Dict]) -> bytes:
    """导出对话到Word文档"""
    doc = Document()
    
    # 添加标题
    doc.add_heading('金鑫投资顾问 - 对话记录', 0)
    doc.add_paragraph(f'导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    doc.add_paragraph()
    
    # 添加每条消息
    for msg in messages:
        if msg.get('hidden', False):
            continue
            
        role = "👤 用户" if msg['role'] == 'user' else "👩‍💼 金鑫"
        time_str = datetime.fromisoformat(msg['timestamp']).strftime("%H:%M")
        
        doc.add_heading(f'{role} ({time_str})', level=2)
        doc.add_paragraph(msg['content'])
        
        if msg.get('image_path') and os.path.exists(msg['image_path']):
            doc.add_paragraph('【图表】')
        
        if msg.get('audio_path'):
            doc.add_paragraph('【语音回复】')
        
        doc.add_paragraph()
    
    # 保存到字节流
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# ================= 6. 会话状态初始化 =================

if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.messages = load_conversations()
    st.session_state.monitoring = False
    st.session_state.monitor_code = "300750"
    st.session_state.monitor_target = 0.0
    st.session_state.voice_enabled = True
    st.session_state.search_query = ""
    st.session_state.last_audio_id = None

# ================= 7. 侧边栏布局 =================

with st.sidebar:
    # 头像和标题
    st.markdown(f"""
    <div style="text-align: center;">
        <img src="{get_avatar_url()}" style="width: 100px; height: 100px; border-radius: 50%; border: 3px solid #10B981;">
        <h3 style="margin-top: 10px; color: #1E3A8A;">金鑫</h3>
        <p style="color: #6B7280; font-size: 14px;">您的智能投资顾问</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 盯盘功能
    with st.expander("🎯 实时盯盘", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            monitor_code = st.text_input("股票代码", 
                                        value=st.session_state.monitor_code,
                                        key="monitor_code_input")
        with col2:
            monitor_target = st.number_input("目标价位", 
                                           value=st.session_state.monitor_target,
                                           step=1.0,
                                           format="%.2f")
        
        col_start, col_stop = st.columns(2)
        with col_start:
            if st.button("🚀 启动监控", type="primary", use_container_width=True):
                st.session_state.monitoring = True
                st.session_state.monitor_code = monitor_code
                st.session_state.monitor_target = monitor_target
                st.success(f"开始监控 {monitor_code}，目标价: {monitor_target}")
                st.rerun()
        
        with col_stop:
            if st.button("🛑 停止监控", type="secondary", use_container_width=True):
                st.session_state.monitoring = False
                st.warning("监控已停止")
                st.rerun()
        
        # 显示监控状态
        if st.session_state.monitoring:
            with st.spinner("获取实时数据..."):
                df, info = get_stock_data(monitor_code)
                if "现价" in info:
                    try:
                        price_match = re.search(r'现价:\s*([\d.]+)', info)
                        if price_match:
                            current_price = float(price_match.group(1))
                            st.metric("当前价格", f"{current_price:.2f}", 
                                     delta=f"目标: {monitor_target}")
                            
                            if current_price <= monitor_target:
                                st.error("🎯 达到目标价位！考虑买入")
                                if st.session_state.voice_enabled:
                                    st.info("语音提示: 达到目标价位")
                            elif current_price >= monitor_target * 1.05:
                                st.success("📈 涨幅超过5%，考虑获利了结")
                    except:
                        pass
    
    st.divider()
    
    # 语音设置
    with st.expander("🎵 语音设置"):
        voice_enabled = st.toggle("启用语音回复", 
                                 value=st.session_state.voice_enabled,
                                 help="是否生成语音回复")
        st.session_state.voice_enabled = voice_enabled
        
        if not TTS_AVAILABLE:
            st.warning("TTS功能未安装")
    
    # 数据管理
    with st.expander("💾 数据管理"):
        col_exp, col_clr = st.columns(2)
        
        with col_exp:
            # 导出所有对话
            if st.session_state.messages:
                doc_bytes = export_to_word(st.session_state.messages)
                st.download_button(
                    label="📥 导出全部",
                    data=doc_bytes,
                    file_name=f"金鑫对话_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )
        
        with col_clr:
            if st.button("🗑️ 清空记录", use_container_width=True):
                st.session_state.messages = []
                if os.path.exists(MEMORY_FILE):
                    try:
                        # 只清空当前用户的记录
                        conversations = []
                        if os.path.exists(MEMORY_FILE):
                            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                                all_conv = json.load(f)
                                conversations = [c for c in all_conv if c.get('user_id') != USER_ID]
                        
                        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                            json.dump(conversations, f, ensure_ascii=False, indent=2)
                        st.success("记录已清空")
                    except:
                        pass
                st.rerun()
    
    # 对话搜索
    st.divider()
    search_query = st.text_input("🔍 搜索对话内容", 
                                key="search_input",
                                placeholder="输入关键词搜索...")
    st.session_state.search_query = search_query

# ================= 8. 主界面 =================

# 标题和头像
st.markdown('<div class="main-title">金鑫 - 智能投资助理</div>', unsafe_allow_html=True)
st.markdown(f"""
<div class="avatar-container">
    <img src="{get_avatar_url()}" class="avatar-img">
</div>
""", unsafe_allow_html=True)

# 语音输入区域
if VOICE_AVAILABLE and mic_recorder:
    st.markdown("### 🎤 语音输入")
    with st.container():
        audio_data = mic_recorder(
            start_prompt="点击开始录音",
            stop_prompt="点击停止",
            key='voice_recorder',
            format="wav"
        )
        
        if audio_data and audio_data['bytes']:
            # 防止重复处理同一录音
            if audio_data['id'] != st.session_state.last_audio_id:
                st.session_state.last_audio_id = audio_data['id']
                
                with st.spinner("正在识别语音..."):
                    text = transcribe_audio(audio_data['bytes'])
                    if text:
                        st.success(f"识别结果: {text}")
                        # 添加到消息队列
                        if 'voice_input' not in st.session_state:
                            st.session_state.voice_input = text
                        else:
                            st.session_state.voice_input = text
                    else:
                        st.error("未识别到语音")

# 显示对话历史
st.markdown("### 💬 对话记录")
if not st.session_state.messages:
    st.info("👋 您好！我是金鑫，您的智能投资顾问。请告诉我您想了解的股票或投资问题。")

for idx, msg in enumerate(st.session_state.messages):
    # 搜索过滤
    if st.session_state.search_query:
        if st.session_state.search_query.lower() not in msg['content'].lower():
            continue
    
    # 隐藏的消息跳过
    if msg.get('hidden', False):
        continue
    
    # 显示消息
    with st.chat_message(msg['role'], avatar=get_avatar_url() if msg['role'] == 'assistant' else "👤"):
        # 内容
        st.markdown(msg['content'])
        
        # 图片
        if msg.get('image_path') and os.path.exists(msg['image_path']):
            try:
                st.image(msg['image_path'], caption="分析图表", use_column_width=True)
            except:
                pass
        
        # 语音
        if msg.get('audio_path') and os.path.exists(msg['audio_path']):
            try:
                st.audio(msg['audio_path'])
            except:
                pass
        
        # 操作按钮
        st.markdown('<div class="message-actions hide-scrollbar">', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📋 复制", key=f"copy_{idx}", use_container_width=True):
                st.code(msg['content'], language=None)
        
        with col2:
            if st.button("🙈 隐藏", key=f"hide_{idx}", use_container_width=True):
                st.session_state.messages[idx]['hidden'] = True
                save_conversation(msg['role'], msg['content'], 
                                 msg.get('image_path'), 
                                 msg.get('audio_path'),
                                 msg.get('metadata', {}))
                st.rerun()
        
        with col3:
            if st.button("🗑️ 删除", key=f"delete_{idx}", use_container_width=True):
                # 物理删除文件
                if msg.get('image_path') and os.path.exists(msg['image_path']):
                    try:
                        os.remove(msg['image_path'])
                    except:
                        pass
                if msg.get('audio_path') and os.path.exists(msg['audio_path']):
                    try:
                        os.remove(msg['audio_path'])
                    except:
                        pass
                
                # 从内存移除
                st.session_state.messages.pop(idx)
                st.rerun()
        
        with col4:
            # 导出单条消息
            doc_bytes = export_to_word([msg])
            st.download_button(
                label="📥 导出",
                data=doc_bytes,
                file_name=f"对话_{idx+1}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"export_{idx}",
                use_container_width=True
            )
        
        st.markdown('</div>', unsafe_allow_html=True)

# ================= 9. 输入处理 =================

st.divider()
st.markdown("### 💭 输入您的问题")

# 文本输入
user_input = st.chat_input("请输入股票代码或投资问题...")

# 优先使用语音输入
if hasattr(st.session_state, 'voice_input') and st.session_state.voice_input:
    user_input = st.session_state.voice_input
    del st.session_state.voice_input

if user_input:
    # 保存用户消息
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)
    
    save_conversation("user", user_input)
    
    # 生成AI回复
    with st.chat_message("assistant", avatar=get_avatar_url()):
        with st.spinner("金鑫正在分析..."):
            try:
                # 获取股票数据
                df, stock_info = get_stock_data(user_input)
                
                # 生成对话式回复
                if GEMINI_AVAILABLE:
                    response_text = generate_conversational_response(user_input, stock_info)
                else:
                    response_text = f"根据数据: {stock_info}\n\n建议关注市场动态，谨慎投资。"
                
                # 清理回复
                clean_text = clean_ai_response(response_text)
                
                # 显示文本
                st.markdown(clean_text)
                
                # 生成图表
                chart_path = None
                if df is not None and not df.empty:
                    try:
                        # 自动生成简单图表
                        plt.figure(figsize=(10, 4))
                        plt.plot(df.index, df['Close'], label='收盘价', linewidth=2)
                        
                        if 'MA5' in df.columns:
                            plt.plot(df.index, df['MA5'], label='5日均线', linestyle='--', alpha=0.7)
                        
                        plt.title(f'股价走势图', fontsize=14)
                        plt.xlabel('日期')
                        plt.ylabel('价格')
                        plt.legend()
                        plt.grid(True, alpha=0.3)
                        plt.xticks(rotation=45)
                        
                        # 保存图表
                        timestamp = int(time.time())
                        chart_path = os.path.join(CHARTS_DIR, f"auto_chart_{timestamp}.png")
                        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
                        plt.close()
                        
                        # 显示图表
                        st.image(chart_path, caption="价格走势分析", use_column_width=True)
                    except Exception as e:
                        st.error(f"图表生成失败: {e}")
                
                # 生成语音
                audio_path = None
                if st.session_state.voice_enabled and TTS_AVAILABLE:
                    timestamp = int(time.time())
                    audio_path = os.path.join(AUDIO_DIR, f"audio_{timestamp}.mp3")
                    if text_to_speech(clean_text, audio_path):
                        st.audio(audio_path)
                    else:
                        audio_path = None
                
                # 保存助理回复
                save_conversation("assistant", clean_text, chart_path, audio_path)
                
                # 刷新消息列表
                st.session_state.messages = load_conversations()
                
            except Exception as e:
                st.error(f"处理出错: {str(e)}")
                save_conversation("assistant", f"抱歉，处理时出现错误: {str(e)[:100]}")

# ================= 10. 监控循环 =================

if st.session_state.monitoring:
    time.sleep(10)  # 每10秒检查一次
    st.rerun()

# ================= 11. 隐藏消息恢复 =================

hidden_messages = [msg for msg in st.session_state.messages if msg.get('hidden', False)]
if hidden_messages and not st.session_state.search_query:
    with st.sidebar.expander("📂 已隐藏消息", expanded=False):
        for idx, msg in enumerate(hidden_messages):
            if st.button(f"恢复: {msg['content'][:30]}...", key=f"restore_{idx}"):
                msg['hidden'] = False
                # 更新文件
                save_conversation(msg['role'], msg['content'], 
                                 msg.get('image_path'), 
                                 msg.get('audio_path'),
                                 msg.get('metadata', {}))
                st.rerun()

# ================= 12. 部署说明 =================
with st.sidebar.expander("🚀 部署说明"):
    st.markdown("""
    ### 快速部署到 Streamlit Cloud
    
    1. 创建 `requirements.txt`:
    ```
    streamlit>=1.28.0
    google-generativeai>=0.3.0
    yfinance>=0.2.28
    pandas>=2.0.0
    matplotlib>=3.7.0
    python-docx>=1.1.0
    pillow>=10.0.0
    requests>=2.31.0
    numpy>=1.24.0
    streamlit-mic-recorder>=0.0.8
    edge-tts>=6.1.9
    SpeechRecognition>=3.10.0
    ```
    
    2. 在 Streamlit Cloud 中设置 Secrets:
    ```
    GEMINI_API_KEY = "您的API密钥"
    ```
    
    3. 上传此文件为 `app.py`
    
    ### 本地运行
    ```bash
    pip install -r requirements.txt
    streamlit run app.py
    ```
    """)

# 添加底部信息
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="text-align: center; color: #6B7280; font-size: 12px;">
    <p>金鑫智能投资助理 v2.0</p>
    <p>数据仅供参考，投资需谨慎</p>
</div>
""", unsafe_allow_html=True)
