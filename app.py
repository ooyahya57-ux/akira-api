from flask import Flask, request, jsonify
import requests
import json
import threading
import time
from byte import Encrypt_ID, encrypt_api
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

API_KEY = "PSX-AKIRA"
MAX_WORKERS = 107

# قاموس لتخزين جلسات السبام لكل هدف
# المفتاح = f"{uid}:{region}"  القيمة = {"active": True, "thread": None}
spam_sessions = {}
sessions_lock = threading.Lock()

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

def send_friend_request(target_uid, jwt_token):
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
        
        if response.status_code == 200:
            return True
        else:
            return False
                
    except Exception as e:
        app.logger.error(f"خطأ في الإرسال: {e}")
        return False

def continuous_spam(target_uid, region, session_key):
    """دالة السبام المستمر لهدف معين - تشتغل حتى يتم إيقاف هذا الهدف فقط"""
    
    # تحميل الحسابات
    accounts = load_tokens(region)
    if not accounts:
        app.logger.error(f"❌ لا توجد حسابات في ملف {region} للهدف {target_uid}")
        with sessions_lock:
            if session_key in spam_sessions:
                del spam_sessions[session_key]
        return
    
    # تجهيز قائمة التوكنات
    tokens_list = []
    app.logger.info(f"🔄 جاري تجهيز التوكنات للهدف {target_uid}...")
    
    for account in accounts:
        uid = account.get("uid", "")
        password = account.get("password", "")
        if uid and password:
            jwt_token = get_jwt_from_api(uid, password)
            if jwt_token:
                tokens_list.append(jwt_token)
                app.logger.info(f"✓ تم تجهيز توكن {uid[:5]}")
    
    if not tokens_list:
        app.logger.error(f"❌ لا يوجد أي توكن صالح للهدف {target_uid}")
        with sessions_lock:
            if session_key in spam_sessions:
                del spam_sessions[session_key]
        return
    
    app.logger.info(f"✅ تم تجهيز {len(tokens_list)} توكن للهدف {target_uid}")
    app.logger.info(f"🚀 بدأ السبام المستمر على الهدف: {target_uid}")
    
    cycle = 0
    total_sent = 0
    
    while True:
        # التحقق إذا كان هذا الهدف لا يزال نشطاً
        with sessions_lock:
            if session_key not in spam_sessions or not spam_sessions[session_key]["active"]:
                app.logger.info(f"🛑 تم إيقاف السبام للهدف {target_uid}")
                break
        
        cycle += 1
        cycle_sent = 0
        
        # إرسال الطلبات من جميع التوكنات
        for i, jwt_token in enumerate(tokens_list):
            with sessions_lock:
                if session_key not in spam_sessions or not spam_sessions[session_key]["active"]:
                    break
            
            success = send_friend_request(target_uid, jwt_token)
            if success:
                cycle_sent += 1
                total_sent += 1
                app.logger.info(f"✓ [{i+1}/{len(tokens_list)}] تم الإرسال إلى {target_uid}")
        
        app.logger.info(f"📊 الهدف {target_uid} - الدورة {cycle}: أرسل {cycle_sent} طلب | المجموع: {total_sent}")
        
        # انتظار بين الدورات
        with sessions_lock:
            if session_key in spam_sessions and spam_sessions[session_key]["active"]:
                time.sleep(1)
    
    # تنظيف الجلسة بعد الانتهاء
    with sessions_lock:
        if session_key in spam_sessions:
            del spam_sessions[session_key]
    
    app.logger.info(f"🏁 انتهى السبام للهدف {target_uid}. إجمالي المرسل: {total_sent}")

@app.route("/send_requests", methods=["GET"])
def send_requests():
    uid = request.args.get("uid")
    region = request.args.get("region")
    api_key = request.args.get("key")
    
    if not api_key or api_key != API_KEY:
        return jsonify({"error": "مفتاح API غير صحيح"}), 403
    
    if not uid or not region:
        return jsonify({"error": "يجب إدخال uid و region"}), 400
    
    session_key = f"{uid}:{region.upper()}"
    
    with sessions_lock:
        # إذا كان هناك سبام نشط لهذا الهدف، لا نبدأ سبام جديد
        if session_key in spam_sessions and spam_sessions[session_key]["active"]:
            return jsonify({
                "error": f"يوجد سبام مستمر بالفعل للهدف {uid}",
                "stop": f"استخدم /stop_spam?uid={uid}&region={region}&key={API_KEY} لإيقافه"
            }), 409
        
        # بدء سبام جديد لهذا الهدف
        spam_sessions[session_key] = {"active": True, "thread": None}
    
    # تشغيل السبام المستمر
    spam_thread = threading.Thread(target=continuous_spam, args=(uid, region.upper(), session_key), daemon=True)
    
    with sessions_lock:
        spam_sessions[session_key]["thread"] = spam_thread
    
    spam_thread.start()
    
    return jsonify({
        "status": "started",
        "message": f"✅ بدأ السبام المستمر إلى {uid} في منطقة {region.upper()}",
        "target_uid": uid,
        "region": region.upper(),
        "note": "السكربت سيرسل طلبات بشكل مستمر بدون توقف",
        "stop": f"http://localhost:5000/stop_spam?uid={uid}&region={region.upper()}&key={API_KEY}"
    })

@app.route("/stop_spam", methods=["GET"])
def stop_spam():
    """إيقاف سبام هدف معين فقط - مثل: /stop_spam?uid=12345678&region=ME&key=PSX-AKIRA"""
    uid = request.args.get("uid")
    region = request.args.get("region")
    api_key = request.args.get("key")
    
    if not api_key or api_key != API_KEY:
        return jsonify({"error": "مفتاح API غير صحيح"}), 403
    
    if not uid or not region:
        return jsonify({
            "error": "يجب إدخال uid و region",
            "example": "/stop_spam?uid=12345678&region=ME&key=PSX-AKIRA"
        }), 400
    
    session_key = f"{uid}:{region.upper()}"
    
    with sessions_lock:
        if session_key not in spam_sessions:
            return jsonify({
                "status": "not_found",
                "message": f"⚠️ لا يوجد سبام نشط للهدف {uid} في منطقة {region.upper()}"
            })
        
        if not spam_sessions[session_key]["active"]:
            return jsonify({
                "status": "already_stopped",
                "message": f"⚠️ السبام للهدف {uid} متوقف بالفعل"
            })
        
        # إيقاف السبام لهذا الهدف فقط
        spam_sessions[session_key]["active"] = False
    
    return jsonify({
        "status": "stopped",
        "message": f"🛑 تم إيقاف السبام للهدف {uid} في منطقة {region.upper()}",
        "target_uid": uid,
        "region": region.upper()
    })

@app.route("/spam_status", methods=["GET"])
def spam_status():
    """التحقق من حالة السبام (لكل الأهداف أو هدف معين)"""
    uid = request.args.get("uid")
    region = request.args.get("region")
    
    if uid and region:
        session_key = f"{uid}:{region.upper()}"
        with sessions_lock:
            if session_key in spam_sessions and spam_sessions[session_key]["active"]:
                return jsonify({
                    "target": uid,
                    "region": region.upper(),
                    "is_spamming": True,
                    "message": "جاري الإرسال..."
                })
            else:
                return jsonify({
                    "target": uid,
                    "region": region.upper(),
                    "is_spamming": False,
                    "message": "متوقف أو غير موجود"
                })
    
    # إذا لم يحدد هدف، عرض جميع الجلسات النشطة
    with sessions_lock:
        active_sessions = []
        for key, session in spam_sessions.items():
            if session["active"]:
                uid_part, region_part = key.split(":", 1)
                active_sessions.append({"uid": uid_part, "region": region_part})
    
    return jsonify({
        "active_spams": active_sessions,
        "count": len(active_sessions),
        "message": "جاري الإرسال..." if active_sessions else "لا يوجد سبام نشط"
    })

@app.route("/")
def index():
    return jsonify({
        "service": "Free Fire Friend Request Sender - Continuous Spam",
        "endpoints": {
            "/send_requests": "?uid=TARGET_UID&region=REGION&key=PSX-AKIRA - لبدء السبام المستمر",
            "/stop_spam": "?uid=TARGET_UID&region=REGION&key=PSX-AKIRA - لإيقاف سبام هدف معين فقط",
            "/spam_status": "?uid=TARGET_UID&region=REGION - لمعرفة حالة هدف (اختياري)"
        },
        "regions": ["ME", "IND", "BR", "US", "SAC", "NA", "EU", "VN", "BD"],
        "example_stop": f"http://localhost:5000/stop_spam?uid=12345678&region=ME&key={API_KEY}"
    })

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
