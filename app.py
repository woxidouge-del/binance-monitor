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
st.title("🛡️ 币安风控哨兵 (智能过滤版)")

# --- 侧边栏 ---
st.sidebar.header("🔐 身份验证")
api_key = st.sidebar.text_input("API Key", type="password")
api_secret = st.sidebar.text_input("Secret Key", type="password")

st.sidebar.header("🔔 通知设置")
dingtalk_url = st.sidebar.text_input("钉钉Webhook", type="password")
enable_monitor = st.sidebar.checkbox("✅ 开启自动监控 (每60秒)", value=False)

# --- 钉钉发送 ---
def send_dingtalk_alert(webhook_url, content):
    if not webhook_url: return
    try:
        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "text",
            "text": {
                "content": f"🚨 [币安风控警报] \n{content}\n⏰ {datetime.now().strftime('%H:%M:%S')}"
            }
        }
        requests.post(webhook_url, headers=headers, data=json.dumps(data))
    except: pass

# --- 核心：尝试获取白名单 (带容错机制) ---
def get_active_symbols_safe():
    try:
        # 尝试连接币安获取正在交易的币种
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=5) # 5秒超时
        if response.status_code == 200:
            data = response.json()
            trading_list = set()
            for s in data['symbols']:
                if s['status'] == 'TRADING' and s['symbol'].endswith("USDT"):
                    trading_list.add(s['symbol'])
            return trading_list, True # 成功获取
    except:
        pass
    return set(), False # 获取失败，返回空集合和失败标记

# --- 扫描逻辑 ---
def scan_market(key, secret):
    base_url = "https://fapi.binance.com"
    endpoint = "/fapi/v1/leverageBracket"
    
    try:
        # 1. 签名认证
        timestamp = int(time.time() * 1000)
        params = {'timestamp': timestamp}
        query_string = urlencode(params)
        signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        headers = {'X-MBX-APIKEY': key}
        final_url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
        
        # 2. 获取杠杆数据
        response = requests.get(final_url, headers=headers, timeout=10)
        
        # 3. 智能获取白名单
        active_symbols, filter_success = get_active_symbols_safe()
        
        current_risky_coins = []
        if response.status_code == 200:
            data = response.json()
            for item in data:
                symbol = item['symbol']
                
                # 基础过滤
                if not symbol.endswith("USDT"): continue
                
                # ⚠️ 智能过滤逻辑：
                # 如果白名单获取成功(filter_success=True)，且该币不在名单里 -> 说明是下架币，跳过！
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
            # 扫描
            risky_list, is_filtered = scan_market(api_key, api_secret)
            
            # 状态栏显示是否过滤成功
            status_text = f"🔄 扫描中... {datetime.now().strftime('%H:%M:%S')}"
            if is_filtered:
                status_text += " | ✅ 下架币已过滤"
            else:
                status_text += " | ⚠️ 网络波动，暂时显示全部 (含下架)"
                
            with status_place.container():
                st.info(status_text)
            
            # --- 列表处理 ---
            if risky_list:
                current_symbols = {item['symbol'] for item in risky_list}
                
                if 'known_coins' not in st.session_state: st.session_state.known_coins = set()
                
                # 比对新增
                if st.session_state.known_coins:
                    new_added = current_symbols - st.session_state.known_coins
                    if new_added:
                        msg = f"新增受限合约: {', '.join(new_added)}"
                        st.toast(msg, icon="🔥")
                        if dingtalk_url: send_dingtalk_alert(dingtalk_url, msg)
                
                st.session_state.known_coins = current_symbols

                # 表格
                df = pd.DataFrame(risky_list)
                df.columns = ["币种", "最大杠杆"]
                df = df.sort_values(by="最大杠杆")
                df = df.reset_index(drop=True)
                df.index = df.index + 1
                table_place.dataframe(df, use_container_width=True)
            else:
                table_place.success("✅ 全场安全 (无异常合约)")
            
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
                if not is_filtered:
                    st.warning("⚠️ 注意：当前网络连接白名单失败，列表可能包含已下架的币种。")
            else:
                st.success("✅ 没有发现异常。")
