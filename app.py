from flask import Flask, render_template, request, redirect, session, jsonify, url_for, Response
import mysql.connector
import requests
import datetime
import pytz
import logging  
import time
import gspread

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("yacapsule.log"), logging.StreamHandler()]
)
logger = logging.getLogger("APP_PY") 

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

triggered_events = set()

TELEGRAM_BOT_TOKEN = "8438239600:AAF0XU_5dfeg4ey1qg7RRLQ8TRzjM8Q4Xk"
TELEGRAM_CHAT_ID = "1267686212"

GOOGLE_CREDS_DICT = {
    "type": "service_account",
    "project_id": "smart-med-dispenser-493611",
    "private_key_id": "531aba989a655f60ec6c371f972bf16017493e77",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCd8FakJ1oZqlk3\nX5WQEddIZf8IegHVC/Kxy0UtONIoySUEW5iRq104mRH95E3e1PztR3XiLLIE8p6j\nh/Zz++NYPR+ojSF0hepsINHhBsikDicB0mwG9aHwOSbJbKozJjoLkCihjJk+XD9Y\nlsUhltgt1djbtEkLU5+Dyl0QTLFJ4cm2kCktDI4teJHpizpWo+jRPz5TwRAtdyN9\nHQT007A16dINwZ2r5PNWFthYGYy8JZxCojDKtqY9JJsLnfYsvhDWbu0DAe6KeCf+\nVwnz3iXkI3bXJyKyE53I7DymVaHmbMUfHl5/jg6I5mrzj/A8N34PwzUn4X9oClKD\nqlONRLxBAgMBAAECggEAEvzc/bk5bNJ9DVoxefObJToV8ifw5nMcR2G/vFMTeRHN\noHt+mSy39WD5t8Nl1T9X9RLdSkbDVDLy/YgQChujVm1qy/HDruWWrE85zErrfkWx\nTNfGYwPO5zmHvzmQMLwMyG0ZZWqo1cVzXCwsIQColsIZ4zgGfBUenVKL47TEr7QE\nGRqJFAeMcVAIAtp6gA8hAvGkdUUDs4AmDQ7cVi+SGczulxSX5XWrWn2hCu4yWcSt\n3thsN3TyMVBLo+jOLsUhCXavluBXMDkDblHzie+wRElA7h2A1Avh6MJVkB7hbm+e\nj88Ax1aZap1zJoflZko3BG2GKxOLrodUrIl3toNAQQKBgQDLWwCqaVhgUGDTjD2q\nCR+zQhGY5JcKmkpYmQNS5iRJHM6YMzbFPgZ4YRZfKvQyiKJ/Br4GMVhQ3tAJi0Ni\nqWdNup5zIYILolwdvktctwMeILKY0VmEpZc0lmD/cPy7d31VObfLTv470hUJAf3w\nkx2jda1EdNqTJPfWEmB5ol66WQKBgQDG027uzx7VS+fXOWJQcI3jrbLyDUjbarIN\n8lWhILiOVe3jQ3vVy6+Z6opI4DscyyYSCjPNBxY2wMvH6vnpRZAEsIliFDA/bIm+\nDAOwOwdXkC9bhmw1u8ERF6IR8pAeHQXS4jK7ZyrppWgmhHZqa93+pYFOF7ovnUSd\nIhotnbuEKQKBgQC8NQJdtdgcc+fZgu9DYuRa9OfyeIYuQvRSIXPJEsU8gZPXm3ay\ngKBeY4TgGZIe/wRdynCurJbPahhi7Og19RFuCC1D4xxIBkF5Kbj4G02gYaTJ+N//\n+34BJripUfomywVNjnjDit2TofDkAFr1gEMrGOt+8yOkkc9q6mEt0hAYKQKBgFnO\nctMHVuP9LzE1yESRMmXetW9DtN726IoIJclr4DDae2Mlvi+pmx2opOGZ9tlgoUeQ\nuCkpxEzi9KjOaCeHti+IFeXpPInJWsYu4xOc9goFJH7wzrvOnLw9soTszU/syA6j\nAUtIpEd44PxU5K/ZHSLCWw+NBBoxrSZUmwJztplRAoGABj9UsQQ+CSgkl0g0TwiJ\n1fL6nvQoCHKJOtpTNSmve+vQr9qVCraLnD65KmvmI+YFjU23zIS6VGnggOcMyvMy\n4hIMY5FubQDNf/zIbi5u0Jr645YU/oRheQDoKOXPMGjg9cYZpk91gfaVKJr646g+\nuD7DDtoOGGp/IssWRV/qnpU=\n-----END PRIVATE KEY-----\n",
    "client_email": "rpi-logger@smart-med-dispenser-493611.iam.gserviceaccount.com",
    "client_id": "103805086149749040171",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/rpi-logger%40smart-med-dispenser-493611.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

def send_telegram_alert(patient_name, medicine_name, scheduled_time):
    message = (
        f"🚨 *YACAPSULE DISPENSER ALERT*\n\n"
        f"👩‍⚕️ *Attention Caregiver:*\n"
        f"Medication is due and requires dispensing!\n\n"
        f"👤 *Patient:* {patient_name}\n"
        f"💊 *Medication:* {medicine_name}\n"
        f"⏰ *Scheduled Time:* {scheduled_time}\n\n"
        f"⚠️ _Please verify a caregiver scans their RFID card at the physical dispenser unit._"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Failed to transmit Telegram message: {e}")

def create_connection():
    try:
        return mysql.connector.connect(
            host='localhost', user='root', password='ahlencarlronnel', database='ahlencarlronnel'
        )
    except mysql.connector.Error as e:
        logger.error(f"Database connection error: {e}")
        return None

def ensure_tables():
    conn = create_connection()
    if not conn: return
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(64) UNIQUE, password VARCHAR(128)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(128) NOT NULL, age INT NOT NULL, status ENUM('active', 'archived') DEFAULT 'active'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patient_prescriptions (
            id INT AUTO_INCREMENT PRIMARY KEY, patient_id INT NOT NULL, medicine_name VARCHAR(255) NOT NULL,
            interval_type ENUM('once_a_day', 'twice_a_day', 'thrice_a_day', 'four_times_a_day', 'every_6hrs') NOT NULL,
            hardware_channel INT NOT NULL, time_1 VARCHAR(10) NULL, time_2 VARCHAR(10) NULL, time_3 VARCHAR(10) NULL, time_4 VARCHAR(10) NULL,
            anchor_start_time VARCHAR(10) NULL, last_calculated_run VARCHAR(10) NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INT AUTO_INCREMENT PRIMARY KEY, medicine_name VARCHAR(255) UNIQUE NOT NULL, quantity INT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_ph_time():
    return datetime.datetime.now(pytz.timezone('Asia/Manila'))

@app.route('/')
def home():
    return redirect(url_for('patients')) if 'user_id' in session else redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        conn = create_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('patients'))
        return "Invalid credentials", 401
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            return "Username and password cannot be empty!", 400
        conn = create_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            cur.close()
            conn.close()
            if err.errno == 1062: return "Username already exists!", 400
            return f"Database error: {err}", 500
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/patients')
def patients():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = create_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT medicine_name FROM inventory")
    inventory_list = [row['medicine_name'] for row in cur.fetchall()]
    
    query = """
        SELECT p.id AS patient_id, p.name, p.age, rx.id AS rx_id, rx.medicine_name, 
               rx.interval_type, rx.hardware_channel, rx.time_1, rx.time_2, rx.time_3, rx.time_4, rx.anchor_start_time
        FROM patients p
        LEFT JOIN patient_prescriptions rx ON p.id = rx.patient_id
        WHERE p.status = 'active'
    """
    cur.execute(query)
    raw_rows = cur.fetchall()
    cur.close()
    conn.close()

    segregated_tables = {
        'once_a_day': [], 'twice_a_day': [], 'thrice_a_day': [], 'four_times_a_day': [], 'every_6hrs': []
    }
    for row in raw_rows:
        if row['interval_type']:
            segregated_tables[row['interval_type']].append(row)
            
    return render_template('patients.html', tables=segregated_tables, inventory=inventory_list, username=session.get('username'))

@app.route('/add_patient', methods=['POST'])
def add_patient():
    if 'user_id' not in session: return redirect(url_for('login'))
    name = request.form.get('name')
    age = request.form.get('age')
    medicine_name = request.form.get('medicine_name')
    frequency = request.form.get('frequency') 

    time_1 = request.form.get('time_1') or None
    time_2 = request.form.get('time_2') or None
    time_3 = request.form.get('time_3') or None
    time_4 = request.form.get('time_4') or None

    channel_mapping = {'once_a_day': 0, 'twice_a_day': 1, 'thrice_a_day': 2, 'four_times_a_day': 3, 'every_6hrs': 4}
    hardware_channel = channel_mapping.get(frequency, 0)

    conn = create_connection()
    if not conn: return "Database Connection Failure", 500
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO patients (name, age, status) VALUES (%s, %s, 'active')", (name, age))
        patient_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO patient_prescriptions 
            (patient_id, medicine_name, interval_type, hardware_channel, time_1, time_2, time_3, time_4) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (patient_id, medicine_name, frequency, hardware_channel, time_1, time_2, time_3, time_4))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database registration failure: {e}")
        return f"Error registering profile: {e}", 500
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('patients'))

@app.route('/update_schedule/<int:patient_id>', methods=['POST'])
def update_schedule(patient_id):
    if 'user_id' not in session: return jsonify(success=False, error="Unauthorized Access"), 401
    request_data = request.get_json() if request.is_json else request.form
    t1 = request_data.get('time_1') or None
    t2 = request_data.get('time_2') or None
    t3 = request_data.get('time_3') or None
    t4 = request_data.get('time_4') or None

    conn = create_connection()
    if not conn: return jsonify(success=False, error="Database Connection Failure"), 500
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE patient_prescriptions SET time_1 = %s, time_2 = %s, time_3 = %s, time_4 = %s WHERE patient_id = %s
        """, (t1, t2, t3, t4, patient_id))
        conn.commit()
        return jsonify(success=True)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, error=str(e)), 500
    finally:
        cur.close()
        conn.close()

@app.route('/check_alarm')
def check_alarm():
    global triggered_events
    if request.remote_addr != '127.0.0.1' and 'user_id' not in session: 
        return jsonify(success=False, error="Unauthorized external request"), 401

    now_ph = get_ph_time()
    current_time_str = now_ph.strftime('%H:%M')
    current_date_str = now_ph.strftime('%Y-%m-%d')

    conn = create_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT rx.*, p.name FROM patient_prescriptions rx JOIN patients p ON rx.patient_id = p.id WHERE p.status = 'active'")
    all_prescriptions = cur.fetchall()
    cur.close()
    conn.close()

    triggered_patients = []
    for rx in all_prescriptions:
        matched_time = None
        rx_id = rx['id']

        if rx['interval_type'] in ['once_a_day', 'twice_a_day', 'thrice_a_day', 'four_times_a_day']:
            for t_field in ['time_1', 'time_2', 'time_3', 'time_4']:
                if rx[t_field] and str(rx[t_field]).strip()[:5] == current_time_str:
                    matched_time = current_time_str
                    break
        
        elif rx['interval_type'] == 'every_6hrs' and rx['last_calculated_run']:
            if str(rx['last_calculated_run']).strip()[:5] == current_time_str:
                matched_time = current_time_str
                try:
                    t_obj = datetime.datetime.strptime(current_time_str, "%H:%M")
                    next_run_str = (t_obj + datetime.timedelta(hours=6)).strftime("%H:%M")
                    conn = create_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE patient_prescriptions SET last_calculated_run=%s WHERE id=%s", (next_run_str, rx_id))
                    conn.commit()
                    cur.close()
                    conn.close()
                except Exception as ex:
                    logger.error(f"Error continuous calculations: {ex}")

        if matched_time:
            # UNIQUE TIME SEPARATED TRACKING KEY IMPLEMENTED TO PREVENT COLLISION BETWEEN INTERVALS
            event_key = (rx_id, rx['hardware_channel'], matched_time, current_date_str)
            if event_key in triggered_events:
                continue

            payload = {
                'id': rx['patient_id'], 'rx_id': rx_id, 'name': rx['name'],
                'medicine': rx['medicine_name'], 'hardware_channel': rx['hardware_channel'], 'schedule_time': matched_time,
                'type': 'scheduled'
            }
            triggered_patients.append(payload)
            triggered_events.add(event_key)
            send_telegram_alert(rx['name'], rx['medicine_name'], matched_time)

    if triggered_patients:
        try:
            logger.info(f"Grouped scheduled targets dispatching: {triggered_patients}")
            response = requests.post("http://localhost:5001/hardware/start_alarm", json={"patients": triggered_patients}, timeout=5.0)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"HARDWARE DISPATCH FAILED: {e}")
            for p in triggered_patients:
                triggered_events.discard((p['rx_id'], p['hardware_channel'], p['schedule_time'], current_date_str))
            return jsonify(success=False, error="Hardware service unreachable"), 500

    return jsonify(triggered_patients=triggered_patients)

@app.route('/inventory')
def inventory():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = create_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM inventory")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('inventory.html', inventory=rows, username=session.get('username'))

@app.route('/export_logs', methods=['GET'])
def export_logs():
    if 'user_id' not in session: return jsonify(success=False, error="Unauthorized Access"), 401
    conn = create_connection()
    cur = conn.cursor()
    cur.execute("SELECT patient_name, medicine_name, channel_used, dispense_type, timestamp FROM dispense_records ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    try:
        client = gspread.service_account_from_dict(GOOGLE_CREDS_DICT)
        sheet = client.open("Yacapsule").sheet1
        sheet.clear()
        
        headers = ["Patient Name", "Medicine Administered", "Hardware Channel Used", "Dispense Type", "Timestamp"]
        formatted_rows = [[r[0], r[1], f"Channel {r[2]}", r[3], r[4].strftime('%Y-%m-%d %H:%M:%S') if hasattr(r[4], 'strftime') else str(r[4])] for r in rows]
            
        sheet.append_row(headers)
        if formatted_rows:
            sheet.append_rows(formatted_rows)
        return jsonify(success=True)
    except Exception as err:
        return jsonify(success=False, error=str(err)), 500

@app.route('/api/log_success', methods=['POST'])
def log_success():
    data = request.get_json() or {}
    patient_name = data.get('name', 'Unknown')
    medicine = data.get('medicine', 'Unknown')
    channel = data.get('channel', '0')
    dispense_type = data.get('type', 'scheduled')
    timestamp_str = get_ph_time().strftime('%Y-%m-%d %H:%M:%S')

    try:
        client = gspread.service_account_from_dict(GOOGLE_CREDS_DICT)
        sheet = client.open("Yacapsule").sheet1
        sheet.append_row([patient_name, medicine, f"Channel {channel}", dispense_type, timestamp_str])
        return jsonify(success=True)
    except Exception as sheets_err:
        return jsonify(success=False, error=str(sheets_err)), 500

@app.route('/dispense_button/<int:rx_id>', methods=['POST'])
def dispense_button(rx_id):
    if 'user_id' not in session: return jsonify(success=False, error="Unauthorized Access"), 401
    request_data = request.get_json() or {}
    notes = request_data.get('verification_notes', 'Not provided')

    if rx_id in [3, 4]:
        med_name = "Metformin" if rx_id == 3 else "Amlodipine"
        channel_num = 3 if rx_id == 3 else 4
        patient_name = notes
        patient_id = 999
    else:
        conn = create_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT rx.*, p.name FROM patient_prescriptions rx JOIN patients p ON rx.patient_id = p.id WHERE rx.id = %s", (rx_id,))
        rx = cur.fetchone()
        cur.close()
        conn.close()
        if not rx: return jsonify(success=False, error="Prescription target not found"), 404
        med_name = rx['medicine_name']
        channel_num = rx['hardware_channel']
        patient_name = rx['name']
        patient_id = rx['patient_id']

    try:
        payload = {
            'id': patient_id, 'rx_id': rx_id, 'name': patient_name,
            'medicine': med_name, 'hardware_channel': channel_num, 'schedule_time': get_ph_time().strftime('%H:%M'),
            'type': 'manual'
        }
        requests.post("http://localhost:5001/hardware/start_alarm", json={"patients": [payload]}, timeout=5.0)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

if __name__ == '__main__':
    ensure_tables()
    app.run(host='0.0.0.0', port=5000, debug=True)
