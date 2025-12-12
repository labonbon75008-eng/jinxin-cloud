"""
金鑫 - 智能投资助理 (稳定修复版)
修复：
1. 使用本地头像文件
2. 修复Gemini模型错误
3. 优化语音识别性能
4. 防止错误重复出现
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

# 安全导入语音组件
try:
    from streamlit_mic_recorder import mic_recorder
    VOICE_AVAILABLE = True
except:
    mic_recorder = None
    VOICE_AVAILABLE = False
    st.warning("语音组件未安装: pip install streamlit-mic-recorder")

try:
    import edge_tts
    TTS_AVAILABLE = True
except:
    TTS_AVAILABLE = False
    st.warning("TTS未安装: pip install edge-tts")

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
    st.error("Gemini未安装: pip install google-generativeai")

# ================= 2. 配置区 =================
st.set_page_config(
    page_title="金鑫 - 智能投资助理",
    page_icon="👩‍💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 全局配置
MEMORY_FILE = "investment_memory.json"
CHARTS_DIR = "charts"
AUDIO_DIR = "audio_cache"

# 创建目录
for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# API密钥
try:
    API_KEY = st.secrets.get("GEMINI_API_KEY", "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU")
except:
    API_KEY = "AIzaSyAaN5lJUzp7MXQuLyi8NMV5V26aizR8kBU"

# Gemini模型配置 - 使用稳定版本
GEMINI_MODEL = "gemini-1.5-flash"  # 或 "gemini-1.5-pro"

# ================= 3. 本地头像处理 =================

def get_avatar_base64(image_path: str) -> str:
    """将本地图片转换为base64"""
    try:
        if os.path.exists(image_path):
            with open(image_path, "rb") as img_file:
                encoded = base64.b64encode(img_file.read()).decode()
                return f"data:image/png;base64,{encoded}"
    except:
        pass
    
    # 如果本地文件不存在，使用简单的默认头像
    default_avatar = """
    <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <circle cx="50" cy="50" r="45" fill="#4F46E5"/>
        <circle cx="50" cy="40" r="15" fill="#FBBF24"/>
        <circle cx="40" cy="35" r="3" fill="#FFFFFF"/>
        <circle cx="60" cy="35" r="3" fill="#FFFFFF"/>
        <path d="M 40 55 Q 50 65 60 55" stroke="#FFFFFF" stroke-width="2" fill="none"/>
    </svg>
    """
    return f"data:image/svg+xml;base64,{base64.b64encode(default_avatar.encode()).decode()}"

# 定义头像路径
ASSISTANT_AVATAR_PATH = "avatar.png"  # 金鑫头像
USER_AVATAR_PATH = "user.png"         # 用户头像

# 获取头像base64
ASSISTANT_AVATAR = get_avatar_base64(ASSISTANT_AVATAR_PATH)
USER_AVATAR = get_avatar_base64(USER_AVATAR_PATH)

# ================= 4. CSS样式 =================
st.markdown("""
<style>
    .main-title {
        text-align: center;
        font-size: 28px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 20px;
    }
    
    .avatar-small {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid #10B981;
    }
    
    .message-actions {
        display: flex;
        flex-wrap: nowrap;
        gap: 5px;
        margin-top: 10px;
        padding: 8px 0;
        border-top: 1px solid #E5E7EB;
    }
    
    .message-actions button {
        min-width: 60px;
        padding: 4px 8px;
        font-size: 12px;
    }
    
    .input-area {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: white;
        padding: 15px;
        border-top: 2px solid #E5E7EB;
        z-index: 1000;
    }
    
    .compact-chart {
        max-width: 500px;
        margin: 10px auto;
    }
    
    @media (max-width: 768px) {
        .avatar-small { width: 35px; height: 35px; }
        .main-title { font-size: 22px; }
    }
</style>
""", unsafe_allow_html=True)

# ================= 5. 数据管理 =================

def load_messages():
    """加载对话记录"""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return []

def save_messages(messages):
    """保存对话记录"""
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(messages[-50:], f, ensure_ascii=False, indent=2)  # 只保存最近50条
    except:
        pass

# ================= 6. 股票数据获取 =================

def get_stock_data_simple(query: str):
    """简化版股票数据获取"""
    query = query.upper().strip()
    
    # 股票映射
    stock_map = {
        "茅台": "600519.SS", "贵州茅台": "600519.SS",
        "腾讯": "0700.HK", "阿里巴巴": "BABA",
        "宁德时代": "300750.SZ", "比亚迪": "002594.SZ",
        "特斯拉": "TSLA", "苹果": "AAPL", "微软": "MSFT",
        "谷歌": "GOOGL", "亚马逊": "AMZN"
    }
    
    # 查找映射
    for name, code in stock_map.items():
        if name in query:
            yahoo_code = code
            break
    else:
        # 尝试提取代码
        if match := re.search(r'(\d{6})', query):
            code = match.group(1)
            if code.startswith('6'):
                yahoo_code = f"{code}.SS"
            else:
                yahoo_code = f"{code}.SZ"
        elif match := re.search(r'(\d{4,5})', query):
            yahoo_code = f"{match.group(1)}.HK"
        elif match := re.search(r'([A-Z]{1,5})', query):
            yahoo_code = match.group(1)
        else:
            return None, "未识别股票代码"
    
    # 获取数据
    try:
        ticker = yf.Ticker(yahoo_code)
        info = ticker.info
        
        name = info.get('longName', info.get('shortName', yahoo_code))
        price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        prev_close = info.get('previousClose', price)
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        
        info_str = f"{name} | 现价: {price:.2f} | 涨跌: {change:+.2f} ({change_pct:+.2f}%)"
        
        # 获取历史数据
        hist = ticker.history(period="1mo")
        if not hist.empty:
            df = hist[['Close', 'Volume']].copy()
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA10'] = df['Close'].rolling(10).mean()
            return df, info_str
        else:
            # 创建模拟数据
            dates = pd.date_range(end=datetime.now(), periods=20, freq='D')
            prices = [price * (1 + np.random.uniform(-0.02, 0.02)) for _ in range(20)]
            df = pd.DataFrame({'Close': prices}, index=dates)
            df['Close'] = df['Close'].rolling(3).mean().fillna(method='bfill')
            return df, info_str
            
    except Exception as e:
        return None, f"数据获取失败: {str(e)[:50]}"

def create_simple_chart(df, title="股价走势"):
    """创建简洁图表"""
    try:
        plt.figure(figsize=(6, 3.5))  # 更小的尺寸
        plt.plot(df.index, df['Close'], color='#4F46E5', linewidth=1.5, label='收盘价')
        
        if 'MA5' in df.columns:
            plt.plot(df.index, df['MA5'], '--', color='#10B981', alpha=0.7, linewidth=1, label='5日均线')
        
        if 'MA10' in df.columns:
            plt.plot(df.index, df['MA10'], ':', color='#F59E0B', alpha=0.7, linewidth=1, label='10日均线')
        
        plt.title(title, fontsize=12)
        plt.xlabel('日期', fontsize=9)
        plt.ylabel('价格', fontsize=9)
        plt.legend(fontsize=8, loc='upper left')
        plt.grid(True, alpha=0.3)
        plt.xticks(fontsize=8, rotation=30)
        plt.yticks(fontsize=8)
        plt.tight_layout()
        
        # 保存图表
        chart_path = os.path.join(CHARTS_DIR, f"chart_{int(time.time())}.png")
        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        return chart_path
    except Exception as e:
        st.error(f"图表生成失败: {e}")
        return None

# ================= 7. AI回复生成 =================

def get_gemini_response(user_query: str, stock_info: str = ""):
    """获取Gemini回复"""
    if not GEMINI_AVAILABLE:
        return "AI服务暂不可用，请检查Gemini配置。"
    
    try:
        genai.configure(api_key=API_KEY)
        
        # 尝试不同的模型
        models_to_try = [
            "gemini-1.5-flash",  # 快速稳定
            "gemini-1.5-pro",    # 功能更强
            "gemini-2.0-flash",  # 最新版本
        ]
        
        response_text = ""
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                
                prompt = f"""
                你是一位专业的投资顾问，名字叫"金鑫"。
                请用自然、亲切的中文回复用户，不要使用专业术语。
                
                用户问题: {user_query}
                股票信息: {stock_info}
                
                请按照以下格式回复:
                1. 问候并回应用户问题
                2. 简要分析股票数据（如果有）
                3. 给出实用建议
                4. 以鼓励的话语结束
                
                示例:
                "您好！我看到您关注茅台。根据最新数据，当前价格在2100元左右..."
                """
                
                response = model.generate_content(prompt)
                response_text = response.text
                break  # 成功则退出
                
            except Exception as e:
                if "404" in str(e):
                    continue  # 尝试下一个模型
                else:
                    raise e
        
        if not response_text:
            return f"根据数据: {stock_info}，建议您关注市场动态。投资有风险，请谨慎决策。"
        
        return response_text
        
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg:
            return f"AI模型配置有误，请检查模型名称。当前错误: {error_msg[:100]}"
        elif "429" in error_msg:
            return "API调用次数超限，请稍后重试。"
        else:
            return f"AI回复生成失败: {error_msg[:100]}"

# ================= 8. 语音功能 =================

def process_voice_input(audio_bytes):
    """处理语音输入"""
    if not SR_AVAILABLE or not audio_bytes:
        return None
    
    try:
        r = sr.Recognizer()
        audio_data = sr.AudioData(audio_bytes, 44100, 2)
        text = r.recognize_google(audio_data, language='zh-CN', show_all=False)
        return text
    except sr.UnknownValueError:
        return None
    except Exception as e:
        st.error(f"语音识别错误: {e}")
        return None

def generate_voice(text: str):
    """生成语音"""
    if not TTS_AVAILABLE or not text:
        return None
    
    try:
        # 限制文本长度
        spoken_text = text[:100]
        
        async def generate():
            try:
                timestamp = int(time.time())
                output_path = os.path.join(AUDIO_DIR, f"voice_{timestamp}.mp3")
                communicate = edge_tts.Communicate(spoken_text, "zh-CN-XiaoxiaoNeural")
                await communicate.save(output_path)
                return output_path
            except:
                return None
        
        # 同步执行异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(generate())
        loop.close()
        
        return result
    except:
        return None

# ================= 9. 会话状态初始化 =================

if 'messages' not in st.session_state:
    st.session_state.messages = load_messages()

if 'processing' not in st.session_state:
    st.session_state.processing = False

if 'voice_input' not in st.session_state:
    st.session_state.voice_input = None

if 'monitoring' not in st.session_state:
    st.session_state.monitoring = False
    st.session_state.monitor_stock = "300750"
    st.session_state.monitor_target = 0.0

# ================= 10. 侧边栏 =================

with st.sidebar:
    # 显示头像
    st.markdown(f"""
    <div style="text-align: center;">
        <img src="{ASSISTANT_AVATAR}" class="avatar-small">
        <h3 style="margin: 10px 0 5px 0; color: #1E3A8A;">金鑫</h3>
        <p style="color: #6B7280; font-size: 14px; margin-bottom: 20px;">智能投资顾问</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 盯盘功能
    with st.expander("🎯 实时盯盘", expanded=True):
        monitor_stock = st.text_input("股票代码", value=st.session_state.monitor_stock)
        monitor_target = st.number_input("目标价格", value=st.session_state.monitor_target, step=1.0)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("启动监控", type="primary", use_container_width=True):
                st.session_state.monitoring = True
                st.session_state.monitor_stock = monitor_stock
                st.session_state.monitor_target = monitor_target
                st.success(f"开始监控 {monitor_stock}")
        
        with col2:
            if st.button("停止监控", type="secondary", use_container_width=True):
                st.session_state.monitoring = False
                st.warning("监控已停止")
    
    st.divider()
    
    # 数据管理
    with st.expander("💾 数据管理"):
        if st.button("清空对话记录", use_container_width=True):
            st.session_state.messages = []
            save_messages([])
            st.success("记录已清空")
            st.rerun()
        
        if st.session_state.messages:
            # 导出功能
            def create_document():
                doc = Document()
                doc.add_heading('金鑫投资对话记录', 0)
                
                for msg in st.session_state.messages:
                    role = "用户" if msg['role'] == 'user' else "金鑫"
                    doc.add_heading(role, level=2)
                    doc.add_paragraph(msg.get('content', ''))
                    doc.add_paragraph()
                
                buffer = io.BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                return buffer
            
            doc_bytes = create_document()
            st.download_button(
                label="导出Word文档",
                data=doc_bytes,
                file_name=f"对话记录_{datetime.now().strftime('%Y%m%d')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
    
    # 搜索功能
    st.divider()
    search_query = st.text_input("🔍 搜索对话", placeholder="输入关键词...")
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"对话数: {len(st.session_state.messages)}")
    st.sidebar.caption(f"更新时间: {datetime.now().strftime('%H:%M:%S')}")

# ================= 11. 主界面 =================

st.markdown('<div class="main-title">金鑫 - 智能投资助理</div>', unsafe_allow_html=True)

# 显示对话记录
if not st.session_state.messages:
    st.info("👋 您好！我是金鑫，您的投资顾问。请输入股票代码或投资问题。")

for idx, msg in enumerate(st.session_state.messages):
    # 搜索过滤
    if search_query and search_query.lower() not in msg.get('content', '').lower():
        continue
    
    # 显示消息
    avatar = ASSISTANT_AVATAR if msg['role'] == 'assistant' else USER_AVATAR
    with st.chat_message(msg['role'], avatar=avatar):
        st.markdown(msg.get('content', ''))
        
        # 显示图表
        if msg.get('chart_path') and os.path.exists(msg['chart_path']):
            st.markdown('<div class="compact-chart">', unsafe_allow_html=True)
            st.image(msg['chart_path'], use_column_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        # 显示语音
        if msg.get('audio_path') and os.path.exists(msg['audio_path']):
            st.audio(msg['audio_path'])
        
        # 操作按钮
        if msg['role'] == 'assistant':
            st.markdown('<div class="message-actions">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("复制", key=f"copy_{idx}", use_container_width=True):
                    st.code(msg.get('content', ''))
            
            with col2:
                if st.button("隐藏", key=f"hide_{idx}", use_container_width=True):
                    st.session_state.messages.pop(idx)
                    save_messages(st.session_state.messages)
                    st.rerun()
            
            with col3:
                if st.button("删除", key=f"delete_{idx}", use_container_width=True):
                    # 删除相关文件
                    if msg.get('chart_path'):
                        try:
                            os.remove(msg['chart_path'])
                        except:
                            pass
                    if msg.get('audio_path'):
                        try:
                            os.remove(msg['audio_path'])
                        except:
                            pass
                    
                    st.session_state.messages.pop(idx)
                    save_messages(st.session_state.messages)
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)

# ================= 12. 输入区域 =================

st.markdown("---")
st.markdown("### 💬 输入您的问题")

# 语音输入（放在文字输入旁边）
if VOICE_AVAILABLE and mic_recorder:
    col_voice, col_space = st.columns([1, 5])
    with col_voice:
        st.markdown("**语音输入**")
        audio_data = mic_recorder(
            start_prompt="点击说话",
            stop_prompt="停止",
            key='voice_recorder',
            format="wav"
        )
        
        # 处理语音输入
        if audio_data and audio_data.get('bytes'):
            if not st.session_state.processing:
                st.session_state.processing = True
                with st.spinner("识别语音中..."):
                    text = process_voice_input(audio_data['bytes'])
                    if text:
                        st.session_state.voice_input = text
                        st.success(f"识别结果: {text}")

# 文字输入
user_text = st.chat_input("请输入股票代码或投资问题...", key="text_input")

# 优先使用语音输入
if st.session_state.voice_input:
    user_input = st.session_state.voice_input
    st.session_state.voice_input = None
    st.session_state.processing = False
elif user_text:
    user_input = user_text
else:
    user_input = None

# 处理用户输入
if user_input and not st.session_state.processing:
    st.session_state.processing = True
    
    # 显示用户消息
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(user_input)
    
    # 保存用户消息
    st.session_state.messages.append({
        'role': 'user',
        'content': user_input,
        'timestamp': datetime.now().isoformat()
    })
    
    # 生成AI回复
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        with st.spinner("金鑫正在分析..."):
            try:
                # 获取股票数据
                df, stock_info = get_stock_data_simple(user_input)
                
                # 生成AI回复
                ai_response = get_gemini_response(user_input, stock_info)
                st.markdown(ai_response)
                
                # 生成图表
                chart_path = None
                if df is not None and not df.empty:
                    chart_path = create_simple_chart(df, "价格走势")
                    if chart_path:
                        st.markdown('<div class="compact-chart">', unsafe_allow_html=True)
                        st.image(chart_path, use_column_width=True)
                        st.markdown('</div>', unsafe_allow_html=True)
                
                # 生成语音
                audio_path = None
                if TTS_AVAILABLE:
                    audio_path = generate_voice(ai_response)
                    if audio_path:
                        st.audio(audio_path)
                
                # 保存AI回复
                st.session_state.messages.append({
                    'role': 'assistant',
                    'content': ai_response,
                    'chart_path': chart_path,
                    'audio_path': audio_path,
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                error_msg = f"处理时出现错误: {str(e)[:100]}"
                st.error(error_msg)
                st.session_state.messages.append({
                    'role': 'assistant',
                    'content': error_msg,
                    'timestamp': datetime.now().isoformat()
                })
    
    # 保存对话记录
    save_messages(st.session_state.messages)
    st.session_state.processing = False
    st.rerun()

# ================= 13. 监控功能 =================

if st.session_state.monitoring:
    try:
        with st.sidebar:
            with st.spinner("监控中..."):
                df, info = get_stock_data_simple(st.session_state.monitor_stock)
                if "现价" in info:
                    price_match = re.search(r'现价:\s*([\d.]+)', info)
                    if price_match:
                        current_price = float(price_match.group(1))
                        
                        if current_price <= st.session_state.monitor_target:
                            st.error(f"🎯 {st.session_state.monitor_stock} 达到目标价: {current_price:.2f}")
                            # 语音提示
                            if TTS_AVAILABLE:
                                warning_audio = generate_voice(f"{st.session_state.monitor_stock}达到目标价位")
                                if warning_audio:
                                    st.audio(warning_audio)
    except:
        pass

# ================= 14. 恢复隐藏消息 =================

hidden_count = sum(1 for msg in st.session_state.messages if msg.get('hidden'))
if hidden_count > 0:
    with st.sidebar.expander(f"📂 隐藏消息 ({hidden_count})"):
        for idx, msg in enumerate(st.session_state.messages):
            if msg.get('hidden'):
                if st.button(f"显示: {msg.get('content', '')[:20]}...", key=f"show_{idx}"):
                    msg['hidden'] = False
                    st.rerun()

# ================= 15. 底部信息 =================

st.sidebar.markdown("---")
st.sidebar.markdown(
    '<div style="text-align: center; color: #6B7280; font-size: 12px;">'
    '<p>数据来源: Yahoo Finance</p>'
    '<p>投资有风险，入市需谨慎</p>'
    '</div>',
    unsafe_allow_html=True
)

# 如果processing被卡住，添加重置按钮
if st.session_state.processing:
    if st.button("重置处理状态"):
        st.session_state.processing = False
        st.rerun()
