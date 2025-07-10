import requests
import json

# --- 配置 ---
# 插件 API 的地址，请确保与你的插件配置一致
BASE_URL = "https://forward.wanghu.rcfortress.site:8443/"
WEBHOOK_PATH = "forward"  # 对应 api_webhook_path
TOKEN = "114514"  # 对应 api_preshared_token，如果未设置则留空

# 要发送的消息
MESSAGE_TO_SEND = "这是一条来自测试客户端的消息！"

def test_inbound_forward():
    """
    测试入站消息转发功能。
    它会向插件的 API 发送一个 POST 请求。
    """
    url = f"{BASE_URL}/{WEBHOOK_PATH.strip('/')}"
    
    headers = {
        "Content-Type": "application/json"
    }
    if TOKEN:
        headers["X-Auth-Token"] = TOKEN
        
    payload = {
        "message": MESSAGE_TO_SEND
    }
    
    print(f"发送 POST 请求到: {url}")
    print(f"Headers: {headers}")
    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        print(f"\n--- 响应 ---")
        print(f"状态码: {response.status_code}")
        try:
            print(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        except json.JSONDecodeError:
            print(f"响应内容 (非 JSON): {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"\n--- 错误 ---")
        print(f"请求失败: {e}")

if __name__ == "__main__":
    test_inbound_forward()