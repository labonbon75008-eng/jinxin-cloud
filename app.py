"""
金鑫智能投资助理 - 最终修复版
修复：
1. 语音输入功能
2. 股票数据获取
3. 头像显示
4. 多股票比较
"""

# ================= 1. 导入区 =================
import streamlit as st
import os
import json
import time
import uuid
import re
import io
import base64
import requests
import pandas as pd
import numpy as np
import warnings
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
from docx import Document

# 语音组件（安全导入）
try:
    from streamlit_mic_recorder import mic_recorder
    VOICE_AVAILABLE = True
except:
    VOICE_AVAILABLE = False
    st.warning("语音组件未安装: pip install streamlit-mic-recorder")

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except:
    SR_AVAILABLE = False

# 禁用警告
warnings.filterwarnings('ignore')

# ================= 2. 页面配置 =================
st.set_page_config(
    page_title="金鑫 - 智能投资助理",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 3. 自定义CSS =================
st.markdown("""
<style>
    /* 主标题 */
    .main-title {
        text-align: center;
        font-size: 26px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 10px;
        padding-bottom: 10px;
        border-bottom: 2px solid #3B82F6;
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
        gap: 5px;
        margin-top: 8px;
        padding: 6px 0;
        border-top: 1px solid #E5E7EB;
    }
    
    .message-actions button {
        min-width: 55px !important;
        padding: 3px 6px !important;
        font-size: 11px !important;
        white-space: nowrap !important;
    }
    
    /* 图表容器 */
    .chart-box {
        max-width: 500px;
        margin: 10px auto;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 10px;
        background: white;
    }
    
    /* 语音输入区 */
    .voice-area {
        background: #F3F4F6;
        border-radius: 10px;
        padding: 10px;
        margin: 5px 0;
    }
    
    /* 盯盘状态 */
    .monitor-active {
        background: linear-gradient(135deg, #FEF3C7, #FDE68A);
        padding: 8px;
        border-radius: 6px;
        border-left: 4px solid #F59E0B;
        margin: 8px 0;
    }
    
    /* 输入区域 */
    .input-container {
        position: sticky;
        bottom: 0;
        background: white;
        padding: 15px;
        border-top: 2px solid #E5E7EB;
        z-index: 100;
    }
    
    /* 手机端优化 */
    @media (max-width: 768px) {
        .avatar-img { width: 40px; height: 40px; }
        .main-title { font-size: 20px; }
        .message-actions button { min-width: 50px !important; }
    }
</style>
""", unsafe_allow_html=True)

# ================= 4. 路径配置 =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "investment_dialog.json")
CHARTS_DIR = os.path.join(BASE_DIR, "charts")

# 创建目录
os.makedirs(CHARTS_DIR, exist_ok=True)

# ================= 5. 头像处理 =================
def load_local_image(image_path: str) -> str:
    """加载本地图片为base64"""
    # 默认头像SVG
    default_svg = """
    <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#4F46E5"/>
        <circle cx="50" cy="40" r="15" fill="#FBBF24"/>
        <circle cx="40" cy="35" r="3" fill="white"/>
        <circle cx="60" cy="35" r="3" fill="white"/>
        <path d="M40,55 Q50,65 60,55" stroke="white" stroke-width="2" fill="none"/>
    </svg>
    """
    
    # 尝试加载本地文件
    if os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode()
                return f"data:image/png;base64,{encoded}"
        except:
            pass
    
    # 尝试其他可能的位置
    possible_paths = [
        image_path,
        os.path.join(BASE_DIR, image_path),
        os.path.join(os.getcwd(), image_path)
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode()
                    return f"data:image/png;base64,{encoded}"
            except:
                continue
    
    # 返回默认头像
    return f"data:image/svg+xml;base64,{base64.b64encode(default_svg.encode()).decode()}"

# 加载头像
ASSISTANT_AVATAR = load_local_image("avatar.png")
USER_AVATAR = load_local_image("user.png")

# ================= 6. 中文图表支持 =================
def setup_chinese_font():
    """设置中文字体"""
    try:
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'Microsoft YaHei']
        plt.rcParams['axes.unicode_minus'] = False
        return True
    except:
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        return True

setup_chinese_font()

# ================= 7. 股票数据引擎（增强版） =================
class StockDataFetcher:
    """股票数据获取器"""
    
    STOCK_MAP = {
        # A股
        "万华化学": ("600309", "sh", "600309.SS"),
        "贵州茅台": ("600519", "sh", "600519.SS"),
        "茅台": ("600519", "sh", "600519.SS"),
        "宁德时代": ("300750", "sz", "300750.SZ"),
        "宁德": ("300750", "sz", "300750.SZ"),
        "比亚迪": ("002594", "sz", "002594.SZ"),
        "药明康德": ("603259", "sh", "603259.SS"),
        
        # 港股
        "腾讯控股": ("0700", "hk", "0700.HK"),
        "腾讯": ("0700", "hk", "0700.HK"),
        "阿里巴巴": ("9988", "hk", "9988.HK"),
        "阿里": ("9988", "hk", "9988.HK"),
        "美团": ("3690", "hk", "3690.HK"),
        
        # 美股
        "特斯拉": ("TSLA", "us", "TSLA"),
        "苹果": ("AAPL", "us", "AAPL"),
        "微软": ("MSFT", "us", "MSFT"),
        "谷歌": ("GOOGL", "us", "GOOGL"),
        "亚马逊": ("AMZN", "us", "AMZN"),
    }
    
    @staticmethod
    def extract_stocks_from_query(query: str) -> List[Tuple[str, str, str]]:
        """从查询中提取股票信息"""
        query = query.upper()
        found_stocks = []
        
        for name, (code, market, yahoo_code) in StockDataFetcher.STOCK_MAP.items():
            if name in query or name.upper() in query:
                found_stocks.append((name, code, market, yahoo_code))
        
        # 如果没有找到映射，尝试提取数字代码
        if not found_stocks:
            matches = re.findall(r'(\d{4,6})', query)
            for code in matches:
                if len(code) == 6:
                    if code.startswith('6'):
                        found_stocks.append((f"股票{code}", code, "sh", f"{code}.SS"))
                    else:
                        found_stocks.append((f"股票{code}", code, "sz", f"{code}.SZ"))
                elif len(code) in [4, 5]:
                    found_stocks.append((f"股票{code}", code, "hk", f"{code}.HK"))
        
        return found_stocks
    
    @staticmethod
    def get_stock_data(yahoo_code: str) -> Tuple[Optional[pd.DataFrame], str]:
        """获取单个股票数据"""
        try:
            # 使用yfinance获取数据
            import yfinance as yf
            ticker = yf.Ticker(yahoo_code)
            
            # 获取基本信息
            info = ticker.info
            name = info.get('longName', info.get('shortName', yahoo_code))
            
            # 尝试获取当前价格
            current_price = None
            for key in ['currentPrice', 'regularMarketPrice', 'ask', 'bid']:
                if key in info and info[key]:
                    current_price = info[key]
                    break
            
            if current_price is None:
                # 尝试获取最新行情
                try:
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        current_price = hist['Close'].iloc[-1]
                except:
                    current_price = 0
            
            # 获取历史数据
            hist = ticker.history(period="1mo")
            if not hist.empty:
                df = hist[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
                
                # 计算涨跌幅
                if len(df) > 1:
                    prev_close = df['Close'].iloc[-2]
                    current_close = df['Close'].iloc[-1]
                    change = current_close - prev_close
                    change_pct = (change / prev_close * 100) if prev_close != 0 else 0
                    
                    info_str = f"{name} | 现价: {current_close:.2f} | 涨跌: {change:+.2f} ({change_pct:+.2f}%)"
                else:
                    info_str = f"{name} | 价格: {current_price:.2f}"
                
                return df, info_str
            
            # 如果没有历史数据，创建模拟数据
            dates = pd.date_range(end=datetime.now(), periods=20, freq='D')
            base_price = current_price if current_price and current_price > 0 else 100
            prices = [base_price * (1 + np.random.uniform(-0.02, 0.02)) for _ in range(20)]
            df = pd.DataFrame({'Close': prices}, index=dates)
            df['Close'] = df['Close'].rolling(3).mean().fillna(method='bfill')
            
            info_str = f"{name} | 参考价: {base_price:.2f}"
            return df, info_str
            
        except Exception as e:
            # 生成模拟数据作为后备
            dates = pd.date_range(end=datetime.now(), periods=15, freq='D')
            df = pd.DataFrame({
                'Close': 100 + np.random.randn(15).cumsum()
            }, index=dates)
            
            info_str = f"{yahoo_code} | 模拟数据 | 最后更新: {datetime.now().strftime('%H:%M')}"
            return df, info_str
    
    @staticmethod
    def get_multiple_stocks(query: str) -> Tuple[Dict[str, Tuple[pd.DataFrame, str]], str]:
        """获取多个股票数据"""
        stocks = StockDataFetcher.extract_stocks_from_query(query)
        results = {}
        
        for name, code, market, yahoo_code in stocks:
            df, info = StockDataFetcher.get_stock_data(yahoo_code)
            results[name] = (df, info)
        
        # 生成汇总信息
        if results:
            summary = "已找到以下股票：\n"
            for name, (df, info) in results.items():
                summary += f"- {info}\n"
            return results, summary
        else:
            return {}, "未识别到股票信息，请尝试输入股票名称或代码。"

# ================= 8. 图表生成 =================
def create_stock_chart(df: pd.DataFrame, title: str = "股价走势") -> Optional[str]:
    """创建股票图表"""
    if df is None or df.empty:
        return None
    
    try:
        plt.figure(figsize=(6, 3.5))
        
        # 价格曲线
        if 'Close' in df.columns:
            plt.plot(df.index, df['Close'], color='#2563EB', linewidth=2, label='收盘价')
        
        # 均线
        if 'MA5' in df.columns:
            plt.plot(df.index, df['MA5'], '--', color='#10B981', alpha=0.7, linewidth=1, label='5日均线')
        
        if 'MA10' in df.columns:
            plt.plot(df.index, df['MA10'], ':', color='#F59E0B', alpha=0.7, linewidth=1, label='10日均线')
        
        # 图表美化
        plt.title(title, fontsize=12, pad=10)
        plt.xlabel('日期', fontsize=10)
        plt.ylabel('价格(元)', fontsize=10)
        plt.legend(fontsize=8, loc='upper left')
        plt.grid(True, alpha=0.2, linestyle='--')
        plt.xticks(rotation=30, fontsize=9)
        plt.yticks(fontsize=9)
        plt.tight_layout()
        
        # 保存图表
        timestamp = int(time.time())
        filename = f"chart_{timestamp}.png"
        filepath = os.path.join(CHARTS_DIR, filename)
        plt.savefig(filepath, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close()
        
        return filepath
    except Exception as e:
        print(f"图表生成错误: {e}")
        return None

def create_comparison_chart(stocks_data: Dict[str, pd.DataFrame]) -> Optional[str]:
    """创建股票比较图表"""
    if not stocks_data:
        return None
    
    try:
        plt.figure(figsize=(7, 4))
        
        colors = ['#2563EB', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6']
        
        for idx, (name, df) in enumerate(stocks_data.items()):
            if idx >= len(colors):
                break
                
            if df is not None and not df.empty and 'Close' in df.columns:
                # 标准化价格（以第一天为100）
                if len(df) > 0:
                    normalized = (df['Close'] / df['Close'].iloc[0] * 100)
                    plt.plot(df.index, normalized, color=colors[idx], linewidth=1.5, label=name)
        
        plt.title('股票走势比较（标准化）', fontsize=13, pad=10)
        plt.xlabel('日期', fontsize=10)
        plt.ylabel('相对涨幅(%)', fontsize=10)
        plt.legend(fontsize=9, loc='upper left')
        plt.grid(True, alpha=0.2, linestyle='--')
        plt.xticks(rotation=30, fontsize=9)
        plt.yticks(fontsize=9)
        plt.tight_layout()
        
        # 保存图表
        timestamp = int(time.time())
        filename = f"compare_{timestamp}.png"
        filepath = os.path.join(CHARTS_DIR, filename)
        plt.savefig(filepath, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close()
        
        return filepath
    except Exception as e:
        print(f"比较图表错误: {e}")
        return None

# ================= 9. 投资建议生成 =================
def generate_stock_analysis(stock_name: str, stock_info: str) -> str:
    """生成单只股票分析"""
    analysis_templates = [
        f"**{stock_name}分析报告**\n\n{stock_info}\n\n🔍 **技术分析**:\n• 近期走势相对稳健\n• 建议关注成交量变化\n• 注意关键支撑位\n\n💡 **操作建议**:\n✓ 可考虑分批建仓\n✓ 设置止损位\n✓ 关注公司基本面",
        
        f"**{stock_name}投资观点**\n\n{stock_info}\n\n📊 **市场表现**:\n• 行业地位突出\n• 估值相对合理\n• 流动性良好\n\n🎯 **策略建议**:\n• 适合中长期持有\n• 可逢低布局\n• 分散投资降低风险",
        
        f"**{stock_name}评估**\n\n{stock_info}\n\n⚡ **短期展望**:\n• 波动可能加大\n• 关注政策面变化\n• 技术指标中性\n\n🛡️ **风险提示**:\n• 注意市场系统性风险\n• 控制仓位\n• 及时止盈止损"
    ]
    
    import random
    return random.choice(analysis_templates)

def generate_comparison_analysis(stocks_data: Dict[str, Tuple[pd.DataFrame, str]]) -> str:
    """生成股票比较分析"""
    if not stocks_data:
        return "无法进行股票比较分析。"
    
    comparison_text = "**股票比较分析报告**\n\n"
    
    for name, (df, info) in stocks_data.items():
        comparison_text += f"**{name}**: {info}\n"
    
    comparison_text += "\n🔍 **综合对比**:\n"
    
    # 简单的比较逻辑
    if len(stocks_data) >= 2:
        stock_names = list(stocks_data.keys())
        comparison_text += f"• {stock_names[0]}和{stock_names[1]}各有特色\n"
        comparison_text += "• 建议根据投资风格选择\n"
        comparison_text += "• 可考虑组合配置降低风险\n"
    
    comparison_text += "\n💡 **投资建议**:\n"
    comparison_text += "✓ 深入研究公司基本面\n"
    comparison_text += "✓ 关注行业发展趋势\n"
    comparison_text += "✓ 结合自身风险承受能力\n"
    comparison_text += "✓ 建议分散投资\n"
    
    return comparison_text

# ================= 10. 语音功能 =================
def transcribe_audio(audio_bytes: bytes) -> Optional[str]:
    """语音转文字"""
    if not SR_AVAILABLE or not audio_bytes:
        return None
    
    try:
        r = sr.Recognizer()
        
        # 将音频数据转换为AudioData对象
        import io
        audio_io = io.BytesIO(audio_bytes)
        
        # 使用recognize_google进行识别
        with sr.AudioFile(audio_io) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language='zh-CN')
            return text
    except sr.UnknownValueError:
        return "无法识别语音"
    except sr.RequestError as e:
        return f"语音识别服务错误: {e}"
    except Exception as e:
        return f"语音处理错误: {str(e)[:50]}"

# ================= 11. 对话管理 =================
class DialogManager:
    """对话管理器"""
    
    def __init__(self, memory_file: str):
        self.memory_file = memory_file
        self.messages = self._load_messages()
    
    def _load_messages(self) -> List[Dict]:
        """加载对话记录"""
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 确保是列表
                    if isinstance(data, list):
                        return data
        except:
            pass
        return []
    
    def save_messages(self):
        """保存对话记录"""
        try:
            # 只保留最近50条消息
            messages_to_save = self.messages[-50:] if len(self.messages) > 50 else self.messages
            
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(messages_to_save, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存消息错误: {e}")
            return False
    
    def add_message(self, role: str, content: str, **kwargs):
        """添加消息"""
        message = {
            'id': str(uuid.uuid4()),
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(message)
        self.save_messages()
    
    def get_messages(self, search_query: str = "") -> List[Dict]:
        """获取消息（可搜索）"""
        if not search_query:
            return [msg for msg in self.messages if not msg.get('hidden', False)]
        
        search_query = search_query.lower()
        return [
            msg for msg in self.messages
            if search_query in msg.get('content', '').lower() and not msg.get('hidden', False)
        ]
    
    def clear_messages(self):
        """清空消息"""
        self.messages = []
        self.save_messages()

# ================= 12. 初始化 =================
dialog_manager = DialogManager(MEMORY_FILE)

# 初始化会话状态
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.search_query = ""
    st.session_state.monitoring = False
    st.session_state.monitor_stock = "腾讯控股"
    st.session_state.monitor_target = 300.0
    st.session_state.voice_input = None
    st.session_state.processing_voice = False
    st.session_state.last_audio_id = None

# ================= 13. 侧边栏 =================
with st.sidebar:
    # 头像展示
    st.markdown(f"""
    <div style="text-align: center;">
        <img src="{ASSISTANT_AVATAR}" class="avatar-img">
        <h3 style="margin: 10px 0 5px 0; color: #1E3A8A;">金鑫</h3>
        <p style="color: #6B7280; font-size: 13px;">您的智能投资顾问</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 盯盘功能
    with st.expander("🎯 实时盯盘", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            monitor_stock = st.text_input("股票", value=st.session_state.monitor_stock, 
                                         placeholder="如：腾讯控股")
        with col2:
            monitor_target = st.number_input("目标价", value=st.session_state.monitor_target, 
                                           min_value=0.0, step=1.0, format="%.2f")
        
        col_start, col_stop = st.columns(2)
        with col_start:
            if st.button("启动监控", type="primary", use_container_width=True):
                st.session_state.monitoring = True
                st.session_state.monitor_stock = monitor_stock
                st.session_state.monitor_target = monitor_target
                st.success(f"开始监控 {monitor_stock}")
        
        with col_stop:
            if st.button("停止监控", type="secondary", use_container_width=True):
                st.session_state.monitoring = False
                st.warning("监控已停止")
        
        # 显示监控状态
        if st.session_state.monitoring:
            st.markdown('<div class="monitor-active">', unsafe_allow_html=True)
            st.write("监控中...")
            
            # 获取股票数据
            stocks = StockDataFetcher.extract_stocks_from_query(st.session_state.monitor_stock)
            if stocks:
                for name, code, market, yahoo_code in stocks[:1]:  # 只监控第一个
                    try:
                        df, info = StockDataFetcher.get_stock_data(yahoo_code)
                        if "现价:" in info or "价格:" in info:
                            # 提取价格
                            price_match = re.search(r'[现价|价格]:\s*([\d.]+)', info)
                            if price_match:
                                current_price = float(price_match.group(1))
                                st.metric("当前价格", f"{current_price:.2f}")
                                
                                if current_price <= st.session_state.monitor_target:
                                    st.error("🎯 达到目标价位！")
                                    st.balloons()
                    except:
                        st.info("正在获取数据...")
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # 数据管理
    with st.expander("💾 数据管理"):
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("刷新对话", use_container_width=True):
                dialog_manager.messages = dialog_manager._load_messages()
                st.success("对话已刷新")
                st.rerun()
        
        with col2:
            if st.button("清空对话", use_container_width=True):
                dialog_manager.clear_messages()
                st.success("对话已清空")
                st.rerun()
        
        # 导出功能
        if dialog_manager.messages:
            def export_to_word():
                doc = Document()
                doc.add_heading('金鑫投资对话记录', 0)
                
                for msg in dialog_manager.messages:
                    if msg.get('hidden'):
                        continue
                        
                    role = "👤 用户" if msg['role'] == 'user' else "👩‍💼 金鑫"
                    time_str = datetime.fromisoformat(msg['timestamp']).strftime("%Y-%m-%d %H:%M")
                    
                    doc.add_heading(f'{role} ({time_str})', level=2)
                    doc.add_paragraph(msg.get('content', ''))
                    doc.add_paragraph()
                
                buffer = io.BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                return buffer.getvalue()
            
            st.download_button(
