from flask import Flask, jsonify, render_template_string
import requests
import uuid
import random
import string
import base64
import re
import os
import urllib3

# Tắt cảnh báo SSL để log sạch đẹp hơn
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==============================
# CẤU HÌNH
# ==============================
ANTPEAK_DOMAIN = "https://antpeak.com"
SSL_VERIFY = False
SUPPORTED_REGIONS = ["sg", "gb-lnd", "ru-spb", "nl", "fr", "us"]
RECAPTCHA_URL = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=6Ld_hskiAAAAADfg9HredZvZx8Z_C8FrNJ519Rc6&co=aHR0cHM6Ly9waXhhaS5hcnQ6NDQz&hl=vi&v=cLm1zuaUXPLFw7nzKiQTH1dX&size=invisible&anchor-ms=20000&execute-ms=15000&cb=hhxccska6jyp"
PIXAI_GRAPHQL = "https://api.pixai.art/graphql"
current_region="sg"
# HASH MỚI NHẤT
HASH_REGISTER = "6c06065e2b1a7dc7b6f8f2dfb0bee6dd2972c2f420f9a31ac6f3c7dd94990d7c"
HASH_DAILY_CHECK = "a0198760d10435733df0b4d7d42eb92512b33859f960cdb7bcbbe1089d108dca"
HASH_dailyClaimQuota = "c2170ae15c0c8821765a4a0538c5026c2f4a37fb7e4e2a7d518e23a1293013f9"
HASH_getMyQuota = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"

# ==============================
# 1. UTILS CƠ BẢN
# ==============================
def generate_fake_gmail():
    length = random.randint(6, 10)
    name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return f"{name}{random.randint(10,99)}@gmail.com"

def generate_password(length=14):
    raw = base64.urlsafe_b64encode(os.urandom(length * 2)).decode()
    return ''.join(c for c in raw if c.isalnum() or c in "!@#$%^&*")[:length]

def generate_browser_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))

# ==============================
# 2. XỬ LÝ PROXY (TỐI ƯU TỐC ĐỘ)
# ==============================
def get_fast_proxy():
    """Lấy proxy từ AntPeak"""
    udid = str(uuid.uuid4())
    launch_url = f"{ANTPEAK_DOMAIN}/api/launch/"
    launch_data = {
        "udid": udid, "appVersion": "2.1.7", "platform": "chrome",
        "platformVersion": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "timeZone": "Asia/Ho_Chi_Minh", "deviceName": "Chrome 135.0.0.0"
    }
    launch_headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

    try:
        r = requests.post(launch_url, json=launch_data, headers=launch_headers, timeout=10, verify=SSL_VERIFY)
        r.raise_for_status()
        token = r.json().get("data", {}).get("accessToken")
    except Exception as e:
        print(f"❌ [{current_region}] Lỗi lấy token AntPeak: {e}")
        return None

    if not token: return None

    list_headers = {
        "accept": "application/json", "authorization": f"Bearer {token}",
        "content-type": "application/json", "user-agent": "Mozilla/5.0",
        "origin": "chrome-extension://majdfhpaihoncoakbjgbdhglocklcgno",
    }
    list_payload = {"protocol": "https", "region": current_region, "type": 0}

    try:
        r = requests.post(f"{ANTPEAK_DOMAIN}/api/server/list/", json=list_payload, headers=list_headers, timeout=10, verify=SSL_VERIFY)
        servers = r.json().get("data", [])
        
        for s in servers:
            addr = s.get("addresses", [None])[0]
            user, pwd, port = s.get("username"), s.get("password"), s.get("port")
            if not (addr and user and pwd and port): continue
            
            proxy_url = f"https://{user}:{pwd}@{addr}:{port}"
            proxies = {"http": proxy_url, "https": proxy_url}
            
            # Test proxy nhanh
            try:
                requests.get("http://ip-api.com/json", proxies=proxies, timeout=3, verify=SSL_VERIFY)
                print(f"🌐 [{current_region}] Proxy Live: {addr}")
                return proxy_url
            except:
                continue
    except Exception as e:
        print(f"❌ [{current_region}] Lỗi lấy danh sách proxy: {e}")
    return None

# ==============================
# 3. LOGIC CHÍNH
# ==============================
def bypass_recaptcha(proxy_url):
    session = requests.Session()
    session.proxies.update({"http": proxy_url, "https": proxy_url})
    try:
        resp = session.get(RECAPTCHA_URL, timeout=10, verify=False)
        recaptcha_token = re.search(r'id="recaptcha-token" value="([^"]*)"', resp.text).group(1)
        k = re.search(r"&k=([^&]+)", RECAPTCHA_URL).group(1)
        co = re.search(r"&co=([^&]+)", RECAPTCHA_URL).group(1)
        v = re.search(r"&v=([^&]+)", RECAPTCHA_URL).group(1)

        post_url = f"https://www.google.com/recaptcha/api2/reload?k={k}"
        data = {"v": v, "reason": "q", "c": recaptcha_token, "k": k, "co": co, "hl": "en", "size": "invisible"}
        r = session.post(post_url, data=data, timeout=10, verify=False)
        m = re.search(r'\["rresp","([^"]+)"', r.text)
        return m.group(1) if m else None
    except:
        return None

def register_account():
    email = generate_fake_gmail()
    password = generate_password()
    browser_id = generate_browser_id()
    
    # Bước 1: Lấy proxy (Nhanh)
    proxy_url = get_fast_proxy()
    if not proxy_url:
        return {"status": "error", "message": "Không tìm thấy Proxy nào sống."}

    # Bước 2: Bypass Captcha
    captcha = bypass_recaptcha(proxy_url)
    if not captcha:
        return {"status": "error", "message": "Lỗi giải Captcha."}

    # Bước 3: Đăng ký
    session = requests.Session()
    session.proxies.update({"http": proxy_url, "https": proxy_url})
    session.verify = False

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "x-browser-id": browser_id,
        "Origin": "https://pixai.art"
    }

    payload = {
        "operationName": "register",
        "variables": {"input": {"email": email, "password": password, "recaptchaToken": captcha}},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_REGISTER}}
    }

    try:
        r = session.post(PIXAI_GRAPHQL, json=payload, headers=headers, timeout=15)
        resp_json = r.json()
        
        # Kiểm tra thành công
        if r.status_code == 200 and resp_json.get("data", {}).get("register"):
            token = session.cookies.get("user_token")
            
            # Bước 4: Kích hoạt Daily (Check nhanh 1 hash quan trọng nhất)
            try:
                auth_headers = {**headers, "Authorization": f"Bearer {token}"}
                session.post(PIXAI_GRAPHQL, 
                             json={"extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_dailyClaimQuota}}}, 
                             headers=auth_headers, timeout=3)
            except: pass
            
            return {
                "status": "success",
                "email": email,
                "password": password,
                "token": token
            }
        else:
            return {"status": "failed", "debug": resp_json}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==============================
# 4. FLASK ROUTE
# ==============================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PixAI Account Gen v2</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --accent: #3b82f6; --success: #22c55e; }
        body { background-color: var(--bg); color: var(--text); font-family: 'JetBrains Mono', monospace; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .container { width: 100%; max-width: 500px; padding: 20px; }
        .card { background-color: var(--card); border-radius: 16px; padding: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid #334155; }
        h1 { text-align: center; color: var(--accent); margin-bottom: 25px; font-size: 24px; text-transform: uppercase; letter-spacing: 2px; }
        
        .btn-gen {
            width: 100%; padding: 15px; font-size: 16px; font-weight: bold; color: white;
            background: linear-gradient(135deg, #3b82f6, #2563eb); border: none; border-radius: 10px; cursor: pointer;
            transition: transform 0.1s, box-shadow 0.2s;
        }
        .btn-gen:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(59, 130, 246, 0.4); }
        .btn-gen:active { transform: translateY(0); }
        .btn-gen:disabled { opacity: 0.7; cursor: not-allowed; background: #475569; }

        .loader { display: none; text-align: center; margin-top: 20px; }
        .spinner { width: 30px; height: 30px; border: 4px solid #334155; border-top: 4px solid var(--accent); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 10px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        .result-box { display: none; margin-top: 25px; background: #0f172a; padding: 15px; border-radius: 10px; border: 1px solid #334155; }
        .field { margin-bottom: 15px; }
        .label { font-size: 12px; color: #94a3b8; margin-bottom: 5px; display: block; }
        .input-group { display: flex; gap: 10px; }
        input { flex: 1; background: #1e293b; border: 1px solid #334155; padding: 10px; color: var(--success); border-radius: 6px; font-family: 'JetBrains Mono'; outline: none; }
        .btn-copy { background: #334155; color: white; border: none; padding: 0 15px; border-radius: 6px; cursor: pointer; font-weight: bold; }
        .btn-copy:hover { background: #475569; }

        .status { margin-top: 15px; text-align: center; font-size: 14px; color: #94a3b8; height: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>PixAI Generator</h1>
            <button class="btn-gen" onclick="createAccount()" id="btnGen">⚡ TẠO TÀI KHOẢN MỚI</button>
            
            <div class="loader" id="loader">
                <div class="spinner"></div>
                <div class="status" id="statusText">Đang tìm Proxy & Giải Captcha...</div>
            </div>

            <div class="result-box" id="resultBox">
                <div class="field">
                    <span class="label">EMAIL</span>
                    <div class="input-group">
                        <input type="text" id="email" readonly>
                        <button class="btn-copy" onclick="copyTo('email')">COPY</button>
                    </div>
                </div>
                <div class="field">
                    <span class="label">PASSWORD</span>
                    <div class="input-group">
                        <input type="text" id="pass" readonly>
                        <button class="btn-copy" onclick="copyTo('pass')">COPY</button>
                    </div>
                </div>
                <div class="field">
                    <span class="label">TOKEN (Đã Active Daily)</span>
                    <div class="input-group">
                        <input type="text" id="token" readonly>
                        <button class="btn-copy" onclick="copyTo('token')">COPY</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function createAccount() {
            const btn = document.getElementById('btnGen');
            const loader = document.getElementById('loader');
            const resultBox = document.getElementById('resultBox');
            const statusText = document.getElementById('statusText');

            // Reset UI
            btn.disabled = true;
            btn.innerText = "⏳ ĐANG XỬ LÝ...";
            resultBox.style.display = 'none';
            loader.style.display = 'block';
            statusText.innerText = "Đang kết nối AntPeak & Google...";

            try {
                const response = await fetch('/api/create');
                const data = await response.json();

                if (data.status === 'success') {
                    document.getElementById('email').value = data.email;
                    document.getElementById('pass').value = data.password;
                    document.getElementById('token').value = data.token;
                    
                    statusText.innerText = "✅ Thành công!";
                    resultBox.style.display = 'block';
                } else {
                    alert('Lỗi: ' + data.message);
                    statusText.innerText = "❌ Thất bại: " + data.message;
                }
            } catch (e) {
                alert('Lỗi kết nối server!');
                statusText.innerText = "❌ Lỗi kết nối!";
            } finally {
                btn.disabled = false;
                btn.innerText = "⚡ TẠO TÀI KHOẢN MỚI";
                loader.style.display = 'none';
            }
        }

        function copyTo(id) {
            const el = document.getElementById(id);
            el.select();
            navigator.clipboard.writeText(el.value);
            const btn = el.nextElementSibling;
            const originalText = btn.innerText;
            btn.innerText = "OK!";
            setTimeout(() => btn.innerText = originalText, 1000);
        }
    </script>
</body>
</html>
"""

# ==============================
# 4. ROUTE FLASK
# ==============================
@app.route('/')
def home():
    # Render giao diện HTML xịn xò
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/create')
def create_api():
    # API xử lý ngầm
    return jsonify(register_account())
