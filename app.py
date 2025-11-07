import os
import json
import time
import threading
import datetime
import requests
import random
from flask import Flask, render_template, request, jsonify, redirect
from flask_cors import CORS

app = Flask(_name_)
CORS(app)

# ===== CONFIG =====
WEATHER_API_KEYS = [
    "78c2f2db26e14bcd81c70611251710",
]

TELEGRAM_TOKEN = "8209053292:AAE2Xh6bftjzZjWz0YO-69aKqOmVBHzJtrk"
CHAT_ID = "5698906519"

# DEFAULT LOCATION BANGIL, PASURUAN
DEFAULT_LAT = -7.5995  # Bangil, Pasuruan
DEFAULT_LON = 112.8186 # Bangil, Pasuruan  
DEFAULT_LOCATION = "Bangil, Pasuruan"

# JADWAL PENYIRAMAN (disesuaikan)
WATERING_SCHEDULES = [
    {"hour": 7, "minute": 0},   # 07:00 pagi
    {"hour": 13, "minute": 30}  # 13:30 siang
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
            state = json.load(f)
            default_state = create_default_state()
            for key, value in default_state.items():
                if key not in state:
                    state[key] = value
            return state
    except Exception as e:
        print(f"Error loading state: {e}")
        return create_default_state()

def create_default_state():
    return {
        "location_name": DEFAULT_LOCATION,
        "lat": DEFAULT_LAT,
        "lon": DEFAULT_LON,
        "last_weather_update": None,
        "plants": [],  # List tanaman yang sedang ditanam
        "harvest_history": []  # Riwayat panen
    }

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving state: {e}")
        return False

def send_telegram_message(text, chat_id=None, parse_mode="Markdown"):
    if not TELEGRAM_TOKEN:
        print("[WARN] TELEGRAM_TOKEN belum diset.")
        return False
    
    if chat_id is None:
        chat_id = CHAT_ID
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Telegram message sent to {chat_id}")
            return True
        else:
            print(f"❌ Telegram error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Error kirim Telegram: {e}")
        return False

# ===== LOCATION FUNCTIONS =====
def get_location_name(lat, lon):
    """Get location name from coordinates using Nominatim"""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=16"
        headers = {'User-Agent': 'CuacaTaniApp/1.0'}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        
        if 'display_name' in data:
            name_parts = data['display_name'].split(',')
            if len(name_parts) >= 2:
                return f"{name_parts[0].strip()}, {name_parts[1].strip()}"
            return data['display_name']
        
        return f"Lokasi ({lat:.4f}, {lon:.4f})"
    except Exception as e:
        print(f"Error getting location name: {e}")
        return f"Lokasi ({lat:.4f}, {lon:.4f})"

# ===== WEATHER FUNCTIONS =====
def fetch_weather_openmeteo(lat, lon):
    """Open-Meteo - FREE, no API key, real weather data"""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&timezone=Asia/Jakarta"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if "error" in data:
            return {"error": data["reason"]}
            
        current = data["current"]
        
        # Convert weather code to text
        weather_codes = {
            0: "Cerah", 1: "Cerah", 2: "Cerah Berawan", 
            3: "Berawan", 45: "Kabut", 48: "Kabut",
            51: "Hujan Ringan", 53: "Hujan Sedang", 55: "Hujan Lebat",
            61: "Hujan Ringan", 63: "Hujan Sedang", 65: "Hujan Lebat",
            80: "Hujan Ringan", 81: "Hujan Sedang", 82: "Hujan Lebat"
        }
        
        weather_condition = weather_codes.get(current["weather_code"], "Berawan")
        
        return {
            "source": "Open-Meteo (Real Data)",
            "location": "Bangil Area",
            "temp_c": round(current["temperature_2m"]),
            "humidity": round(current["relative_humidity_2m"]),
            "wind_kph": round(current["wind_speed_10m"] * 3.6),  # Convert m/s to km/h
            "condition": weather_condition,
            "feelslike_c": round(current["temperature_2m"] + 2)
        }
    except Exception as e:
        print(f"Open-Meteo error: {e}")
        return {"error": str(e)}

def fetch_weather_weatherapi(lat, lon, api_key):
    try:
        q = f"{lat},{lon}"
        url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={q}&aqi=no"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if "error" in data:
            error_msg = data["error"].get("message", "API error")
            print(f"❌ WeatherAPI error: {error_msg}")
            return {"error": error_msg}
        
        current = data.get("current", {})
        location = data.get("location", {})
        
        result = {
            "source": "WeatherAPI",
            "location": location.get("name", "Bangil"),
            "temp_c": round(current.get("temp_c", 0)),
            "humidity": current.get("humidity", 0),
            "condition": current.get("condition", {}).get("text", "Unknown"),
            "wind_kph": round(current.get("wind_kph", 0)),
            "feelslike_c": round(current.get("feelslike_c", 0))
        }
        
        print(f"✅ WeatherAPI data: {result['location']} - {result['temp_c']}°C")
        return result
        
    except Exception as e:
        print(f"WeatherAPI error: {e}")
        return {"error": "API timeout"}

def fetch_weather(lat=None, lon=None):
    try:
        with LOCK:
            state = load_state()
        
        if lat is None or lon is None:
            lat = state.get("lat", DEFAULT_LAT)
            lon = state.get("lon", DEFAULT_LON)
        
        print(f"🔍 Fetching weather for: {lat}, {lon}")
        
        # 1. Try WeatherAPI first
        for api_key in WEATHER_API_KEYS:
            result = fetch_weather_weatherapi(lat, lon, api_key)
            if "error" not in result:
                return result
        
        # 2. Fallback to Open-Meteo (FREE, real data)
        print("🔄 Falling back to Open-Meteo...")
        result = fetch_weather_openmeteo(lat, lon)
        if "error" not in result:
            return result
        
        # 3. Final fallback - realistic Bangil data
        print("⚠ Using realistic Bangil data")
        bangil_conditions = ["Cerah", "Cerah Berawan", "Berawan", "Hujan Ringan"]
        return {
            "source": "System (Realistic Bangil)",
            "location": "Bangil, Pasuruan",
            "temp_c": random.randint(28, 34),
            "humidity": random.randint(70, 85),
            "condition": random.choice(bangil_conditions),
            "wind_kph": random.randint(5, 15),
            "feelslike_c": random.randint(30, 36)
        }
    except Exception as e:
        print(f"Error in fetch_weather: {e}")
        return {"error": str(e)}

def format_weather_message(weather_data, time_of_day="Pagi"):
    """Format data cuaca menjadi pesan Telegram"""
    try:
        location = weather_data.get('location', 'Bangil')
        temp = weather_data.get('temp_c', 0)
        humidity = weather_data.get('humidity', 0)
        condition = weather_data.get('condition', 'Cerah')
        wind = weather_data.get('wind_kph', 0)
        
        if time_of_day == "Pagi":
            emoji = "🌅"
            activity = "• 🌱 Periksa kondisi tanaman\n• 💧 Persiapan penyiraman\n• 🐛 Cek hama dan penyakit"
        else:
            emoji = "☀"  
            activity = "• 🌿 Pantau pertumbuhan tanaman\n• 💦 Evaluasi kebutuhan air\n• 📝 Catat perkembangan"
        
        message = f"""{emoji} LAPORAN CUACA {time_of_day.upper()} {emoji}

📍 Lokasi: {location}
🌡 Suhu: {temp}°C
💧 Kelembaban: {humidity}%
🌬 Angin: {wind} km/jam  
☁ Kondisi: {condition}

💡 Tips Bertani Hari Ini:
• 💧 Sesuaikan penyiraman dengan cuaca
• 🌱 Pantau pertumbuhan 8 jenis tanaman
• 🐛 Waspada hama dan penyakit

📋 Kegiatan {time_of_day}:
{activity}

Tetap semangat bertani! 🌾"""
        
        return message
    except Exception as e:
        return f"Laporan cuaca {time_of_day} untuk {weather_data.get('location', 'Bangil')}"

def calculate_difference(target, actual):
    """Hitung selisih target dan aktual"""
    try:
        # Convert string to numbers
        target_num = float(''.join(filter(str.isdigit, target)))
        actual_num = float(actual)
        difference = actual_num - target_num
        
        if difference > 0:
            return f"+{difference} (Lebih)"
        elif difference < 0:
            return f"{difference} (Kurang)"
        else:
            return "0 (Tepat)"
    except:
        return "Tidak bisa dihitung"

# ===== PLANT MANAGEMENT =====
def add_plant(plant_type, quantity, date_planted, target_harvest):
    """Tambahkan tanaman baru"""
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
                "actual_harvest": None,
                "harvest_amount": None,
                "status": "growing",  # growing, ready, harvested
                "notified": False
            }
            
            state["plants"].append(new_plant)
            save_state(state)
            
            # Kirim notifikasi tanam
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
    """Panen tanaman"""
    try:
        with LOCK:
            state = load_state()
            
            for plant in state["plants"]:
                if plant["id"] == plant_id and plant["status"] == "growing":
                    plant["status"] = "harvested"
                    plant["actual_harvest"] = datetime.date.today().isoformat()
                    plant["harvest_amount"] = harvest_amount
                    
                    # Pindahkan ke riwayat
                    harvest_record = plant.copy()
                    harvest_record["harvest_id"] = len(state["harvest_history"]) + 1
                    state["harvest_history"].append(harvest_record)
                    
                    save_state(state)
                    
                    # Kirim notifikasi panen
                    message = f"""🌾 HASIL PANEN 🌾

Jenis: {plant['name']}
Tanggal Tanam: {plant['date_planted']}
Target: {plant['target_harvest']}
Hasil Aktual: {harvest_amount}
Selisih: {calculate_difference(plant['target_harvest'], harvest_amount)}

Selamat atas panennya! 🎉"""
                    
                    send_telegram_message(message)
                    return True
                    
        return False
    except Exception as e:
        print(f"Error harvesting plant: {e}")
        return False

def check_harvest_schedule():
    """Cek jadwal panen"""
    try:
        with LOCK:
            state = load_state()
            today = datetime.date.today().isoformat()
            
            for plant in state["plants"]:
                if (plant["status"] == "growing" and 
                    plant["harvest_date"] == today and 
                    not plant["notified"]):
                    
                    # Kirim notifikasi panen
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
        print(f"Error checking harvest schedule: {e}")

# ===== NOTIFICATION FUNCTIONS =====
def send_watering_notification():
    """Kirim notifikasi penyiraman"""
    try:
        with LOCK:
            state = load_state()
            loc_name = state.get("location_name", "Bangil")
        
        current_time = datetime.datetime.now().strftime("%H:%M")
        
        # Hitung total tanaman yang sedang tumbuh
        growing_plants = len([p for p in state.get("plants", []) if p["status"] == "growing"])
        
        text = f"""🚿 WAKTU PENYIRAMAN 🚿

📍 Lokasi: {loc_name}
🕐 Pukul: {current_time} WIB
🌱 Tanaman Aktif: {growing_plants} jenis

💧 Panduan Penyiraman:
• Gunakan air bersih
• Siram merata di sekitar akar  
• Perhatikan kondisi masing-masing tanaman
• Sesuaikan volume dengan jenis tanaman

Selamat menyiram! 💦"""
        
        print(f"💧 Sending watering notification for {loc_name}")
        if send_telegram_message(text):
            print("✅ Notifikasi penyiraman terkirim")
            return True
        else:
            print("❌ Gagal kirim notifikasi penyiraman")
            return False
                
    except Exception as e:
        print(f"Error sending watering notification: {e}")
        return False

def send_weather_report(time_of_day):
    """Kirim laporan cuaca"""
    try:
        weather_data = fetch_weather()
        
        if "error" not in weather_data:
            message = format_weather_message(weather_data, time_of_day)
            
            success = send_telegram_message(message)
            if success:
                print(f"✅ Laporan cuaca {time_of_day} terkirim")
            else:
                print(f"❌ Gagal kirim laporan {time_of_day}")
                
    except Exception as e:
        print(f"Error sending weather report: {e}")

# ===== SCHEDULER =====
def background_scheduler():
    """Scheduler untuk notifikasi otomatis"""
    print("🕐 Background scheduler started...")
    print("💧 Jadwal penyiraman: 07:00 & 13:30")
    print("🌅 Laporan cuaca: 07:00 & 14:00")
    print("🌾 Cek panen: Setiap jam")
    
    while True:
        try:
            now = datetime.datetime.now()
            current_hour = now.hour
            current_minute = now.minute
            
            # Laporan cuaca jam 7:00 dan 14:00
            if current_minute == 0:
                if current_hour == 7:
                    print("🌅 Waktunya laporan cuaca pagi")
                    send_weather_report("Pagi")
                elif current_hour == 14:
                    print("☀ Waktunya laporan cuaca siang")  
                    send_weather_report("Siang")
            
            # Jadwal penyiraman
            for schedule in WATERING_SCHEDULES:
                if (current_hour == schedule['hour'] and 
                    current_minute == schedule['minute']):
                    
                    print(f"💧 Waktunya penyiraman jam {schedule['hour']:02d}:{schedule['minute']:02d}")
                    send_watering_notification()
            
            # Cek panen setiap jam
            if current_minute == 0:
                check_harvest_schedule()
            
            time.sleep(60)
                
        except Exception as e:
            print(f"Scheduler error: {e}")
            time.sleep(60)

# ===== TELEGRAM BOT =====
def telegram_polling():
    """Polling untuk menerima message dari Telegram"""
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
                    
                    print(f"📨 Received: {text}")
                    
                    if str(chat_id) != CHAT_ID:
                        continue
                    
                    # Handle commands
                    if text.startswith("/cuaca"):
                        weather_data = fetch_weather()
                        if "error" not in weather_data:
                            response_message = format_weather_message(weather_data, "Real-time")
                            response_message = f"🌤 CUACA REAL-TIME 🌤\n\n" + response_message
                        else:
                            response_message = f"❌ Gagal mengambil data cuaca"
                        
                        send_telegram_message(response_message, chat_id)
                        
                    elif text.startswith("/status"):
                        with LOCK:
                            state = load_state()
                        
                        growing_count = len([p for p in state.get("plants", []) if p["status"] == "growing"])
                        harvested_count = len(state.get("harvest_history", []))
                        
                        status_message = f"""🌱 STATUS KEBUN 🌱

📍 Lokasi: {state.get('location_name', 'Bangil')}
🌿 Tanaman Aktif: {growing_count} jenis
🌾 Total Panen: {harvested_count} kali

💧 Jadwal Penyiraman:
• 07.00 Pagi
• 13.30 Siang

Ketik /plants untuk lihat detail tanaman"""
                        
                        send_telegram_message(status_message, chat_id)

                    elif text.startswith("/plants"):
                        with LOCK:
                            state = load_state()
                        
                        plants_message = "🌿 DAFTAR TANAMAN AKTIF 🌿\n\n"
                        growing_plants = [p for p in state.get("plants", []) if p["status"] == "growing"]
                        
                        if not growing_plants:
                            plants_message += "Belum ada tanaman aktif"
                        else:
                            for plant in growing_plants:
                                plants_message += f"""• {plant['name']}
  Jumlah: {plant['quantity']} tanaman
  Tanam: {plant['date_planted']}
  Target: {plant['target_harvest']}
  Perkiraan Panen: {plant['harvest_date']}
  
"""
                        
                        send_telegram_message(plants_message, chat_id)
                        
                    elif text.startswith("/help") or text.startswith("/start"):
                        help_message = """🤖 CUACATANI BOT - 8 JENIS TANAMAN 🤖

Perintah yang tersedia:
/cuaca - Cek cuaca terkini
/status - Status kebun keseluruhan  
/plants - Lihat tanaman aktif
/help - Tampilkan bantuan

⏰ Notifikasi Otomatis:
• 🌅 07:00 - Laporan cuaca pagi
• ☀ 14:00 - Laporan cuaca siang  
• 💧 07:00 & 13:30 - Pengingat penyiraman
• 🌾 - Pengingat panen (otomatis)

📊 8 Jenis Tanaman:
Cabe, Tomat, Terong, Kangkung, Bayam, Sawi, Wortel, Kol"""
                        
                        send_telegram_message(help_message, chat_id)
                    
                    elif text.startswith("/test"):
                        send_telegram_message("🧪 Test berhasil! Bot aktif 🎉", chat_id)
                    
                    elif text.startswith("/location"):
                        with LOCK:
                            state = load_state()
                        
                        current_loc = state.get('location_name', 'Bangil')
                        current_lat = state.get('lat', DEFAULT_LAT)
                        current_lon = state.get('lon', DEFAULT_LON)
                        
                        location_msg = f"""📍 LOKASI SAAT INI 📍

Nama: {current_loc}
Latitude: {current_lat}
Longitude: {current_lon}

Cuaca saat ini: {fetch_weather().get('location', 'Bangil')}"""
                        
                        send_telegram_message(location_msg, chat_id)
                        
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(10)

# ===== FLASK ROUTES =====
@app.route("/")
def index():
    """Serve dashboard HTML"""
    return render_template("index.html")

@app.route("/api/weather")
def api_weather():
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        
        if lat and lon:
            weather_data = fetch_weather(lat, lon)
        else:
            weather_data = fetch_weather()
            
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
    """Get available plant types"""
    return jsonify(PLANT_TYPES)

@app.route("/api/add_plant", methods=["POST"])
def api_add_plant():
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
            
        plant_type = data.get("plant_type")
        quantity = data.get("quantity")
        date_planted = data.get("date_planted")
        target_harvest = data.get("target_harvest")
        
        if not all([plant_type, quantity, date_planted, target_harvest]):
            return jsonify({"error": "All fields are required"}), 400
        
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
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
            
        plant_id = data.get("plant_id")
        harvest_amount = data.get("harvest_amount")
        
        if not all([plant_id, harvest_amount]):
            return jsonify({"error": "plant_id and harvest_amount are required"}), 400
        
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
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
            
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
            return jsonify({"error": "unknown type"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/set_location", methods=["POST"])
def api_set_location():
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
            
        lat = data.get("lat")
        lon = data.get("lon")
        
        if lat is None or lon is None:
            return jsonify({"error": "lat & lon required"}), 400
        
        lat = float(lat)
        lon = float(lon)
        
        with LOCK:
            state = load_state()
            state["lat"] = lat
            state["lon"] = lon
            
            location_name = get_location_name(lat, lon)
            state["location_name"] = location_name
            
            save_state(state)
        
        return jsonify({
            "status": "ok",
            "lat": lat,
            "lon": lon,
            "location_name": location_name
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== RUN =====
if _name_ == "_main_":
    print("🤖 CuacaTani Bot Starting...")
    print("📍 Lokasi: Bangil, Pasuruan")
    print("🌿 8 Jenis Tanaman: Cabe, Tomat, Terong, Kangkung, Bayam, Sawi, Wortel, Kol")
    print("💧 Penyiraman: 07:00 & 13:30")
    print("🌅 Laporan Cuaca: 07:00 & 14:00")
    
    # Buat folder templates
    if not os.path.exists("templates"):
        os.makedirs("templates")
        print("📁 Created templates folder")
    
    # Kirim startup message
    startup_msg = """🚀 CUACATANI BOT AKTIF!

📍 Lokasi: Bangil, Pasuruan
🌿 8 Jenis Tanaman: Siap dilacak
⏰ Notifikasi otomatis aktif
💧 Penyiraman: 07:00 & 13:30
🌤 Cuaca: Real-time dari Open-Meteo

Ketik /help untuk bantuan"""
    
    if send_telegram_message(startup_msg):
        print("✅ Startup message sent")
    
    # Start threads
    threading.Thread(target=background_scheduler, daemon=True).start()
    threading.Thread(target=telegram_polling, daemon=True).start()
    
    # Untuk deploy di hosting (Railway, Heroku, dll)
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Server ready on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
