import os
import json
import time
import threading
import datetime
import requests
import random
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ===== CONFIG =====
WEATHER_API_KEYS = [
    "78c2f2db26e14bcd81c70611251710",
]

TELEGRAM_TOKEN = "8230075534:AAHI6KIlF49HiKsukOswY79lsmLyv9bl3dY"
CHAT_ID = "6645915205"

# DEFAULT LOCATION BANGIL, PASURUAN
DEFAULT_LAT = -7.5995
DEFAULT_LON = 112.8186
DEFAULT_LOCATION = "Bangil, Pasuruan"

# JADWAL PENYIRAMAN
WATERING_SCHEDULES = [
    {"hour": 7, "minute": 0},
    {"hour": 13, "minute": 30}
]

# 8 JENIS TANAMAN
PLANT_TYPES = {
    "cabe": {"name": "Cabe Rawit", "harvest_days": 90},
    "tomat": {"name": "Tomat", "harvest_days": 80},
    "terong": {"name": "Terong", "harvest_days": 85},
    "kangkung": {"name": "Kangkung", "harvest_days": 30},
    "bayam": {"name": "Bayam", "harvest_days": 25},
    "sawi": {"name": "Sawi", "harvest_days": 40},
    "wortel": {"name": "Wortel", "harvest_days": 70},
    "kol": {"name": "Kol/Kubis", "harvest_days": 75}
}

STATE_FILE = "farm_state.json"
LOCK = threading.Lock()

# ===== HELPERS =====
def load_state():
    try:
        if not os.path.exists(STATE_FILE):
            return create_default_state()
        
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading state: {e}")
        return create_default_state()

def create_default_state():
    return {
        "location_name": DEFAULT_LOCATION,
        "lat": DEFAULT_LAT,
        "lon": DEFAULT_LON,
        "last_weather_update": None,
        "plants": [],
        "harvest_history": []
    }

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving state: {e}")
        return False

def send_telegram_message(text, chat_id=None):
    if not TELEGRAM_TOKEN:
        return False
    
    if chat_id is None:
        chat_id = CHAT_ID
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error kirim Telegram: {e}")
        return False

# ===== WEATHER FUNCTIONS =====
def fetch_weather_openmeteo(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,apparent_temperature&timezone=Asia/Jakarta"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if "error" in data:
            return {"error": data["reason"]}
            
        current = data["current"]
        
        weather_codes = {
            0: "Cerah", 1: "Cerah", 2: "Cerah Berawan", 
            3: "Berawan", 45: "Kabut", 48: "Kabut",
            51: "Hujan Ringan", 53: "Hujan Sedang", 55: "Hujan Lebat",
            61: "Hujan Ringan", 63: "Hujan Sedang", 65: "Hujan Lebat"
        }
        
        return {
            "source": "Open-Meteo",
            "location": "Bangil Area",
            "temp_c": round(current["temperature_2m"]),
            "humidity": round(current["relative_humidity_2m"]),
            "wind_kph": round(current["wind_speed_10m"] * 3.6),
            "condition": weather_codes.get(current["weather_code"], "Berawan"),
            "feelslike_c": round(current["apparent_temperature"])
        }
    except Exception as e:
        return {"error": str(e)}

def fetch_weather(lat=None, lon=None):
    try:
        with LOCK:
            state = load_state()
        
        if lat is None or lon is None:
            lat = state.get("lat", DEFAULT_LAT)
            lon = state.get("lon", DEFAULT_LON)
        
        # Coba Open-Meteo dulu (FREE)
        result = fetch_weather_openmeteo(lat, lon)
        if "error" not in result:
            return result
        
        # Fallback realistic Bangil
        bangil_conditions = ["Cerah", "Cerah Berawan", "Berawan", "Hujan Ringan"]
        return {
            "source": "System (Bangil)",
            "location": "Bangil, Pasuruan",
            "temp_c": random.randint(28, 34),
            "humidity": random.randint(70, 85),
            "condition": random.choice(bangil_conditions),
            "wind_kph": random.randint(5, 15),
            "feelslike_c": random.randint(30, 36)
        }
    except Exception as e:
        return {"error": str(e)}

def format_weather_message(weather_data, time_of_day="Pagi"):
    try:
        location = weather_data.get('location', 'Bangil')
        temp = weather_data.get('temp_c', 0)
        feels_like = weather_data.get('feelslike_c', temp)
        humidity = weather_data.get('humidity', 0)
        condition = weather_data.get('condition', 'Cerah')
        wind = weather_data.get('wind_kph', 0)
        
        if time_of_day == "Pagi":
            emoji = "🌅"
            activity = "• Periksa kondisi tanaman\n• Persiapan penyiraman\n• Cek hama dan penyakit"
        else:
            emoji = "☀"  
            activity = "• Pantau pertumbuhan tanaman\n• Evaluasi kebutuhan air\n• Catat perkembangan"
        
        return f"""{emoji} LAPORAN CUACA {time_of_day.upper()} {emoji}

📍 Lokasi: {location}
🌡 Suhu: {temp}°C
🌡 Terasa Seperti: {feels_like}°C
💧 Kelembaban: {humidity}%
🌬 Angin: {wind} km/jam  
☁ Kondisi: {condition}

📋 Kegiatan {time_of_day}:
{activity}

Tetap semangat bertani! 🌾"""
    except Exception:
        return f"Laporan cuaca {time_of_day} untuk Bangil"

# ===== PLANT MANAGEMENT =====
def add_plant(plant_type, quantity, date_planted, target_harvest):
    try:
        with LOCK:
            state = load_state()
            
            plant_info = PLANT_TYPES.get(plant_type, {
                "name": plant_type.capitalize(),
                "harvest_days": 60
            })
            
            harvest_date = (datetime.datetime.strptime(date_planted, "%Y-%m-%d") + 
                          datetime.timedelta(days=plant_info["harvest_days"])).strftime("%Y-%m-%d")
            
            new_plant = {
                "id": len(state["plants"]) + 1,
                "type": plant_type,
                "name": plant_info["name"],
                "quantity": int(quantity),
                "date_planted": date_planted,
                "target_harvest": target_harvest,
                "harvest_date": harvest_date,
                "status": "growing",
                "notified": False
            }
            
            state["plants"].append(new_plant)
            save_state(state)
            
            message = f"""🌱 TANAMAN BARU DITANAM 🌱

Jenis: {new_plant['name']}
Jumlah: {quantity} tanaman
Tanggal Tanam: {date_planted}
Target Panen: {target_harvest}
Perkiraan Panen: {harvest_date}

Selamat menanam! 🌿"""
            
            send_telegram_message(message)
            return True
            
    except Exception as e:
        print(f"Error adding plant: {e}")
        return False

def harvest_plant(plant_id, harvest_amount):
    try:
        with LOCK:
            state = load_state()
            
            for plant in state["plants"]:
                if plant["id"] == plant_id and plant["status"] == "growing":
                    plant["status"] = "harvested"
                    plant["actual_harvest"] = datetime.date.today().isoformat()
                    plant["harvest_amount"] = harvest_amount
                    
                    # Calculate difference
                    try:
                        target_num = float(''.join(filter(str.isdigit, plant["target_harvest"])))
                        actual_num = float(harvest_amount)
                        difference = actual_num - target_num
                        diff_text = f"{difference:+g}" if difference != 0 else "0"
                    except:
                        diff_text = "N/A"
                    
                    save_state(state)
                    
                    message = f"""🌾 HASIL PANEN 🌾

Jenis: {plant['name']}
Tanggal Tanam: {plant['date_planted']}
Target: {plant['target_harvest']}
Hasil Aktual: {harvest_amount}
Selisih: {diff_text}

Selamat atas panennya! 🎉"""
                    
                    send_telegram_message(message)
                    return True
                    
        return False
    except Exception as e:
        print(f"Error harvesting plant: {e}")
        return False

def check_harvest_schedule():
    try:
        with LOCK:
            state = load_state()
            today = datetime.date.today().isoformat()
            
            for plant in state["plants"]:
                if (plant["status"] == "growing" and 
                    plant["harvest_date"] == today and 
                    not plant["notified"]):
                    
                    message = f"""⏰ WAKTU PANEN ⏰

Jenis: {plant['name']}
Jumlah: {plant['quantity']} tanaman
Tanggal Tanam: {plant['date_planted']}
Target: {plant['target_harvest']}

Sekarang waktunya panen! 🌾"""
                    
                    if send_telegram_message(message):
                        plant["notified"] = True
                        save_state(state)
                        
    except Exception as e:
        print(f"Error checking harvest: {e}")

# ===== NOTIFICATION FUNCTIONS =====
def send_watering_notification():
    try:
        with LOCK:
            state = load_state()
            loc_name = state.get("location_name", "Bangil")
        
        growing_plants = len([p for p in state.get("plants", []) if p["status"] == "growing"])
        
        text = f"""🚿 WAKTU PENYIRAMAN 🚿

📍 Lokasi: {loc_name}
🕐 Pukul: {datetime.datetime.now().strftime("%H:%M")} WIB
🌱 Tanaman Aktif: {growing_plants} jenis

Selamat menyiram! 💦"""
        
        return send_telegram_message(text)
    except Exception as e:
        print(f"Error watering notification: {e}")
        return False

def send_weather_report(time_of_day):
    try:
        weather_data = fetch_weather()
        if "error" not in weather_data:
            message = format_weather_message(weather_data, time_of_day)
            send_telegram_message(message)
    except Exception as e:
        print(f"Error weather report: {e}")

# ===== SCHEDULER =====
def background_scheduler():
    print("🕐 Background scheduler started...")
    
    while True:
        try:
            now = datetime.datetime.now()
            
            # Cuaca pagi & siang
            if now.minute == 0:
                if now.hour == 7:
                    send_weather_report("Pagi")
                elif now.hour == 14:
                    send_weather_report("Siang")
            
            # Penyiraman
            for schedule in WATERING_SCHEDULES:
                if (now.hour == schedule['hour'] and 
                    now.minute == schedule['minute']):
                    send_watering_notification()
            
            # Cek panen
            if now.minute == 0:
                check_harvest_schedule()
            
            time.sleep(60)
                
        except Exception as e:
            print(f"Scheduler error: {e}")
            time.sleep(60)

# ===== TELEGRAM BOT =====
def telegram_polling():
    print("📱 Telegram polling started...")
    last_update_id = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 30}
            
            response = requests.get(url, params=params, timeout=35)
            data = response.json()
            
            if data.get("ok"):
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    
                    message = update.get("message", {})
                    text = message.get("text", "").strip()
                    chat_id = message.get("chat", {}).get("id")
                    
                    if str(chat_id) != CHAT_ID:
                        continue
                    
                    # Handle commands
                    if text.startswith("/cuaca"):
                        weather_data = fetch_weather()
                        if "error" not in weather_data:
                            msg = format_weather_message(weather_data, "Real-time")
                            send_telegram_message(f"🌤 CUACA REAL-TIME 🌤\n\n{msg}", chat_id)
                        
                    elif text.startswith("/status"):
                        with LOCK:
                            state = load_state()
                        
                        growing = len([p for p in state.get("plants", []) if p["status"] == "growing"])
                        harvested = len(state.get("harvest_history", []))
                        
                        msg = f"""🌱 STATUS KEBUN 🌱

📍 Lokasi: {state.get('location_name', 'Bangil')}
🌿 Tanaman Aktif: {growing} jenis
🌾 Total Panen: {harvested} kali

💧 Jadwal Penyiraman:
• 07.00 Pagi
• 13.30 Siang"""
                        send_telegram_message(msg, chat_id)

                    elif text.startswith("/plants"):
                        with LOCK:
                            state = load_state()
                        
                        plants_msg = "🌿 TANAMAN AKTIF 🌿\n\n"
                        growing_plants = [p for p in state.get("plants", []) if p["status"] == "growing"]
                        
                        if not growing_plants:
                            plants_msg += "Belum ada tanaman aktif"
                        else:
                            for plant in growing_plants:
                                plants_msg += f"""• {plant['name']}
  Jumlah: {plant['quantity']} tanaman
  Tanam: {plant['date_planted']}
  Target: {plant['target_harvest']}
  Panen: {plant['harvest_date']}
  
"""
                        send_telegram_message(plants_msg, chat_id)
                        
                    elif text.startswith("/help") or text.startswith("/start"):
                        help_msg = """🤖 CUACATANI BOT

Perintah:
/cuaca - Cek cuaca
/status - Status kebun  
/plants - Lihat tanaman
/help - Bantuan

⏰ Notifikasi Otomatis:
• 07:00 & 14:00 - Laporan cuaca
• 07:00 & 13:30 - Penyiraman
• Otomatis - Pengingat panen"""
                        send_telegram_message(help_msg, chat_id)
                        
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(10)

# ===== FLASK ROUTES =====
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/weather")
def api_weather():
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        weather_data = fetch_weather(lat, lon)
        return jsonify(weather_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/state")
def api_state():
    try:
        with LOCK:
            state = load_state()
        return jsonify(state)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/plant_types")
def api_plant_types():
    return jsonify(PLANT_TYPES)

@app.route("/api/add_plant", methods=["POST"])
def api_add_plant():
    try:
        data = request.get_json() or request.form
        plant_type = data.get("plant_type")
        quantity = data.get("quantity")
        date_planted = data.get("date_planted")
        target_harvest = data.get("target_harvest")
        
        if not all([plant_type, quantity, date_planted, target_harvest]):
            return jsonify({"error": "Semua field harus diisi"}), 400
        
        success = add_plant(plant_type, quantity, date_planted, target_harvest)
        
        if success:
            return jsonify({"status": "ok", "message": "Tanaman berhasil ditambahkan"})
        else:
            return jsonify({"error": "Gagal menambahkan tanaman"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/harvest_plant", methods=["POST"])
def api_harvest_plant():
    try:
        data = request.get_json() or request.form
        plant_id = data.get("plant_id")
        harvest_amount = data.get("harvest_amount")
        
        if not all([plant_id, harvest_amount]):
            return jsonify({"error": "plant_id dan harvest_amount harus diisi"}), 400
        
        success = harvest_plant(int(plant_id), harvest_amount)
        
        if success:
            return jsonify({"status": "ok", "message": "Panen berhasil dicatat"})
        else:
            return jsonify({"error": "Gagal mencatat panen"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/force_notify", methods=["POST"])
def api_force_notify():
    try:
        data = request.get_json() or request.form
        typ = data.get("type")
        
        if typ == "weather_morning":
            send_weather_report("Pagi")
            return jsonify({"sent": True, "type": "weather_morning"})
        elif typ == "weather_afternoon":
            send_weather_report("Siang")
            return jsonify({"sent": True, "type": "weather_afternoon"})
        elif typ == "water":
            ok = send_watering_notification()
            return jsonify({"sent": ok, "type": "water"})
        else:
            return jsonify({"error": "Tipe tidak dikenal"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== RUN =====
if __name__ == "__main__":
    print("🤖 CuacaTani Bot Starting...")
    print("📍 Lokasi: Bangil, Pasuruan")
    print("🌿 8 Jenis Tanaman")
    print("💧 Penyiraman: 07:00 & 13:30")
    print("🌅 Laporan Cuaca: 07:00 & 14:00")
    
    # Buat folder templates jika belum ada
    if not os.path.exists("templates"):
        os.makedirs("templates")
    
    # Kirim startup message
    startup_msg = """🚀 CUACATANI BOT AKTIF!

📍 Lokasi: Bangil, Pasuruan
🌿 8 Jenis Tanaman: Siap dilacak
⏰ Notifikasi otomatis aktif
💧 Penyiraman: 07:00 & 13:30

Ketik /help untuk mulai"""
    
    send_telegram_message(startup_msg)
    
    # Start threads
    threading.Thread(target=background_scheduler, daemon=True).start()
    threading.Thread(target=telegram_polling, daemon=True).start()
    
    # Run app
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Server ready on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)