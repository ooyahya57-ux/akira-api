from flask import Flask, request, jsonify
import requests
import json
import threading
from byte import Encrypt_ID, encrypt_api
from concurrent.futures import ThreadPoolExecutor
import time

app = Flask(__name__)

API_KEY = "CTX-TEAM"
MAX_WORKERS = 107

def load_tokens(region):
    try:
        region = region.upper()
        region_files = {
            "IND": "spam_ind.json",
            "BR": "spam_br.json",
            "US": "spam_br.json",
            "SAC": "spam_br.json",
            "NA": "spam_br.json",
            "EU": "spam_eu.json",
            "VN": "spam_vn.json",
            "ME": "spam_me.json",
            "BD": "spam_bd.json"
        }
        
        file_path = region_files.get(region, "spam_me.json")
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
    
        return data

    except Exception as e:
        app.logger.error(f"Error loading {file_path}: {e}")
        return None

def get_jwt_from_api(uid, password):
    try:
        url = f"http://cloud-serv.mooo.com:3012/getjwt?uid={uid}&pw={password}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            token_keys = ["token", "jwt", "access_token", "Token", "JWT", "accessToken"]
            for key in token_keys:
                if key in data:
                    return str(data[key])
        return None
        
    except Exception as e:
        app.logger.error(f"JWT API error for {uid[:5]}: {e}")
        return None

def send_friend_request(target_uid, jwt_token, region, results, lock):
    try:
        encrypted_id = Encrypt_ID(target_uid)
        payload = f"08a7c4839f1e10{encrypted_id}1801"
        encrypted_payload = encrypt_api(payload)
        
        url = "https://clientbp.ggpolarbear.com/RequestAddingFriend"
        
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "X-Unity-Version": "2018.4.11f1",
            "X-GA": "v1 1",
            "ReleaseVersion": "OB53",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-N975F Build/PI)",
            "Connection": "close",
            "Accept-Encoding": "gzip, deflate, br"
        }

        response = requests.post(url, headers=headers, data=bytes.fromhex(encrypted_payload), timeout=5)
        
        with lock:
            if response.status_code == 200:
                results["success"] += 1
                app.logger.info(f"تم إرسال طلب من حساب إلى {target_uid[:5]}")
            else:
                results["failed"] += 1
                
    except Exception as e:
        with lock:
            results["failed"] += 1
        app.logger.error(f"خطأ في الإرسال: {e}")
 
def process_account(account, target_uid, region, results, lock):
    try:
        uid = account.get("uid", "")
        password = account.get("password", "")
        
        if not uid or not password:
            with lock:
                results["failed"] += 1
            return
        
        
        jwt_token = get_jwt_from_api(uid, password)
        
        if not jwt_token:
            with lock:
                results["failed"] += 1
            app.logger.warning(f"فشل تحويل {uid[:5]} إلى JWT")
            return
        
        send_friend_request(target_uid, jwt_token, region, results, lock)
        
    except Exception as e:
        with lock:
            results["failed"] += 1
        app.logger.error(f"خطأ في معالجة الحساب: {e}")


@app.route("/send_requests", methods=["GET"])
def send_requests():
    uid = request.args.get("uid")
    region = request.args.get("region")
    api_key = request.args.get("key")
    max_accounts = request.args.get("max", default=110, type=int)
    
    if not api_key or api_key != API_KEY:
        return jsonify({"error": "مفتاح API غير صحيح"}), 403
    
    if not uid or not region:
        return jsonify({"error": "يجب إدخال uid و region"}), 400
    

    accounts = load_tokens(region)
    if not accounts:
        return jsonify({"error": f"لا توجد حسابات في ملف {region}"}), 500
    
    accounts_to_process = accounts[:max_accounts]
    
    results = {"success": 0, "failed": 0}
    lock = threading.Lock()
    
    app.logger.info(f"بدء معالجة {len(accounts_to_process)} حساب لـ {uid[:5]}...")
    
  
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        
        for account in accounts_to_process:
            future = executor.submit(
                process_account,
                account,
                uid,
                region,
                results,
                lock
            )
            futures.append(future)
        

        app.logger.info(f"تم بدء {len(futures)} مهمة معالجة")
    
    # ارجع النتائج الحالية
    return jsonify({
        "region": region.upper(),
        "target_uid": uid,
        "total_accounts": len(accounts_to_process),
        "started": True,
        "message": "jwt done"
    })


@app.route("/")
def index():
    return jsonify({
        "service": "Free Fire Friend Request Sender",
        "endpoint": "/send_requests?uid=TARGET_UID&region=REGION&key=PSX-AKIRA",
        "regions": ["ME", "IND", "BR", "US", "SAC", "NA", "EU", "VN", "BD"]
    })

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)