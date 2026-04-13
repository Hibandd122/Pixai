# api.py
# -*- coding: utf-8 -*-
"""
Pixai Account Generator API
Endpoint: POST /api/create  (cũng hỗ trợ GET để dễ test)
Trả về JSON: { "status": "...", "email": "...", "password": "...", "token": "..." }
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import random
import string
import base64
import re
import os
import time
import uuid
import urllib3

# Tắt cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================
# CONSTANTS
# ==============================
CONSTANTS = {
    "RECAPTCHA_URL": (
        "https://www.google.com/recaptcha/api2/anchor"
        "?ar=1&k=6Ld_hskiAAAAADfg9HredZvZx8Z_C8FrNJ519Rc6"
        "&co=aHR0cHM6Ly9waXhhaS5hcnQ6NDQz"
        "&hl=vi&v=cLm1zuaUXPLFw7nzKiQTH1dX"
        "&size=invisible&anchor-ms=20000&execute-ms=15000&cb=hhxccska6jyp"
    ),
    "PIXAI_GRAPHQL": "https://api.pixai.art/graphql",
    "HASH_REGISTER": "adc0954063d07fe53bdf6d5e0cb471d0196f730c0e55fec5d5b631d5411f7500",
    "HASH_DAILY": "c2170ae15c0c8821765a4a0538c5026c2f4a37fb7e4e2a7d518e23a1293013f9",
    "REQ_TIMEOUT": 18,
    "MAX_RETRIES": 2,
    "ANTPEAK_DOMAIN": "https://antpeak.com",
    "SUPPORTED_REGIONS": ["sg", "gb-lnd", "ru-spb", "nl", "fr", "us"],
    "SSL_VERIFY": False,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Cache proxy đơn giản
_PROXY_CACHE = {"proxy": None, "timestamp": 0}
PROXY_CACHE_TTL = 30  # giây

# ==============================
# LOGGER ĐƠN GIẢN
# ==============================
class SimpleLogger:
    def info(self, msg):
        print(f"[INFO] {msg}")
    def warning(self, msg):
        print(f"[WARN] {msg}")
    def error(self, msg):
        print(f"[ERROR] {msg}")

logger = SimpleLogger()

# ==============================
# UTILS (PROXY & HELPER)
# ==============================
def get_working_proxy(region="sg"):
    """Lấy proxy HTTP/HTTPS từ AntPeak và test nhanh"""
    # Kiểm tra cache còn hạn
    if _PROXY_CACHE["proxy"] and (time.time() - _PROXY_CACHE["timestamp"]) < PROXY_CACHE_TTL:
        logger.info(f"Reusing cached proxy: {_PROXY_CACHE['proxy']}")
        return _PROXY_CACHE["proxy"]

    # Lấy token AntPeak
    udid = str(uuid.uuid4())
    launch_url = f"{CONSTANTS['ANTPEAK_DOMAIN']}/api/launch/"
    launch_data = {
        "udid": udid, "appVersion": "2.1.7", "platform": "chrome",
        "platformVersion": random.choice(USER_AGENTS),
        "timeZone": "Asia/Ho_Chi_Minh", "deviceName": "Chrome 135.0.0.0"
    }
    try:
        r = requests.post(launch_url, json=launch_data,
                          headers={"Content-Type": "application/json", "User-Agent": random.choice(USER_AGENTS)},
                          timeout=10, verify=CONSTANTS["SSL_VERIFY"])
        r.raise_for_status()
        token = r.json().get("data", {}).get("accessToken")
        if not token:
            logger.error("Không lấy được token AntPeak")
            return None
    except Exception as e:
        logger.error(f"Lỗi lấy token AntPeak: {e}")
        return None

    # Lấy danh sách server proxy
    list_headers = {
        "accept": "application/json", "authorization": f"Bearer {token}",
        "content-type": "application/json", "user-agent": random.choice(USER_AGENTS),
        "origin": "chrome-extension://majdfhpaihoncoakbjgbdhglocklcgno",
    }
    list_payload = {"protocol": "https", "region": region, "type": 0}
    try:
        r = requests.post(f"{CONSTANTS['ANTPEAK_DOMAIN']}/api/server/list/",
                          json=list_payload, headers=list_headers,
                          timeout=10, verify=CONSTANTS["SSL_VERIFY"])
        servers = r.json().get("data", [])
        for s in servers:
            addr = s.get("addresses", [None])[0]
            user, pwd, port = s.get("username"), s.get("password"), s.get("port")
            if not (addr and user and pwd and port):
                continue
            proxy_url = f"https://{user}:{pwd}@{addr}:{port}"
            proxies = {"http": proxy_url, "https": proxy_url}
            # Test proxy nhanh
            try:
                test_resp = requests.get("http://ip-api.com/json", proxies=proxies,
                                         timeout=3, verify=CONSTANTS["SSL_VERIFY"])
                if test_resp.status_code == 200:
                    logger.info(f"Proxy hoạt động: {addr}")
                    _PROXY_CACHE["proxy"] = proxy_url
                    _PROXY_CACHE["timestamp"] = time.time()
                    return proxy_url
            except:
                continue
    except Exception as e:
        logger.error(f"Lỗi lấy danh sách proxy: {e}")
    return None

# ==============================
# PIXAI GENERATOR CLASS
# ==============================
class PixAiGenerator:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = CONSTANTS["SSL_VERIFY"]
        self.proxy_url = None
        self.user_agent = random.choice(USER_AGENTS)

    def _generate_fake_data(self):
        prefixes = ['user', 'dev', 'gen', 'art', 'px', 'neo', 'ai']
        prefix = random.choice(prefixes)
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(5, 9)))
        domains = ['gmail.com', 'outlook.com', 'hotmail.com', 'proton.me']
        email = f"{prefix}{suffix}{random.randint(10, 999)}@{random.choice(domains)}"

        raw = base64.urlsafe_b64encode(os.urandom(28)).decode()
        password = ''.join(c for c in raw if c.isalnum() or c in "!@#$%^&*")[:14]
        if len(password) < 8:
            password += ''.join(random.choices(string.ascii_letters + string.digits, k=8 - len(password)))

        browser_id = ''.join(random.choices('abcdef' + string.digits, k=32))
        return email, password, browser_id

    def _build_headers(self, browser_id, auth_token=None):
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": self.user_agent,
            "x-browser-id": browser_id,
            "Origin": "https://pixai.art",
            "Referer": "https://pixai.art/",
            "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "Connection": "keep-alive",
        }
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    def _bypass_recaptcha(self):
        for attempt in range(CONSTANTS['MAX_RETRIES']):
            try:
                resp = self.session.get(
                    CONSTANTS['RECAPTCHA_URL'],
                    timeout=CONSTANTS['REQ_TIMEOUT']
                )
                token_match = re.search(r'id="recaptcha-token" value="([^"]*)"', resp.text)
                if not token_match:
                    logger.warning(f"Không tìm thấy recaptcha token (lần {attempt+1})")
                    time.sleep(1)
                    continue

                recaptcha_token = token_match.group(1)
                params = dict(x.split('=') for x in CONSTANTS['RECAPTCHA_URL'].split('?')[1].split('&'))
                post_url = f"https://www.google.com/recaptcha/api2/reload?k={params['k']}"
                data = {
                    "v": params['v'], "reason": "q", "c": recaptcha_token,
                    "k": params['k'], "co": params['co'], "hl": "en", "size": "invisible"
                }
                r = self.session.post(post_url, data=data, timeout=CONSTANTS['REQ_TIMEOUT'])
                m = re.search(r'\["rresp","([^"]+)"', r.text)
                if m:
                    return m.group(1)
                logger.warning(f"Parse captcha thất bại (lần {attempt+1})")
                time.sleep(1.5)
            except Exception as e:
                logger.error(f"Lỗi bypass captcha (lần {attempt+1}): {e}")
                if attempt < CONSTANTS['MAX_RETRIES'] - 1:
                    time.sleep(2)
        return None

    def _claim_daily(self, headers, browser_id, token):
        try:
            auth_headers = self._build_headers(browser_id, auth_token=token)
            daily_payload = {
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": CONSTANTS['HASH_DAILY']
                    }
                }
            }
            resp = self.session.post(
                CONSTANTS['PIXAI_GRAPHQL'],
                json=daily_payload,
                headers=auth_headers,
                timeout=5
            )
            if resp.status_code == 200:
                logger.info("Đã claim daily credits thành công")
            else:
                logger.warning(f"Daily claim trả về mã {resp.status_code}")
        except Exception as e:
            logger.warning(f"Bỏ qua daily claim: {e}")

    def _extract_error(self, resp_json, status_code):
        if isinstance(resp_json, dict):
            if resp_json.get('errors'):
                return resp_json['errors'][0].get('message', 'Lỗi API không xác định')
            if resp_json.get('message'):
                return resp_json['message']
        return f"HTTP {status_code}"

    def create_account(self):
        self.proxy_url = get_working_proxy()
        if not self.proxy_url:
            return {"status": "error", "message": "Không có proxy hoạt động"}

        self.session.proxies.update({"http": self.proxy_url, "https": self.proxy_url})
        logger.info(f"Sử dụng proxy: {self.proxy_url}")

        captcha = self._bypass_recaptcha()
        if not captcha:
            _PROXY_CACHE["proxy"] = None  # Xóa cache proxy lỗi
            return {"status": "error", "message": "Bypass captcha thất bại"}

        email, password, browser_id = self._generate_fake_data()
        logger.info(f"Đang đăng ký: {email}")

        headers = self._build_headers(browser_id)
        payload = {
            "operationName": "register",
            "variables": {
                "input": {
                    "email": email,
                    "password": password,
                    "recaptchaToken": captcha
                }
            },
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": CONSTANTS['HASH_REGISTER']
                }
            }
        }

        for attempt in range(CONSTANTS['MAX_RETRIES']):
            try:
                r = self.session.post(
                    CONSTANTS['PIXAI_GRAPHQL'],
                    json=payload,
                    headers=headers,
                    timeout=CONSTANTS['REQ_TIMEOUT']
                )
                logger.info(f"Phản hồi đăng ký: {r.status_code} (lần {attempt+1})")
                try:
                    resp_json = r.json()
                except:
                    logger.error(f"JSON không hợp lệ: {r.text[:300]}")
                    if attempt < CONSTANTS['MAX_RETRIES'] - 1:
                        time.sleep(2)
                        continue
                    return {"status": "error", "message": "Phản hồi server không hợp lệ"}

                if r.status_code == 200 and resp_json.get("data", {}).get("register"):
                    token = self.session.cookies.get("user_token")
                    logger.info(f"Tạo tài khoản thành công: {email}")
                    self._claim_daily(headers, browser_id, token)
                    return {
                        "status": "success",
                        "email": email,
                        "password": password,
                        "token": token
                    }

                err_msg = self._extract_error(resp_json, r.status_code)
                logger.error(f"Đăng ký thất bại: {err_msg}")
                if "too many" in err_msg.lower() or r.status_code == 429:
                    return {"status": "failed", "message": err_msg}
                if attempt < CONSTANTS['MAX_RETRIES'] - 1:
                    logger.info("Thử lại sau 3 giây...")
                    time.sleep(3)

            except requests.exceptions.Timeout:
                logger.error(f"Timeout (lần {attempt+1})")
                if attempt < CONSTANTS['MAX_RETRIES'] - 1:
                    time.sleep(2)
                    continue
                return {"status": "error", "message": "Request timeout"}
            except requests.exceptions.ProxyError as e:
                logger.error(f"Lỗi proxy: {e}")
                _PROXY_CACHE["proxy"] = None
                return {"status": "error", "message": "Kết nối proxy thất bại"}
            except requests.exceptions.RequestException as e:
                logger.error(f"Lỗi request: {e}")
                return {"status": "error", "message": str(e)}
            except Exception as e:
                logger.error(f"Lỗi không xác định: {e}")
                return {"status": "error", "message": str(e)}

        return {"status": "failed", "message": "Đã hết số lần thử"}

# ==============================
# FLASK APP & ROUTES
# ==============================
app = Flask(__name__)
CORS(app)  # Cho phép mọi origin truy cập API

@app.route('/api/create', methods=['GET', 'POST'])
def create_account_api():
    """API tạo tài khoản PixAI, trả về JSON"""
    logger.info("Nhận yêu cầu tạo tài khoản")
    generator = PixAiGenerator()
    result = generator.create_account()
    logger.info(f"Kết quả: {result.get('status')} - {result.get('email', 'N/A')}")
    return jsonify(result)

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint kiểm tra trạng thái API"""
    return jsonify({"status": "ok", "timestamp": time.time()})
