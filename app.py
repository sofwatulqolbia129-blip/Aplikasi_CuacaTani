import os
import json
import time
import threading
import datetime
import requests
import random
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

app = Flask(_name_)
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
DEFAULT_LOCATION = "Bangil, Pasuruan, Jawa Timur"

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

# ===== INITIALIZATION =====
def initialize_app():
    """Initialize application state"""
    print("🔧 Initializing application...")
    
    # Create state file if not exists
    try:
        state = load_state()
        print("✅ State initialized")
    except Exception as e:
        print(f"❌ State initialization failed: {e}")
    
    # Create templates directory
    if not os.path.exists("templates"):
        os.makedirs("templates")
        print("✅ Templates directory created")
    
    print("🎉 Application initialization complete")

# ===== HELPERS =====
def load_state():
    """Load state from file"""
    try:
        if not os.path.exists(STATE_FILE):
            default_state = {
                "location_name": DEFAULT_LOCATION,
                "lat": DEFAULT_LAT,
                "lon": DEFAULT_LON,
                "last_weather_update": None,
                "plants": [],
                "harvest_history": []
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(default_state, f, ensure_ascii=False, indent=2)
            return default_state
        
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading state: {e}")
        return create_default_state()

def create_default_state():
    """Create default state"""
    return {
        "location_name": DEFAULT_LOCATION,
        "lat": DEFAULT_LAT,
        "lon": DEFAULT_LON,
        "last_weather_update": None,
        "plants": [],
        "harvest_history": []
    }

def save_state(state):
    """Save state to file"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving state: {e}")
        return False

def send_telegram_message(text, chat_id=None):
    """Send message to Telegram"""
    if not TELEGRAM_TOKEN:
        return False
    
    if chat_id is None:
        chat_id = CHAT_ID
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error sending Telegram: {e}")
        return False

# ===== WEATHER FUNCTIONS =====
def fetch_weather_openmeteo(lat, lon):
    """Fetch weather from Open-Meteo"""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code&timezone=Asia/Jakarta"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if "error" in data:
            return {"error": data["reason"]}
            
        current = data["current"]
        
        weather_codes = {
            0: "Cerah", 1: "Cerah", 2: "Cerah Berawan", 
            3: "Berawan", 45: "Kabut", 48: "Kabut",
            51: "Gerimis Ringan", 53: "Gerimis Sedang", 55: "Gerimis Lebat",
            61: "Hujan Ringan", 63: "Hujan Sedang", 65: "Hujan Lebat",
            80: "Hujan Lebat Ringan", 81: "Hujan Lebat Sedang", 82: "Hujan Lebat Deras",
            95: "Badai Petir", 96: "Badai Petir dengan Hujan Es", 99: "Badai Petir Parah"
        }
        
        return {
            "source": "Open-Meteo",
            "location": "Bangil, Pasuruan",
            "temp_c": round(current["temperature_2m"]),
            "humidity": round(current["relative_humidity_2m"]),
            "wind_kph": round(current["wind_speed_10m"] * 3.6),
            "condition": weather_codes.get(current["weather_code"], "Berawan"),
            "precipitation": round(current.get("precipitation", 0), 1)
        }
    except Exception as e:
        return {"error": str(e)}

def get_bangil_weather_fallback():
    """Fallback weather data for Bangil"""
    try:
        now = datetime.datetime.now()
        month = now.month
        hour = now.hour
        
        # Musim di Bangil
        if month in [11, 12, 1, 2, 3]:  # Musim Hujan
            conditions = ["Hujan Ringan", "Hujan Sedang", "Berawan", "Cerah Berawan"]
            temp_range = (26, 32)
            humidity_range = (75, 90)
        else:  # Musim Kemarau
            conditions = ["Cerah", "Cerah Berawan", "Berawan"]
            temp_range = (28, 35)
            humidity_range = (65, 80)
        
        # Adjust temperature based on time
        if 5 <= hour < 10:  # Pagi
            base_temp = temp_range[0] + 2
        elif 10 <= hour < 15:  # Siang
            base_temp = temp_range[1] - 1
        else:  # Sore/Malam
            base_temp = temp_range[0] + 3
            
        temp_c = base_temp + random.randint(-1, 1)
        humidity = random.randint(humidity_range[0], humidity_range[1])
        
        return {
            "source": "System (Bangil Data)",
            "location": "Bangil, Pasuruan, Jawa Timur", 
            "temp_c": temp_c,
            "humidity": humidity,
            "condition": random.choice(conditions),
            "wind_kph": random.randint(5, 15),
            "precipitation": random.randint(0, 3) if "Hujan" in conditions[0] else 0
        }
    except Exception as e:
        return {
            "source": "System",
            "location": "Bangil, Pasuruan",
            "temp_c": 30,
            "humidity": 75,
            "condition": "Cerah",
            "wind_kph": 10,
            "precipitation": 0
        }

def fetch_weather(lat=None, lon=None):
    """Main weather fetch function"""
    try:
        with LOCK:
            state = load_state()
        
        if lat is None or lon is None:
            lat = state.get("lat", DEFAULT_LAT)
            lon = state.get("lon", DEFAULT_LON)
        
        # Try Open-Meteo first
        result = fetch_weather_openmeteo(lat, lon)
        if "error" not in result:
            return result
        
        # Fallback to Bangil data
        return get_bangil_weather_fallback()
        
    except Exception as e:
        return get_bangil_weather_fallback()

def format_weather_message(weather_data, time_of_day="Pagi"):
    """Format weather message for Telegram"""
    try:
        location = weather_data.get('location', 'Bangil, Pasuruan')
        temp = weather_data.get('temp_c', 0)
        humidity = weather_data.get('humidity', 0)
        condition = weather_data.get('condition', 'Cerah')
        wind = weather_data.get('wind_kph', 0)
        precipitation = weather_data.get('precipitation', 0)
        
        condition_emoji = {
            "Cerah": "☀",
            "Cerah Berawan": "⛅", 
            "Berawan": "☁",
            "Hujan Ringan": "🌦",
            "Hujan Sedang": "🌧",
            "Hujan Lebat": "⛈",
            "Gerimis": "💧"
        }
        
        emoji = condition_emoji.get(condition, "🌤")
        time_emoji = "🌅" if time_of_day == "Pagi" else "☀"
        
        if time_of_day == "Pagi":
            activity = "• Periksa kelembaban tanah\n• Persiapan penyiraman pagi\n• Cek hama tanaman"
        else:
            activity = "• Pantau pertumbuhan tanaman\n• Evaluasi kebutuhan air\n• Catat perkembangan"
        
        if "Hujan" in condition or precipitation > 2:
            watering_rec = "💧 Kurangi penyiraman (sudah hujan)"
        elif temp > 32:
            watering_rec = "💧 Tambah frekuensi penyiraman (panas)"
        else:
            watering_rec = "💧 Penyiraman normal sesuai jadwal"
        
        return f"""{time_emoji} LAPORAN CUACA {time_of_day.upper()} {emoji}

📍 *Lokasi*: {location}
🌡 *Suhu*: {temp}°C
💧 *Kelembaban*: {humidity}%
🌬 *Angin*: {wind} km/jam
☁ *Kondisi*: {condition} {emoji}
🌧 *Curah Hujan*: {precipitation} mm

{watering_rec}

📋 *Kegiatan {time_of_day.lower()}*:
{activity}

Tetap semangat bertani! 🌾"""
        
    except Exception as e:
        return f"Laporan cuaca {time_of_day} untuk Bangil, Pasuruan"

# ===== PLANT MANAGEMENT =====
def add_plant(plant_type, quantity, date_planted, target_harvest):
    """Add new plant to tracking"""
    try:
        with LOCK:
            state = load_state()
            
            plant_info = PLANT_TYPES.get(plant_type)
            if not plant_info:
                return False
            
            planted_date = datetime.datetime.strptime(date_planted, "%Y-%m-%d")
            harvest_date = (planted_date + datetime.timedelta(days=plant_info["harvest_days"])).strftime("%Y-%m-%d")
            
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
            success = save_state(state)
            
            if success:
                message = f"""🌱 TANAMAN BARU DITANAM 🌱

*Jenis*: {new_plant['name']}
*Jumlah*: {quantity} tanaman
*Tanggal Tanam*: {date_planted}
*Target Panen*: {target_harvest}
*Perkiraan Panen*: {harvest_date}

Selamat menanam! 🌿"""
                
                send_telegram_message(message)
                return True
            return False
            
    except Exception as e:
        print(f"❌ Error adding plant: {e}")
        return False

def harvest_plant(plant_id, harvest_amount):
    """Mark plant as harvested"""
    try:
        with LOCK:
            state = load_state()
            
            for plant in state["plants"]:
                if plant["id"] == plant_id and plant["status"] == "growing":
                    plant["status"] = "harvested"
                    plant["actual_harvest"] = datetime.date.today().isoformat()
                    plant["harvest_amount"] = harvest_amount
                    
                    try:
                        target_str = ''.join(filter(str.isdigit, str(plant["target_harvest"]))) or "0"
                        actual_str = ''.join(filter(str.isdigit, str(harvest_amount))) or "0"
                        
                        target_num = float(target_str)
                        actual_num = float(actual_str)
                        difference = actual_num - target_num
                        
                        if difference > 0:
                            diff_text = f"📈 *Lebih*: +{difference} dari target"
                        elif difference < 0:
                            diff_text = f"📉 *Kurang*: {difference} dari target" 
                        else:
                            diff_text = "🎯 *Tepat*: Sesuai target"
                    except:
                        diff_text = "📊 *Selisih*: Tidak dapat dihitung"
                    
                    success = save_state(state)
                    
                    if success:
                        message = f"""🌾 HASIL PANEN 🌾

*Jenis*: {plant['name']}
*Tanggal Tanam*: {plant['date_planted']}
*Target*: {plant['target_harvest']}
*Hasil Aktual*: {harvest_amount}
{diff_text}

Selamat atas panennya! 🎉"""
                        
                        send_telegram_message(message)
                        return True
                    break
            return False
                
    except Exception as e:
        print(f"❌ Error harvesting plant: {e}")
        return False

def check_harvest_schedule():
    """Check if any plants are ready for harvest"""
    try:
        with LOCK:
            state = load_state()
            today = datetime.date.today().isoformat()
            
            for plant in state["plants"]:
                if (plant["status"] == "growing" and 
                    plant["harvest_date"] == today and 
                    not plant["notified"]):
                    
                    message = f"""⏰ WAKTU PANEN ⏰

*Jenis*: {plant['name']}
*Jumlah*: {plant['quantity']} tanaman
*Tanggal Tanam*: {plant['date_planted']}
*Target*: {plant['target_harvest']}

Sekarang waktunya panen! 🌾"""
                    
                    if send_telegram_message(message):
                        plant["notified"] = True
                        save_state(state)
    except Exception as e:
        print(f"❌ Error checking harvest: {e}")

# ===== NOTIFICATION FUNCTIONS =====
def send_watering_notification():
    """Send watering reminder"""
    try:
        with LOCK:
            state = load_state()
            loc_name = state.get("location_name", "Bangil, Pasuruan")
        
        growing_plants = len([p for p in state.get("plants", []) if p["status"] == "growing"])
        
        weather_data = fetch_weather()
        condition = weather_data.get("condition", "Cerah")
        
        if "Hujan" in condition:
            recommendation = "💡 *Rekomendasi*: Kurangi volume penyiraman karena kondisi lembab"
        elif weather_data.get("temp_c", 0) > 32:
            recommendation = "💡 *Rekomendasi*: Tambah volume penyiraman karena cuaca panas"
        else:
            recommendation = "💡 *Rekomendasi*: Penyiraman normal sesuai kebutuhan"
        
        text = f"""🚿 WAKTU PENYIRAMAN 🚿

📍 *Lokasi*: {loc_name}
🕐 *Pukul*: {datetime.datetime.now().strftime("%H:%M")} WIB
🌱 *Tanaman Aktif*: {growing_plants} jenis
☁ *Kondisi Cuaca*: {condition}

{recommendation}

Selamat menyiram! 💦"""
        
        return send_telegram_message(text)
    except Exception as e:
        print(f"❌ Error watering notification: {e}")
        return False

def send_weather_report(time_of_day):
    """Send weather report"""
    try:
        weather_data = fetch_weather()
        if "error" not in weather_data:
            message = format_weather_message(weather_data, time_of_day)
            send_telegram_message(message)
    except Exception as e:
        print(f"❌ Error sending weather report: {e}")

# ===== SCHEDULER =====
def background_scheduler():
    """Background task scheduler"""
    print("🕐 Background scheduler started...")
    
    while True:
        try:
            now = datetime.datetime.now()
            
            # Weather reports
            if now.minute == 0:
                if now.hour == 7:
                    send_weather_report("Pagi")
                elif now.hour == 14:
                    send_weather_report("Siang")
            
            # Watering notifications
            for schedule in WATERING_SCHEDULES:
                if (now.hour == schedule['hour'] and 
                    now.minute == schedule['minute']):
                    send_watering_notification()
            
            # Check harvest every hour
            if now.minute == 0:
                check_harvest_schedule()
            
            time.sleep(60)
                
        except Exception as e:
            print(f"❌ Scheduler error: {e}")
            time.sleep(60)

# ===== TELEGRAM BOT =====
def telegram_polling():
    """Telegram bot polling"""
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
                    
                    if text.startswith("/cuaca"):
                        weather_data = fetch_weather()
                        if "error" not in weather_data:
                            msg = format_weather_message(weather_data, "Real-time")
                            send_telegram_message(msg, chat_id)
                        else:
                            send_telegram_message("❌ Gagal mengambil data cuaca", chat_id)
                        
                    elif text.startswith("/status"):
                        with LOCK:
                            state = load_state()
                        
                        growing = len([p for p in state.get("plants", []) if p["status"] == "growing"])
                        harvested = len([p for p in state.get("plants", []) if p["status"] == "harvested"])
                        
                        weather_data = fetch_weather()
                        condition = weather_data.get("condition", "Tidak diketahui")
                        temp = weather_data.get("temp_c", 0)
                        
                        msg = f"""🌱 STATUS KEBUN 🌱

📍 *Lokasi*: {state.get('location_name', 'Bangil, Pasuruan')}
🌿 *Tanaman Aktif*: {growing} jenis
🌾 *Tanaman Dipanen*: {harvested} jenis
🌡 *Suhu Saat Ini*: {temp}°C
☁ *Kondisi*: {condition}

💧 *Jadwal Penyiraman*:
• 07:00 Pagi
• 13:30 Siang

Terbuka untuk saran dan masukan! 📝"""
                        send_telegram_message(msg, chat_id)

                    elif text.startswith("/plants"):
                        with LOCK:
                            state = load_state()
                        
                        plants_msg = "🌿 DAFTAR TANAMAN AKTIF 🌿\n\n"
                        growing_plants = [p for p in state.get("plants", []) if p["status"] == "growing"]
                        
                        if not growing_plants:
                            plants_msg += "❌ Belum ada tanaman aktif\n\n_Gunakan /tanam untuk menambah tanaman_"
                        else:
                            for plant in growing_plants:
                                plants_msg += f"""📌 *{plant['name']}*
  🔢 Jumlah: {plant['quantity']} tanaman
  📅 Tanam: {plant['date_planted']}
  🎯 Target: {plant['target_harvest']}
  🌾 Panen: {plant['harvest_date']}
  
"""
                        send_telegram_message(plants_msg, chat_id)
                    
                    elif text.startswith("/help") or text.startswith("/start"):
                        help_msg = """🤖 CUACATANI BOT - BANGIL, PASURUAN

*Perintah Tersedia*:
/cuaca - Data cuaca real-time
/status - Status kebun terkini  
/plants - Daftar tanaman aktif
/help - Bantuan ini

⏰ *Notifikasi Otomatis*:
• 07:00 & 14:00 - Laporan cuaca harian
• 07:00 & 13:30 - Pengingat penyiraman
• Otomatis - Peringatan waktu panen

📍 *Lokasi*: Bangil, Pasuruan, Jawa Timur
🌦 *Sumber Cuaca*: Open-Meteo & Data Lokal"""
                        send_telegram_message(help_msg, chat_id)
                        
            time.sleep(1)
                        
        except Exception as e:
            print(f"❌ Polling error: {e}")
            time.sleep(10)

# ===== FLASK ROUTES =====
@app.route("/")
def index():
    """Main page"""
    return "🌱 CuacaTani Bot API is Running! - Bangil, Pasuruan"

@app.route("/api/weather")
def api_weather():
    """Weather API endpoint"""
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        weather_data = fetch_weather(lat, lon)
        return jsonify(weather_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/state")
def api_state():
    """State API endpoint"""
    try:
        with LOCK:
            state = load_state()
        return jsonify(state)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/plant_types")
def api_plant_types():
    """Plant types API endpoint"""
    return jsonify(PLANT_TYPES)

@app.route("/api/add_plant", methods=["POST"])
def api_add_plant():
    """Add plant API endpoint"""
    try:
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
            
        plant_type = data.get("plant_type")
        quantity = data.get("quantity")
        date_planted = data.get("date_planted")
        target_harvest = data.get("target_harvest")
        
        if not all([plant_type, quantity, date_planted, target_harvest]):
            return jsonify({"error": "Semua field harus diisi"}), 400
        
        success = add_plant(plant_type, quantity, date_planted, target_harvest)
        
        if success:
            return jsonify({"status": "success", "message": "Tanaman berhasil ditambahkan"})
        else:
            return jsonify({"error": "Gagal menambahkan tanaman"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/harvest_plant", methods=["POST"])
def api_harvest_plant():
    """Harvest plant API endpoint"""
    try:
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
            
        plant_id = data.get("plant_id")
        harvest_amount = data.get("harvest_amount")
        
        if not all([plant_id, harvest_amount]):
            return jsonify({"error": "plant_id dan harvest_amount harus diisi"}), 400
        
        success = harvest_plant(int(plant_id), harvest_amount)
        
        if success:
            return jsonify({"status": "success", "message": "Panen berhasil dicatat"})
        else:
            return jsonify({"error": "Gagal mencatat panen"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/force_notify", methods=["POST"])
def api_force_notify():
    """Force notification API endpoint"""
    try:
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
            
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

@app.route("/health")
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "service": "CuacaTani Bot",
        "location": "Bangil, Pasuruan",
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "1.0.0"
    })

# ===== APPLICATION STARTUP =====
def start_background_services():
    """Start background threads"""
    print("🔄 Starting background services...")
    
    try:
        # Start scheduler thread
        scheduler_thread = threading.Thread(target=background_scheduler, daemon=True)
        scheduler_thread.start()
        print("✅ Background scheduler started")
        
        # Start Telegram polling thread
        telegram_thread = threading.Thread(target=telegram_polling, daemon=True)
        telegram_thread.start()
        print("✅ Telegram polling started")
        
    except Exception as e:
        print(f"❌ Error starting background services: {e}")

if _name_ == "_main_":
    # Initialize application
    initialize_app()
    
    # Start background services
    start_background_services()
    
    # Send startup notification
    startup_msg = """🚀 CUACATANI BOT BERHASIL DI DEPLOY!

📍 *Lokasi*: Bangil, Pasuruan, Jawa Timur
🌿 *Jenis Tanaman*: 8 jenis siap dilacak
⏰ *Notifikasi otomatis*: Aktif
💧 *Penyiraman*: 07:00 & 13:30 WIB
🌦 *Laporan Cuaca*: 07:00 & 14:00 WIB

Ketik /help untuk melihat perintah"""
    
    send_telegram_message(startup_msg)
    
    # Run Flask application
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Starting Flask server on port {port}")
    print("✅ CuacaTani Bot is ready!")
    
    # Run without debug mode for production
    app.run(host="0.0.0.0", port=port, debug=False)
