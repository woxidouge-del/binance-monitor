import streamlit as st
import requests
import pandas as pd
import time
import hmac
import hashlib
import json
from urllib.parse import urlencode
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(page_title="币安风控哨兵(云端版)", page_icon="☁️", layout="wide")
st.title("☁️ 币安风控哨兵 (云端运行中)")

# --- 侧边栏设置 ---
st.sidebar.header("🔐 身份验证")
api_key = st.sidebar.text_input("API Key", type="password")
api_secret = st.sidebar.text_input("Secret Key", type="password")

st.sidebar.header("🔔 通知设置")
dingtalk_url = st.sidebar.text_input("钉钉机器人Webhook", type="password")
enable_monitor = st.sidebar.checkbox("✅ 开启自动监控 (每60秒)", value=False)

# --- 功能函数：发钉钉消息 ---
def send_dingtalk_alert(webhook_url, content):
    if not webhook_url: return False
    try:
        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "text",
            "text": {
                "content": f"🚨 [币安风控警报] \n{content}\n⏰ 时间: {datetime.now().strftime('%H:%M:%S')}"
            }
        }
        resp = requests.post(webhook_url, headers=headers, data=json.dumps(data))
        return resp.status_code == 200
    except Exception as e:
        print(f"发送钉钉失败: {e}")
        return False

# =========== 测试按钮 ===========
if st.sidebar.button("🔔 测试钉钉发送"):
    if not dingtalk_url:
        st.sidebar.error("❌ 请先填入 Webhook 链接！")
    else:
        success = send_dingtalk_alert(dingtalk_url, "【云端测试】配置成功！程序正在云服务器上运行。")
        if success:
            st.sidebar.success("✅ 发送成功！")
        else:
            st.sidebar.error("❌ 发送失败，请检查关键词。")
# ===============================

# --- 状态初始化 ---
if 'known_coins' not in st.session_state:
    st.session_state.known_coins = set()

# --- 获取白名单 ---
def get_trading_symbols():
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=5)
        data = response.json()
        trading_list = []
        for s in data['symbols']:
            if s['status'] == 'TRADING' and s['symbol'].endswith("USDT"):
                trading_list.append(s['symbol'])
        return set(trading_list)
    except:
        return set()

# --- 核心扫描 ---
def scan_market(key, secret):
    base_url = "https://fapi.binance.com"
    endpoint = "/fapi/v1/leverageBracket"
    try:
        active_symbols = get_trading_symbols()
        if not active_symbols: return []

        timestamp = int(time.time() * 1000)
        params = {'timestamp': timestamp}
        query_string = urlencode(params)
        signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        
        headers = {'X-MBX-APIKEY': key}
        final_url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
        
        response = requests.get(final_url, headers=headers, timeout=10)
        
        current_risky_coins = []
        if response.status_code == 200:
            data = response.json()
            for item in data:
                symbol = item['symbol']
                if symbol not in active_symbols: continue
                
                max_leverage = item['brackets'][0]['initialLeverage']
                
                if max_leverage < 20:
                    current_risky_coins.append({
                        "symbol": symbol,
                        "leverage": max_leverage
                    })
            return current_risky_coins
        else:
            return []
    except:
        return []

# --- 主程序 ---
if not api_key or not api_secret:
    st.info("👈 请在左侧填入 API Key 和 钉钉链接。")
else:
    status_place = st.empty()
    table_place = st.empty()

    if enable_monitor:
        while True:
            with status_place.container():
                st.info(f"🔄 云端监控运行中... {datetime.now().strftime('%H:%M:%S')}")
            
            risky_list = scan_market(api_key, api_secret)
            current_symbols = {item['symbol'] for item in risky_list}
            
            # --- 比对逻辑 ---
            if not st.session_state.known_coins:
                st.session_state.known_coins = current_symbols
            else:
                new_added = current_symbols - st.session_state.known_coins
                
                if new_added:
                    msg = f"发现新增高危合约: {', '.join(new_added)}"
                    st.toast(msg, icon="🔥")
                    
                    if dingtalk_url:
                        send_dingtalk_alert(dingtalk_url, msg)
                
                st.session_state.known_coins = current_symbols

            # 表格展示
            if risky_list:
                df = pd.DataFrame(risky_list)
                df.columns = ["币种", "最大杠杆"]
                df = df.sort_values(by="最大杠杆")
                df = df.reset_index(drop=True)
                df.index = df.index + 1
                table_place.dataframe(df, use_container_width=True)
            else:
                table_place.success("✅ 暂无异常 (云端连接正常)。")
            
            time.sleep(60)
            st.rerun()
            
    else:
        if st.button("🚀 手动扫描一次"):
            risky_list = scan_market(api_key, api_secret)
            if risky_list:
                df = pd.DataFrame(risky_list)
                df.columns = ["币种", "最大杠杆"]
                df = df.sort_values(by="最大杠杆")
                st.dataframe(df)
            else:
                st.success("✅ 安全。")