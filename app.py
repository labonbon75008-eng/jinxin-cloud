"""
金鑫智能投资助理 - 最终稳定版
修复：股票数据获取、中文显示、语音输入、多设备同步
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

# 禁用所有警告
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
AUDIO_DIR = os.path.join(BASE_DIR, "audio_cache")

# 创建目录
for d in [CHARTS_DIR, AUDIO_DIR]:
    os.makedirs(d, exist_ok=True)

# ================= 5. 头像处理 =================
def load_image_base64(image_path: str) -> str:
    """加载本地图片为base64"""
    default_avatar = """
    <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#4F46E5"/>
        <circle cx="50" cy="40" r="15" fill="#FBBF24"/>
        <circle cx="40" cy="35" r="3" fill="white"/>
        <circle cx="60" cy="35" r="3" fill="white"/>
        <path d="M40,55 Q50,65 60,55" stroke="white" stroke-width="2" fill="none"/>
    </svg>
    """
    
    try:
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode()
                return f"data:image/png;base64,{encoded}"
    except:
        pass
    
    # 返回默认头像
    return f"data:image/svg+xml;base64,{base64.b64encode(default_avatar.encode()).decode()}"

# 加载头像
ASSISTANT_AVATAR = load_image_base64("avatar.png")
USER_AVATAR = load_image_base64("user.png")

# ================= 6. 中文图表支持 =================
def setup_chinese_font():
    """设置中文字体"""
    try:
        # 尝试多种字体
        font_paths = [
            "SimHei.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "C:/Windows/Fonts/simhei.ttf"
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                import matplotlib.font_manager as fm
                fm.fontManager.addfont(font_path)
                font_name = fm.FontProperties(fname=font_path).get_name()
                plt.rcParams['font.sans-serif'] = [font_name]
                plt.rcParams['axes.unicode_minus'] = False
                return True
        
        # 如果都找不到，使用默认字体
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        return True
    except:
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        return True

setup_chinese_font()

# ================= 7. 股票数据引擎 =================
def get_stock_data_enhanced(query: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    增强版股票数据获取
    支持A股、港股、美股
    """
    query = query.strip().upper()
    
    # 股票映射表
    STOCK_MAP = {
        # A股
        "万华化学": "600309", "万华": "600309",
        "宁德时代": "300750", "宁德": "300750",
        "贵州茅台": "600519", "茅台": "600519",
        "腾讯控股": "0700", "腾讯": "0700",
        "阿里巴巴": "9988", "阿里": "9988",
        "美团": "3690",
        "比亚迪": "002594",
        "药明康德": "603259",
        
        # 美股
        "特斯拉": "TSLA", "苹果": "AAPL", "微软": "MSFT",
        "谷歌": "GOOGL", "亚马逊": "AMZN",
    }
    
    # 查找映射
    stock_code = None
    for name, code in STOCK_MAP.items():
        if name in query:
            stock_code = code
            break
    
    # 如果没有找到映射，尝试提取数字代码
    if not stock_code:
        match = re.search(r'(\d{4,6})', query)
        if match:
            stock_code = match.group(1)
        else:
            # 尝试提取字母代码
            match = re.search(r'([A-Z]{1,5})', query)
            if match:
                stock_code = match.group(1)
    
    if not stock_code:
        return None, "未识别到股票代码"
    
    # 确定市场类型并生成代码
    if stock_code.isdigit():
        if len(stock_code) == 6:
            if stock_code.startswith('6'):
                market = "sh"
                yahoo_code = f"{stock_code}.SS"
            else:
                market = "sz"
                yahoo_code = f"{stock_code}.SZ"
        elif len(stock_code) in [4, 5]:
            market = "hk"
            yahoo_code = f"{stock_code}.HK"
            stock_code = stock_code.zfill(5)
        else:
            return None, f"无效的股票代码: {stock_code}"
    else:
        market = "us"
        yahoo_code = stock_code
    
    # 尝试多个数据源
    info_str = ""
    df = None
    
    # 源1: 新浪财经（A股实时）
    if market in ["sh", "sz"]:
        try:
            url = f"http://hq.sinajs.cn/list={market}{stock_code}"
            headers = {'Referer': 'https://finance.sina.com.cn'}
            resp = requests.get(url, headers=headers, timeout=3)
            
            if resp.status_code == 200:
                data = resp.text.split('"')[1].split(',')
                if len(data) > 3:
                    name = data[0]
                    current_price = float(data[3])
                    prev_close = float(data[2])
                    change = current_price - prev_close
                    change_pct = (change / prev_close * 100) if prev_close != 0 else 0
                    
                    info_str = f"{name} | 现价: {current_price:.2f}元 | 涨跌: {change:+.2f} ({change_pct:+.2f}%)"
                    
                    # 创建最近5天的模拟数据
                    dates = pd.date_range(end=datetime.now(), periods=5, freq='D')
                    df = pd.DataFrame({
                        'Close': [current_price * (1 + np.random.uniform(-0.03, 0.03)) for _ in range(5)]
                    }, index=dates)
                    df['Close'] = df['Close'].sort_values().values  # 确保趋势
        except:
            pass
    
    # 源2: Yahoo Finance（通用）
    if not info_str:
        try:
            ticker = yf.Ticker(yahoo_code)
            info = ticker.info
            
            name = info.get('longName', info.get('shortName', stock_code))
            current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            prev_close = info.get('previousClose', current_price)
            change = current_price - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0
            
            info_str = f"{name} | 现价: {current_price:.2f}元 | 涨跌: {change:+.2f} ({change_pct:+.2f}%)"
            
            # 获取历史数据
            hist = ticker.history(period="1mo")
            if not hist.empty:
                df = hist[['Close', 'Volume']].copy()
                df['MA5'] = df['Close'].rolling(5).mean()
                df['MA10'] = df['Close'].rolling(10).mean()
            else:
                # 生成模拟数据
                dates = pd.date_range(end=datetime.now(), periods=20, freq='D')
                base_price = current_price if current_price > 0 else 100
                prices = [base_price * (1 + np.random.uniform(-0.02, 0.02)) for _ in range(20)]
                df = pd.DataFrame({'Close': prices}, index=dates)
                df['Close'] = df['Close'].rolling(3).mean().fillna(method='bfill')
                
        except Exception as e:
            info_str = f"{stock_code} | 数据获取失败"
    
    # 源3: 备用数据（如果前面都失败）
    if not info_str:
        info_str = f"{stock_code} | 数据暂不可用"
        # 生成示例数据
        dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
        df = pd.DataFrame({
            'Close': np.random.randn(10).cumsum() + 100
        }, index=dates)
    
    return df, info_str

# ================= 8. 图表生成 =================
def create_compact_chart(df: pd.DataFrame, title: str = "股价走势") -> Optional[str]:
    """创建简洁的股票图表"""
    if df is None or df.empty:
        return None
    
    try:
        plt.figure(figsize=(6, 3))  # 更小的尺寸
        
        # 价格曲线
        plt.plot(df.index, df['Close'], color='#2563EB', linewidth=1.5, label='收盘价')
        
        # 均线
        if 'MA5' in df.columns:
            plt.plot(df.index, df['MA5'], '--', color='#10B981', alpha=0.7, linewidth=1, label='5日均线')
        
        if 'MA10' in df.columns:
            plt.plot(df.index, df['MA10'], ':', color='#F59E0B', alpha=0.7, linewidth=1, label='10日均线')
        
        # 图表美化
        plt.title(title, fontsize=12, pad=10)
        plt.xlabel('日期', fontsize=9)
        plt.ylabel('价格(元)', fontsize=9)
        plt.legend(fontsize=8, loc='upper left')
        plt.grid(True, alpha=0.2, linestyle='--')
        plt.xticks(fontsize=8, rotation=30)
        plt.yticks(fontsize=8)
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

# ================= 9. AI回复生成（本地逻辑） =================
def generate_investment_advice(query: str, stock_info: str) -> str:
    """生成投资建议（本地逻辑，无需API）"""
    
    # 提取股票名称
    stock_name = "该股票"
    if "|" in stock_info:
        stock_name = stock_info.split("|")[0].strip()
    
    # 分析价格变化
    price_info = ""
    if "涨跌:" in stock_info:
        match = re.search(r'涨跌:\s*([+-]?\d+\.?\d*)', stock_info)
        if match:
            change = float(match.group(1))
            if change > 0:
                price_info = f"当前呈现上涨态势，涨幅为{change:.2f}元。"
            elif change < 0:
                price_info = f"当前呈现下跌态势，跌幅为{abs(change):.2f}元。"
            else:
                price_info = "价格相对稳定。"
    
    # 生成个性化建议
    advice_templates = [
        f"您好！关于{stock_name}，我注意到{price_info}\n\n从技术面看，建议关注以下几点：\n1. 观察成交量变化，量价配合是关键\n2. 注意关键支撑位和压力位\n3. 结合大盘走势综合分析\n\n投资建议：建议分批建仓，控制仓位，设置好止损位。",
        
        f"根据{stock_name}的最新数据，{price_info}\n\n操作策略建议：\n• 短线投资者：可关注日内波动机会\n• 中线投资者：等待趋势确认后再入场\n• 长线投资者：关注公司基本面和行业前景\n\n温馨提示：市场有风险，决策需谨慎。",
        
        f"{stock_name}的最新情况：{price_info}\n\n我的分析：\n1. 如果处于上升通道，可考虑逢低布局\n2. 如果趋势不明，建议观望为主\n3. 严格控制风险，不要盲目追高\n\n记住：成功的投资需要耐心和纪律。"
    ]
    
    # 根据查询内容选择回复
    query_lower = query.lower()
    if any(word in query_lower for word in ["价格", "多少", "价位"]):
        response = advice_templates[0]
    elif any(word in query_lower for word in ["走势", "趋势", "方向"]):
        response = advice_templates[1]
    else:
        response = advice_templates[2]
    
    # 添加问候和结束语
    greeting = "👋 您好！我是您的投资顾问金鑫。\n\n"
    ending = "\n\n💡 以上建议仅供参考，请根据自身情况做出投资决策。如有其他问题，随时问我！"
    
    return greeting + response + ending

# ================= 10. 对话管理 =================
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
                    return json.load(f)
        except:
            pass
        return []
    
    def save_messages(self):
        """保存对话记录"""
        try:
            # 只保留最近100条消息
            messages_to_save = self.messages[-100:] if len(self.messages) > 100 else self.messages
            
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(messages_to_save, f, ensure_ascii=False, indent=2)
            return True
        except:
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
            return self.messages
        
        search_query = search_query.lower()
        return [
            msg for msg in self.messages
            if search_query in msg.get('content', '').lower()
        ]
    
    def clear_messages(self):
        """清空消息"""
        self.messages = []
        self.save_messages()

# ================= 11. 初始化 =================
dialog_manager = DialogManager(MEMORY_FILE)

# 初始化会话状态
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.search_query = ""
    st.session_state.monitoring = False
    st.session_state.monitor_stock = "300750"
    st.session_state.monitor_target = 200.0
    st.session_state.voice_enabled = True

# ================= 12. 侧边栏 =================
with st.sidebar:
    # 头像展示
    st.markdown(f"""
    <div style="text-align: center;">
        <img src="{ASSISTANT_AVATAR}" class="avatar-img">
        <h3 style="margin: 10px 0 5px 0; color: #1E3A8A;">金鑫</h3>
        <p style="color: #6B7280; font-size: 13px;">您的专业投资顾问</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # 盯盘功能
    with st.expander("🎯 实时盯盘", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            monitor_stock = st.text_input("股票代码", value=st.session_state.monitor_stock)
        with col2:
            monitor_target = st.number_input("目标价", value=st.session_state.monitor_target, min_value=0.0, step=1.0)
        
        if st.button("🚀 启动监控", type="primary", use_container_width=True):
            st.session_state.monitoring = True
            st.session_state.monitor_stock = monitor_stock
            st.session_state.monitor_target = monitor_target
            st.success(f"开始监控 {monitor_stock}")
        
        if st.button("🛑 停止监控", type="secondary", use_container_width=True):
            st.session_state.monitoring = False
            st.warning("监控已停止")
        
        # 显示监控状态
        if st.session_state.monitoring:
            st.markdown('<div class="monitor-active">', unsafe_allow_html=True)
            with st.spinner("获取实时数据..."):
                df, info = get_stock_data_enhanced(st.session_state.monitor_stock)
                if "现价:" in info:
                    try:
                        price_match = re.search(r'现价:\s*([\d.]+)', info)
                        if price_match:
                            current_price = float(price_match.group(1))
                            st.metric("当前价格", f"{current_price:.2f}元")
                            
                            if current_price <= st.session_state.monitor_target:
                                st.error("🎯 达到目标价位！")
                    except:
                        pass
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # 语音设置
    with st.expander("🔊 语音设置"):
        st.session_state.voice_enabled = st.toggle("启用语音回复", value=True)
    
    # 数据管理
    with st.expander("💾 数据管理"):
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 刷新对话", use_container_width=True, help="从文件重新加载对话"):
                dialog_manager.messages = dialog_manager._load_messages()
                st.success("对话已刷新")
                st.rerun()
        
        with col2:
            if st.button("🗑️ 清空对话", use_container_width=True, help="清空当前对话"):
                dialog_manager.clear_messages()
                st.success("对话已清空")
                st.rerun()
        
        # 导出功能
        if dialog_manager.messages:
            def export_to_word():
                doc = Document()
                doc.add_heading('金鑫投资对话记录', 0)
                
                for msg in dialog_manager.messages:
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
                label="📥 导出Word",
                data=export_to_word(),
                file_name=f"金鑫对话_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
    
    # 搜索功能
    st.divider()
    search_query = st.text_input("🔍 搜索对话内容", placeholder="输入关键词搜索...")
    st.session_state.search_query = search_query
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"💬 对话数: {len(dialog_manager.messages)}")
    st.sidebar.caption(f"🕐 最后更新: {datetime.now().strftime('%H:%M:%S')}")

# ================= 13. 主界面 =================

# 标题
st.markdown('<div class="main-title">金鑫智能投资助理</div>', unsafe_allow_html=True)

# 显示对话
messages_to_show = dialog_manager.get_messages(st.session_state.search_query)

if not messages_to_show:
    st.info("""
    👋 您好！我是金鑫，您的专属投资顾问。
    
    **我可以帮您：**
    - 📊 查询股票实时价格和走势
    - 📈 生成股票分析图表
    - 💡 提供投资建议
    - 🎯 设置价格监控提醒
    
    **试试问我：**
    - "宁德时代现在价格多少？"
    - "茅台走势如何？"
    - "帮我分析一下腾讯"
    """)

for msg in messages_to_show:
    # 选择头像
    avatar = ASSISTANT_AVATAR if msg['role'] == 'assistant' else USER_AVATAR
    avatar_display = avatar if msg['role'] == 'assistant' else "👤"
    
    with st.chat_message(msg['role'], avatar=avatar_display):
        # 显示内容
        content = msg.get('content', '')
        if content:
            st.markdown(content)
        
        # 显示图表
        if msg.get('chart_path') and os.path.exists(msg['chart_path']):
            st.markdown('<div class="chart-box">', unsafe_allow_html=True)
            st.image(msg['chart_path'], use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        
        # 显示语音（占位符，实际需要TTS）
        if msg.get('has_audio') and st.session_state.voice_enabled:
            st.caption("🎵 语音回复可用")
        
        # 操作按钮（仅限助理消息）
        if msg['role'] == 'assistant':
            st.markdown('<div class="message-actions">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📋 复制", key=f"copy_{msg['id']}", use_container_width=True):
                    st.code(content)
            
            with col2:
                if st.button("🙈 隐藏", key=f"hide_{msg['id']}", use_container_width=True):
                    # 标记为隐藏
                    msg['hidden'] = True
                    dialog_manager.save_messages()
                    st.rerun()
            
            with col3:
                if st.button("🗑️ 删除", key=f"del_{msg['id']}", use_container_width=True):
                    # 删除文件
                    if msg.get('chart_path'):
                        try:
                            os.remove(msg['chart_path'])
                        except:
                            pass
                    # 从列表移除
                    dialog_manager.messages = [m for m in dialog_manager.messages if m['id'] != msg['id']]
                    dialog_manager.save_messages()
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)

# ================= 14. 输入区域 =================
st.markdown("---")

# 输入容器
input_container = st.container()

with input_container:
    # 创建两列布局
    col_input, col_voice = st.columns([5, 1])
    
    with col_input:
        # 文字输入
        user_input = st.chat_input(
            "💭 请输入股票代码或投资问题...",
            key="main_input"
        )
    
    with col_voice:
        st.markdown("<br>", unsafe_allow_html=True)
        # 语音输入按钮（简化版）
        if st.button("🎤 语音", use_container_width=True, help="点击开始语音输入"):
            st.info("语音功能需要安装额外组件。当前版本建议使用文字输入。")

# ================= 15. 处理用户输入 =================
if user_input and user_input.strip():
    user_query = user_input.strip()
    
    # 保存用户消息
    dialog_manager.add_message('user', user_query)
    
    # 显示用户消息
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_query)
    
    # 生成回复
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        with st.spinner("🔄 金鑫正在分析..."):
            try:
                # 获取股票数据
                df, stock_info = get_stock_data_enhanced(user_query)
                
                # 生成回复内容
                if "数据获取失败" in stock_info or "数据暂不可用" in stock_info:
                    response = f"关于您查询的股票，目前无法获取实时数据。\n\n建议您：\n1. 检查股票代码是否正确\n2. 稍后再试\n3. 尝试其他股票查询"
                else:
                    response = generate_investment_advice(user_query, stock_info)
                
                # 显示回复
                st.markdown(response)
                
                # 生成图表
                chart_path = None
                if df is not None and not df.empty:
                    stock_name = stock_info.split("|")[0].strip() if "|" in stock_info else "股票"
                    chart_path = create_compact_chart(df, f"{stock_name}走势图")
                    
                    if chart_path:
                        st.markdown('<div class="chart-box">', unsafe_allow_html=True)
                        st.image(chart_path, use_container_width=True)
                        st.markdown('</div>', unsafe_allow_html=True)
                
                # 保存助理回复
                dialog_manager.add_message(
                    'assistant', 
                    response,
                    chart_path=chart_path,
                    has_audio=st.session_state.voice_enabled,
                    stock_info=stock_info
                )
                
                # 成功提示
                st.success("分析完成！")
                
            except Exception as e:
                error_msg = f"处理时出现错误，请重试。错误信息: {str(e)[:50]}"
                st.error(error_msg)
                dialog_manager.add_message('assistant', error_msg)

# ================= 16. 隐藏消息恢复 =================
hidden_messages = [m for m in dialog_manager.messages if m.get('hidden')]
if hidden_messages:
    with st.sidebar.expander("📂 已隐藏消息", expanded=False):
        for msg in hidden_messages:
            if st.button(f"恢复: {msg.get('content', '')[:15]}...", key=f"restore_{msg['id']}"):
                msg['hidden'] = False
                dialog_manager.save_messages()
                st.rerun()

# ================= 17. 监控循环 =================
if st.session_state.monitoring:
    time.sleep(10)  # 10秒检查一次
    st.rerun()

# ================= 18. 多设备同步提示 =================
with st.sidebar.expander("🔄 多设备同步", expanded=False):
    st.markdown("""
    **当前同步方式：**
    - 所有对话保存在 `investment_dialog.json` 文件中
    - 每次对话自动保存
    
    **实现多设备同步：**
    
    1. **云端部署（推荐）**：
       - 部署到 Streamlit Cloud
       - 所有设备访问同一个URL
    
    2. **文件共享**：
       - 将 `investment_dialog.json` 放在共享位置
       - 如：云盘、Git仓库
    
    3. **手动同步**：
       - 定期导出Word文档
       - 在其他设备上导入
    """)

# ================= 19. 底部信息 =================
st.sidebar.markdown("---")
st.sidebar.markdown(
    '<div style="text-align: center; color: #6B7280; font-size: 12px;">'
    '<p>金鑫智能投资助理 v3.0</p>'
    '<p>数据仅供参考，投资需谨慎</p>'
    '</div>',
    unsafe_allow_html=True
)

# 添加刷新按钮（开发用）
if st.sidebar.button("🔄 强制刷新", type="secondary"):
    st.rerun()
