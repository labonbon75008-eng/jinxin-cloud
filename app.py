"""
金鑫 - 智能投资助理 (增强版)
修复问题：
1. 语音按钮移至对话框旁边
2. 头像正确显示
3. 图片大小优化且显示数据
4. 多设备对话同步
"""

# ================= 1. 导入区 =================
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
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from PIL import Image
import yfinance as yf
from docx import Document
from docx.shared import Inches

# 安全导入语音组件
try:
    from streamlit_mic_recorder import mic_recorder
    VOICE_AVAILABLE = True
except:
    mic_recorder = None
    VOICE_AVAILABLE = False

try:
    import edge_tts
    TTS_AVAILABLE = True
except:
    TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except:
    SR_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except:
    GEMINI_AVAILABLE = False

# ================= 2. 配置区 =================
st.set_page_config(
    page_title="金鑫 - 智能投资助理",
    page_icon="👩‍💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 全局配置
MEMORY_FILE = "investment_memory_shared.json"  # 改为共享文件
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"
FONT_PATH = "SimHei.ttf"

# 创建目录
for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API密钥
try:
    API_KEY = st.secrets.get("GEMINI_API_KEY", "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU")
except:
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU"

# ================= 3. CSS样式 =================
st.markdown("""
<style>
    /* 主标题 */
    .main-title {
        text-align: center;
        font-size: 28px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 10px;
    }
    
    /* 头像样式 */
    .avatar-img {
        width: 50px;
        height: 50px;
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid #10B981;
    }
    
    /* 消息操作按钮 */
    .message-actions {
        display: flex;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 5px;
        margin-top: 8px;
        padding: 5px 0;
    }
    
    /* 语音输入区 */
    .voice-input-container {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 10px 0;
    }
    
    /* 图表容器 */
    .chart-container {
        max-width: 600px;
        margin: 10px auto;
    }
    
    /* 响应式调整 */
    @media (max-width: 768px) {
        .avatar-img { width: 40px; height: 40px; }
        .main-title { font-size: 22px; }
    }
    
    /* 隐藏滚动条 */
    .hide-scrollbar::-webkit-scrollbar { display: none; }
    .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
""", unsafe_allow_html=True)

# ================= 4. 头像管理 =================

def get_avatar_base64():
    """返回base64编码的默认头像（防止网络问题）"""
    # 一个简单的默认头像SVG
    avatar_svg = """
    <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <circle cx="50" cy="50" r="45" fill="#4F46E5"/>
        <circle cx="50" cy="40" r="15" fill="#FBBF24"/>
        <circle cx="40" cy="35" r="3" fill="#FFFFFF"/>
        <circle cx="60" cy="35" r="3" fill="#FFFFFF"/>
        <path d="M 40 55 Q 50 65 60 55" stroke="#FFFFFF" stroke-width="2" fill="none"/>
        <circle cx="50" cy="80" r="20" fill="#FBBF24"/>
        <rect x="35" y="60" width="30" height="40" rx="5" fill="#4F46E5"/>
    </svg>
    """
    return base64.b64encode(avatar_svg.encode()).decode()

def get_avatar_url():
    """获取头像URL（多种来源尝试）"""
    urls = [
        # DiceBear稳定URL
        "https://api.dicebear.com/7.x/avataaars/svg?seed=Jinxin&backgroundColor=b6e3f4",
        # 备用URL
        "https://avatars.dicebear.com/api/avataaars/jinxin.svg?background=%23b6e3f4",
        # 本地base64回退
        f"data:image/svg+xml;base64,{get_avatar_base64()}"
    ]
    return urls[0]  # 使用第一个

# ================= 5. 数据同步 =================

def generate_user_id():
    """生成唯一的用户ID（基于设备+时间）"""
    import hashlib
    import platform
    import socket
    
    # 获取设备信息
    device_info = f"{platform.node()}_{platform.system()}_{socket.gethostname()}"
    timestamp = datetime.now().strftime("%Y%m%d")
    
    # 生成哈希ID
    user_hash = hashlib.md5(f"{device_info}_{timestamp}".encode()).hexdigest()[:8]
    return f"user_{user_hash}"

def load_conversations():
    """加载对话历史（支持多设备同步）"""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 按时间排序，最新的在前
                data.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                return data
    except Exception as e:
        st.error(f"加载对话失败: {e}")
    return []

def save_conversation(role: str, content: str, **kwargs):
    """保存对话（自动同步到共享文件）"""
    try:
        # 加载现有对话
        conversations = load_conversations()
        
        # 创建新消息
        message = {
            'id': str(uuid.uuid4()),
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'user_agent': st.secrets.get("USER_AGENT", "default"),
            **kwargs
        }
        
        # 添加到开头（最新消息在前）
        conversations.insert(0, message)
        
        # 限制最大保存100条消息
        if len(conversations) > 100:
            conversations = conversations[:100]
        
        # 保存到文件
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(conversations, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        st.error(f"保存对话失败: {e}")
        return False

# ================= 6. 数据获取与图表 =================

def extract_stock_code(query: str):
    """提取股票代码"""
    query = query.upper().strip()
    
    # 映射表
    stock_map = {
        "茅台": "600519", "贵州茅台": "600519",
        "腾讯": "0700", "阿里巴巴": "9988",
        "宁德时代": "300750", "比亚迪": "002594",
        "特斯拉": "TSLA", "苹果": "AAPL"
    }
    
    for name, code in stock_map.items():
        if name in query:
            query = code
            break
    
    # 提取代码
    if match := re.search(r'(\d{4,6})', query):
        code = match.group(1)
        if len(code) == 6:
            if code.startswith('6'):
                return f"{code}.SS", f"sh{code}"
            else:
                return f"{code}.SZ", f"sz{code}"
        elif len(code) in [4, 5]:
            return f"{code}.HK", f"hk{code}"
    elif match := re.search(r'([A-Z]{1,5})', query):
        code = match.group(1)
        return code, f"gb_{code.lower()}"
    
    return None, None

def get_stock_data(query: str):
    """获取股票数据（增强版）"""
    yahoo_code, sina_code = extract_stock_code(query)
    
    if not yahoo_code:
        return None, "未识别到股票代码"
    
    info_str = ""
    df = None
    
    # 尝试Yahoo Finance
    try:
        ticker = yf.Ticker(yahoo_code)
        
        # 获取基本信息
        info = ticker.info
        name = info.get('longName', info.get('shortName', yahoo_code))
        current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        prev_close = info.get('previousClose', current_price)
        change = current_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        
        info_str = f"{name} | 现价: ${current_price:.2f} | 涨跌: {change:+.2f} ({change_pct:+.2f}%)"
        
        # 获取历史数据
        hist = ticker.history(period="1mo")
        if not hist.empty:
            df = hist[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            # 添加交易信号
            df['Signal'] = np.where(df['MA5'] > df['MA20'], 1, -1)
            
    except Exception as e:
        info_str = f"数据获取失败: {str(e)[:50]}"
    
    return df, info_str

def create_stock_chart(df, stock_name="股票"):
    """创建股票图表（优化版）"""
    if df is None or df.empty:
        return None
    
    try:
        plt.style.use('seaborn-v0_8')
        fig, axes = plt.subplots(2, 1, figsize=(8, 6), 
                                gridspec_kw={'height_ratios': [3, 1]})
        
        # 价格图表
        ax1 = axes[0]
        ax1.plot(df.index, df['Close'], label='收盘价', linewidth=2, color='#4F46E5')
        
        if 'MA5' in df.columns:
            ax1.plot(df.index, df['MA5'], label='5日均线', linestyle='--', alpha=0.7, color='#10B981')
        if 'MA20' in df.columns:
            ax1.plot(df.index, df['MA20'], label='20日均线', linestyle='-.', alpha=0.7, color='#F59E0B')
        
        # 添加填充区域
        if 'High' in df.columns and 'Low' in df.columns:
            ax1.fill_between(df.index, df['Low'], df['High'], alpha=0.2, color='#93C5FD')
        
        ax1.set_title(f'{stock_name} 价格走势', fontsize=14, fontweight='bold')
        ax1.set_ylabel('价格 (元)', fontsize=10)
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis='x', rotation=45)
        
        # 交易量图表
        ax2 = axes[1]
        if 'Volume' in df.columns:
            ax2.bar(df.index, df['Volume'], color=['#10B981' if df['Close'].iloc[i] >= df['Open'].iloc[i] 
                                                  else '#EF4444' for i in range(len(df))], 
                   alpha=0.6)
            ax2.set_ylabel('成交量', fontsize=10)
        
        ax2.tick_params(axis='x', rotation=45)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 保存图表
        timestamp = int(time.time())
        filename = f"chart_{timestamp}.png"
        filepath = os.path.join(CHARTS_DIR, filename)
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        plt.close()
        
        return filepath
    except Exception as e:
        st.error(f"图表生成失败: {e}")
        return None

# ================= 7. AI回复生成 =================

def generate_ai_response(user_query: str, stock_info: str = ""):
    """生成AI回复"""
    if not GEMINI_AVAILABLE:
        return "AI服务暂不可用，请稍后重试。"
    
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        角色：你是一位名叫"金鑫"的专业投资顾问，女性，有10年投资经验。
        风格：语气亲切自然，像朋友聊天一样，不要用专业术语。
        
        用户问题：{user_query}
        股票信息：{stock_info}
        
        请用以下格式回复：
        1. 首先回应用户的关切
        2. 简要分析数据（如果有时）
        3. 给出实用的建议
        4. 最后用鼓励的话语结束
        
        示例回复：
        "我看到您关注茅台。根据最新数据，目前价格在2100元左右，比昨天涨了2%左右。
        从最近一个月看，走势还是比较稳健的。如果您是长期投资，可以考虑分批买入。
        投资有风险，建议您根据自身情况谨慎决策哦~"
        
        现在请回复：
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI回复生成失败: {str(e)[:50]}"

# ================= 8. 语音功能 =================

def text_to_speech_sync(text: str, output_path: str) -> bool:
    """同步文本转语音"""
    if not TTS_AVAILABLE or not text:
        return False
    
    try:
        # 限制文本长度
        spoken_text = text[:150]
        
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

def transcribe_audio(audio_bytes: bytes):
    """语音转文字"""
    if not SR_AVAILABLE:
        return None
    
    try:
        r = sr.Recognizer()
        audio_data = sr.AudioData(audio_bytes, 44100, 2)
        text = r.recognize_google(audio_data, language='zh-CN')
        return text
    except:
        return None

# ================= 9. 初始化会话状态 =================

if 'messages' not in st.session_state:
    st.session_state.messages = load_conversations()

if 'monitoring' not in st.session_state:
    st.session_state.monitoring = False
    st.session_state.monitor_code = "300750"
    st.session_state.monitor_target = 0.0

if 'voice_enabled' not in st.session_state:
    st.session_state.voice_enabled = True

# ================= 10. 侧边栏 =================

with st.sidebar:
    # 头像和标题
    st.markdown(f"""
    <div style="text-align: center;">
        <img src="{get_avatar_url()}" style="width: 80px; height: 80px; border-radius: 50%;">
        <h3 style="margin-top: 10px; color: #1E3A8A;">金鑫</h3>
        <p style="color: #6B7280; font-size: 14px;">智能投资顾问</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 盯盘功能
    with st.expander("🎯 实时盯盘", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            monitor_code = st.text_input("股票代码", value=st.session_state.monitor_code)
        with col2:
            monitor_target = st.number_input("目标价", value=st.session_state.monitor_target, step=1.0)
        
        if st.button("🚀 启动监控", type="primary", use_container_width=True):
            st.session_state.monitoring = True
            st.session_state.monitor_code = monitor_code
            st.session_state.monitor_target = monitor_target
            st.success(f"监控启动: {monitor_code}")
            st.rerun()
        
        if st.button("🛑 停止监控", type="secondary", use_container_width=True):
            st.session_state.monitoring = False
            st.warning("监控已停止")
            st.rerun()
        
        if st.session_state.monitoring:
            df, info = get_stock_data(monitor_code)
            if "现价" in info:
                try:
                    price_match = re.search(r'现价:\s*([\d.]+)', info)
                    if price_match:
                        current_price = float(price_match.group(1))
                        st.metric("当前价格", f"{current_price:.2f}")
                        
                        if current_price <= monitor_target:
                            st.error("🎯 触发买入信号！")
                            # 语音提示
                            if st.session_state.voice_enabled:
                                st.audio("https://assets.mixkit.co/sfx/preview/mixkit-correct-answer-tone-2870.mp3")
                except:
                    pass
    
    st.divider()
    
    # 语音设置
    with st.expander("🎵 语音设置"):
        st.session_state.voice_enabled = st.toggle("启用语音回复", value=True)
        if not TTS_AVAILABLE:
            st.warning("语音功能需安装: pip install edge-tts")
    
    # 数据管理
    with st.expander("💾 数据管理"):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 同步对话", use_container_width=True):
                st.session_state.messages = load_conversations()
                st.success("已同步最新对话")
                st.rerun()
        
        with col2:
            if st.button("🗑️ 清空本地", use_container_width=True):
                st.session_state.messages = []
                st.success("本地对话已清空")
                st.rerun()
        
        # 导出功能
        if st.session_state.messages:
            def create_word_doc():
                doc = Document()
                doc.add_heading('金鑫投资对话记录', 0)
                
                for msg in st.session_state.messages:
                    role = "用户" if msg['role'] == 'user' else "金鑫"
                    time_str = datetime.fromisoformat(msg['timestamp']).strftime("%Y-%m-%d %H:%M")
                    doc.add_heading(f'{role} ({time_str})', level=2)
                    doc.add_paragraph(msg['content'])
                    doc.add_paragraph()
                
                buffer = io.BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                return buffer
            
            doc_bytes = create_word_doc()
            st.download_button(
                label="📥 导出Word",
                data=doc_bytes,
                file_name=f"金鑫对话_{datetime.now().strftime('%Y%m%d')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
    
    # 对话搜索
    st.divider()
    search_query = st.text_input("🔍 搜索对话", placeholder="输入关键词...")
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"对话数: {len(st.session_state.messages)}")
    st.sidebar.caption(f"同步时间: {datetime.now().strftime('%H:%M')}")

# ================= 11. 主界面 =================

# 标题
st.markdown('<div class="main-title">金鑫 - 智能投资助理</div>', unsafe_allow_html=True)

# 显示对话历史
if not st.session_state.messages:
    st.info("👋 您好！我是金鑫，您的投资顾问。请告诉我您想了解的股票或投资问题。")

for msg in st.session_state.messages:
    # 搜索过滤
    if search_query and search_query.lower() not in msg['content'].lower():
        continue
    
    # 使用正确的头像
    avatar_url = get_avatar_url() if msg['role'] == 'assistant' else "👤"
    
    with st.chat_message(msg['role'], avatar=avatar_url):
        # 显示内容
        st.markdown(msg['content'])
        
        # 显示图片
        if msg.get('chart_path') and os.path.exists(msg['chart_path']):
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.image(msg['chart_path'], use_column_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        # 显示语音
        if msg.get('audio_path') and os.path.exists(msg['audio_path']):
            st.audio(msg['audio_path'])
        
        # 操作按钮
        st.markdown('<div class="message-actions hide-scrollbar">', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📋", key=f"copy_{msg['id']}", help="复制"):
                st.code(msg['content'])
        
        with col2:
            if st.button("🙈", key=f"hide_{msg['id']}", help="隐藏"):
                msg['hidden'] = True
                st.rerun()
        
        with col3:
            if st.button("🗑️", key=f"delete_{msg['id']}", help="删除"):
                st.session_state.messages.remove(msg)
                save_conversation("system", "消息已删除")
                st.rerun()
        
        with col4:
            # 导出单条
            doc = Document()
            doc.add_heading('对话记录', 0)
            doc.add_paragraph(f"时间: {msg.get('timestamp', '')}")
            doc.add_paragraph(f"角色: {msg['role']}")
            doc.add_paragraph(msg['content'])
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            st.download_button(
                label="📥",
                data=buffer,
                file_name=f"对话_{msg['id'][:8]}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"export_{msg['id']}",
                help="导出"
            )
        
        st.markdown('</div>', unsafe_allow_html=True)

# ================= 12. 输入区域 (语音+文字) =================

st.markdown("---")

# 创建输入容器
input_container = st.container()

with input_container:
    # 第一行：语音输入
    if VOICE_AVAILABLE and mic_recorder:
        st.markdown("### 🎤 语音输入")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            audio_data = mic_recorder(
                start_prompt="点击说话",
                stop_prompt="停止",
                key='voice_input',
                format="wav"
            )
            
            if audio_data and audio_data.get('bytes'):
                with st.spinner("识别中..."):
                    text = transcribe_audio(audio_data['bytes'])
                    if text:
                        st.success(f"识别结果: {text}")
                        # 直接处理语音输入
                        user_input = text
    
    # 第二行：文字输入 + 发送按钮
    st.markdown("### 💬 文字输入")
    
    # 使用表单包装输入区域
    with st.form(key="chat_form", clear_on_submit=True):
        col_text, col_send = st.columns([4, 1])
        
        with col_text:
            text_input = st.text_area(
                "输入您的问题",
                placeholder="例如：茅台现在价格多少？宁德时代走势如何？",
                height=80,
                key="text_input"
            )
        
        with col_send:
            st.markdown("<br>", unsafe_allow_html=True)
            submit_button = st.form_submit_button(
                "🚀 发送",
                type="primary",
                use_container_width=True
            )
        
        if submit_button and text_input.strip():
            user_input = text_input.strip()

# 处理用户输入
if 'user_input' in locals() and user_input:
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
                
                # 生成AI回复
                ai_response = generate_ai_response(user_input, stock_info)
                st.markdown(ai_response)
                
                # 生成图表
                chart_path = None
                if df is not None and not df.empty:
                    chart_path = create_stock_chart(df, stock_info.split("|")[0] if "|" in stock_info else "股票")
                    if chart_path:
                        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                        st.image(chart_path, use_column_width=True)
                        st.markdown('</div>', unsafe_allow_html=True)
                
                # 生成语音
                audio_path = None
                if st.session_state.voice_enabled and TTS_AVAILABLE:
                    timestamp = int(time.time())
                    audio_path = os.path.join(AUDIO_DIR, f"audio_{timestamp}.mp3")
                    if text_to_speech_sync(ai_response[:100], audio_path):
                        st.audio(audio_path)
                
                # 保存回复
                save_conversation("assistant", ai_response, 
                                chart_path=chart_path, 
                                audio_path=audio_path,
                                stock_info=stock_info)
                
                # 刷新消息列表
                st.session_state.messages = load_conversations()
                st.rerun()
                
            except Exception as e:
                error_msg = f"抱歉，处理时出现错误: {str(e)[:50]}"
                st.error(error_msg)
                save_conversation("assistant", error_msg)

# ================= 13. 监控循环 =================

if st.session_state.monitoring:
    time.sleep(10)
    st.rerun()

# ================= 14. 隐藏消息恢复 =================

hidden_messages = [m for m in st.session_state.messages if m.get('hidden')]
if hidden_messages:
    with st.sidebar.expander("📂 已隐藏消息"):
        for msg in hidden_messages:
            if st.button(f"恢复: {msg['content'][:20]}...", key=f"restore_{msg['id']}"):
                msg['hidden'] = False
                st.rerun()

# ================= 15. 部署说明 =================

with st.sidebar.expander("🚀 部署说明", expanded=False):
    st.markdown("""
    ### 多设备同步说明
    
    1. **共享文件同步**：
       - 所有设备访问同一个JSON文件
       - 自动加载最新对话
    
    2. **手动同步**：
       - 点击侧边栏"🔄 同步对话"按钮
       - 系统会自动从共享文件加载
    
    3. **注意事项**：
       - 确保所有设备都能访问共享文件
       - 网络延迟可能导致同步延迟
    
    ### 安装依赖
    ```bash
    pip install streamlit google-generativeai yfinance pandas matplotlib
    pip install python-docx pillow requests numpy
    pip install streamlit-mic-recorder edge-tts SpeechRecognition
    ```
    """)

# 底部信息
st.sidebar.markdown("---")
st.sidebar.markdown(
    '<div style="text-align: center; color: #6B7280; font-size: 12px;">'
    '<p>© 2025 金鑫智能投资助理</p>'
    '<p>数据仅供参考，投资需谨慎</p>'
    '</div>',
    unsafe_allow_html=True
)
