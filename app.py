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
st.set_page_config(page_title="币安风控哨兵Pro", page_icon="🛡️", layout="wide")
st.title("🛡️ 币安风控哨兵 (智能过滤+钉钉版)")

# --- 侧边栏 ---
st.sidebar.header("🔐 身份验证")
api_key = st.sidebar.text_input("API Key", type="password")
api_secret = st.sidebar.text_input("Secret Key", type="password")

st.sidebar.header("🔔 通知设置")
dingtalk_url = st.sidebar.text_input("钉钉Webhook", type="password")
enable_monitor = st.sidebar.checkbox("✅ 开启自动监控 (每60秒)", value=False)

# --- 钉钉发送函数 ---
def send_dingtalk_alert(webhook_url, content):
    if not webhook_url: return False
    try:
        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "text",
            "text": {
                "content": f"🚨 [币安风控警报] \n{content}\n⏰ {datetime.now().strftime('%H:%M:%S')}"
            }
        }
        resp = requests.post(webhook_url, headers=headers, data=json.dumps(data))
        return resp.status_code == 200
    except Exception as e:
        return False

# =========== 👇 帮你把测试按钮加回来了！ ===========
if st.sidebar.button("🔔 点我测试钉钉"):
    if not dingtalk_url:
        st.sidebar.error("❌ 请先填入 Webhook 链接！")
    else:
        success = send_dingtalk_alert(dingtalk_url, "【系统自检】配置成功！\n如果有新增的高危币种，我会立刻通知你。")
        if success:
            st.sidebar.success("✅ 发送成功！手机应该响了。")
        else:
            st.sidebar.error("❌ 发送失败，请检查关键词是否设为'警报'。")
# ================================================

# --- 核心：智能获取白名单 ---
def get_active_symbols_safe():
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            trading_list = set()
            for s in data['symbols']:
                if s['status'] == 'TRADING' and s['symbol'].endswith("USDT"):
                    trading_list.add(s['symbol'])
            return trading_list, True
    except:
        pass
    return set(), False

# --- 扫描逻辑 ---
def scan_market(key, secret):
    base_url = "https://fapi.binance.com"
    endpoint = "/fapi/v1/leverageBracket"
    try:
        # 签名
        timestamp = int(time.time() * 1000)
        params = {'timestamp': timestamp}
        query_string = urlencode(params)
        signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        headers = {'X-MBX-APIKEY': key}
        final_url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
        
        response = requests.get(final_url, headers=headers, timeout=10)
        
        # 获取白名单
        active_symbols, filter_success = get_active_symbols_safe()
        
        current_risky_coins = []
        if response.status_code == 200:
            data = response.json()
            for item in data:
                symbol = item['symbol']
                if not symbol.endswith("USDT"): continue
                
                # 智能过滤：如果白名单获取成功，且币不在名单里，则跳过
                if filter_success and (symbol not in active_symbols):
                    continue
                
                max_leverage = item['brackets'][0]['initialLeverage']
                
                if max_leverage < 20:
                    current_risky_coins.append({
                        "symbol": symbol,
                        "leverage": max_leverage
                    })
            return current_risky_coins, filter_success
        else:
            return [], False
    except:
        return [], False

# --- 主程序 ---
if not api_key or not api_secret:
    st.info("👈 请在左侧填入 API Key")
else:
    status_place = st.empty()
    table_place = st.empty()

    if enable_monitor:
        while True:
            risky_list, is_filtered = scan_market(api_key, api_secret)
            
            # 状态显示
            status_text = f"🔄 扫描中... {datetime.now().strftime('%H:%M:%S')}"
            status_text += " | ✅ 下架币已过滤" if is_filtered else " | ⚠️ 暂时显示全部"
            with status_place.container():
                st.info(status_text)
            
            # --- 报警逻辑的核心在这里 ---
            if risky_list:
                current_symbols = {item['symbol'] for item in risky_list}
                
                # 初始化记忆
                if 'known_coins' not in st.session_state:
                    st.session_state.known_coins = current_symbols
                
                # 比对：现在的 - 刚才记下的 = 新增的
                if st.session_state.known_coins:
                    new_added = current_symbols - st.session_state.known_coins
                    if new_added:
                        # 只有这里才会触发真实报警！
                        msg = f"发现新增高危合约: {', '.join(new_added)}"
                        st.toast(msg, icon="🔥")
                        if dingtalk_url: send_dingtalk_alert(dingtalk_url, msg)
                
                # 更新记忆
                st.session_state.known_coins = current_symbols

                # 表格
                df = pd.DataFrame(risky_list)
                df.columns = ["币种", "最大杠杆"]
                df = df.sort_values(by="最大杠杆")
                df = df.reset_index(drop=True)
                df.index = df.index + 1
                table_place.dataframe(df, use_container_width=True)
            else:
                st.session_state.known_coins = set()
                table_place.success("✅ 全场安全")
            
            time.sleep(60)
            st.rerun()
            
    else:
        if st.button("🚀 手动扫描一次"):
            risky_list, is_filtered = scan_market(api_key, api_secret)
            if risky_list:
                df = pd.DataFrame(risky_list)
                df.columns = ["币种", "最大杠杆"]
                df = df.sort_values(by="最大杠杆")
                st.dataframe(df)
            else:
                st.success("✅ 无异常")
