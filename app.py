from flask import Flask, render_template, request, redirect, session, jsonify, url_for
import mysql.connector
import requests
import datetime
import pytz
import logging  # Import logging module
import gspread  # Import gspread for Google Sheets
from oauth2client.service_account import ServiceAccountCredentials # for gspread
import config  # Import SPREADSHEET_ID

# ---------- LOGGING CONFIGURATION ----------
# Configure logging to write to both file and terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("yacapsule.log"),  # Write all logs to this shared file
        logging.StreamHandler()              # Keep printing to the terminal
    ]
)
logger = logging.getLogger("APP_PY") # Create a logger named "APP_PY"

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Track triggered events per patient and per date to prevent duplicates.
triggered_events = set()

# ---------- TELEGRAM BOT CONFIGURATION ----------
TELEGRAM_BOT_TOKEN = "8438239600:AAF0XU_5dfeg4ey1qgZ7RRLQ8TRzjM8Q4Xk"
TELEGRAM_CHAT_ID = "1267686212"

def send_telegram_alert(patient_name, medicine_name, scheduled_time):
    """Sends a native medical push alert to the caregiver's Telegram account."""
    message = (
        f"🚨 *YACAPSULE DISPENSER ALERT*\n\n"
        f"👩‍⚕️ *Attention Caregiver:*\n"
        f"Medication is due and requires dispensing!\n\n"
        f"👤 *Patient:* {patient_name}\n"
        f"💊 *Medication:* {medicine_name}\n"
        f"⏰ *Scheduled Time:* {scheduled_time}\n\n"
        f"⚠️ _Please verify the patient scans their RFID card at the physical dispenser unit._"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info(f"Telegram mobile push alert successfully dispatched for {patient_name}.")
        else:
            logger.error(f"Telegram API responded with error status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to transmit Telegram message due to connectivity issue: {e}")

# ---------- GOOGLE SHEETS FUNCTION ----------
def save_logs_to_sheets():
    """Reads the yacapsule.log file and uploads to a new worksheet in Google Sheets."""
    try:
        # 1. Authenticate using credentials.json
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)

        # 2. Open the spreadsheet using SPREADSHEET_ID from config.py
        spreadsheet = client.open_by_key(config.SPREADSHEET_ID)

        # 3. Create a unique worksheet name based on the current timestamp
        current_time_ph = get_ph_time()
        worksheet_name = f"Log_Saved_on_{current_time_ph.strftime('%Y-%m-%d_%H-%M-%S')}"

        # 4. Check if a worksheet with this name already exists
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
            # Worksheet already exists, do nothing or append data
            return {'success': True, 'message': f'Data already saved to worksheet: {worksheet_name}'}
        except gspread.exceptions.WorksheetNotFound:
            # Create a new worksheet
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1, cols=4)
            worksheet.append_row(["Timestamp", "Source", "Level", "Message"]) # Add header

        # 5. Read the contents of yacapsule.log
        with open("yacapsule.log", "r") as log_file:
            log_lines = log_file.readlines()

        # 6. Parse and upload log lines (line by line to prevent bulk upload errors)
        rows_to_append = []
        for line in log_lines:
            try:
                # Basic parsing based on logging.basicConfig format
                timestamp_str, rest = line.split(" - ", 1)
                source, rest = rest.split(" - ", 1)
                level, message = rest.split(" - ", 1)
                rows_to_append.append([timestamp_str.strip(), source.strip(), level.strip(), message.strip()])
            except ValueError:
                # Handle lines that don't match the format (e.g., multiline errors, standard Flask output)
                rows_to_append.append([current_time_ph.strftime('%Y-%m-%d %H:%M:%S'), "Unknown", "OTHER", line.strip()])

        # Append all rows at once to be efficient
        worksheet.append_rows(rows_to_append)

        # 7. (Optional but Recommended) Clear the log file to start fresh for the next batch
        # This keeps the log file small and prevents duplication.
        open("yacapsule.log", "w").close()

        logger.info(f"Log history successfully saved to new worksheet: {worksheet_name}")
        return {'success': True, 'worksheet_name': worksheet_name}

    except FileNotFoundError:
        return {'success': False, 'error': 'credentials.json file not found. Place it in the app directory.'}
    except gspread.exceptions.APIError as e:
        return {'success': False, 'error': f'Google Sheets API Error: {str(e)}'}
    except Exception as e:
        logger.error(f"Failed to save logs to sheets: {str(e)}")
        return {'success': False, 'error': str(e)}

# ---------- DATABASE CONNECTION FUNCTIONS ----------
def create_connection():
    try:
        return mysql.connector.connect(
            host='localhost',
            user='root',
            password='ahlencarlronnel',
            database='ahlencarlronnel'
        )
    except mysql.connector.Error as e:
        logger.error(f"Database connection error: {e}") # Changed to logger
        return None

def ensure_tables():
    conn = create_connection()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(64) UNIQUE,
            password VARCHAR(128)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patient_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(128),
            age INT,
            medicine VARCHAR(128),
            schedule_time VARCHAR(10)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS removed_patients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(128),
            age INT,
            medicine VARCHAR(128),
            schedule_time VARCHAR(10)
        )
    """)
    
    # NEW INVENTORY TABLE AUTOMATION
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INT AUTO_INCREMENT PRIMARY KEY,
            medicine_name VARCHAR(255) UNIQUE,
            quantity INT NOT NULL
        )
    """)
    
    # Auto-populate inventory if it's currently empty
    cur.execute("SELECT COUNT(*) FROM inventory")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO inventory (medicine_name, quantity) VALUES 
            ('Losartan', 10),
            ('Amlodipine', 10),
            ('Metformin', 10)
        """)
        logger.info("Inventory table initialized with default stocks.")
        
    conn.commit()
    cur.close()
    conn.close()

# ---------- TIMEZONE FUNCTION ----------
def get_ph_time():
    philippines_tz = pytz.timezone('Asia/Manila')
    return datetime.datetime.now(philippines_tz)

# ---------- AUTH ROUTES ----------
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('patients'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        conn = create_connection()
        if not conn:
            return "Database connection failed", 500
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            logger.info(f"User '{username}' logged in.") # Changed to logger
            return redirect(url_for('patients'))
        logger.warning(f"Invalid login attempt for username '{username}'") # Changed to logger
        return "Invalid credentials", 401
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        conn = create_connection()
        if not conn:
            return "Database connection failed", 500
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"New user registered: {username}") # Changed to logger
            return redirect(url_for('login'))
        except mysql.connector.Error as e:
            logger.error(f"Registration error for {username}: {e}") # Changed to logger
            return f"Registration error: {e}", 400
    return render_template('register.html')

@app.route('/logout')
def logout():
    username = session.get('username')
    session.clear()
    logger.info(f"User '{username}' logged out.") # Changed to logger
    return redirect(url_for('login'))

# ---------- PATIENT ROUTES ----------
@app.route('/patients')
def patients():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = create_connection()
    if not conn:
        return "Database connection failed", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM patient_records")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('patients.html', patients=rows, username=session.get('username'))

@app.route('/edit_schedule/<int:patient_id>', methods=['GET', 'POST'])
def edit_schedule(patient_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = create_connection()
    if not conn:
        return "Database connection failed", 500
    cur = conn.cursor(dictionary=True)
    if request.method == 'POST':
        new_schedule = request.form.get('new_schedule_time', '')
        try:
            cur.execute("UPDATE patient_records SET schedule_time=%s WHERE id=%s", (new_schedule, patient_id))
            conn.commit()
            cur.close()
            conn.close()
            # Clear duplicate trigger preventing logic for this date and patient so a re-saved time can re-trigger on that same day
            current_date_str = get_ph_time().strftime('%Y-%m-%d')
            event_key = (patient_id, current_date_str)
            triggered_events.discard(event_key)
            logger.info(f"Schedule for patient ID {patient_id} updated to {new_schedule}") # Changed to logger
            return redirect(url_for('patients'))
        except Exception as e:
            cur.close()
            conn.close()
            logger.error(f"Error updating schedule for patient ID {patient_id}: {e}") # Changed to logger
            return f"Error updating schedule: {e}", 400
    cur.execute("SELECT * FROM patient_records WHERE id=%s", (patient_id,))
    patient = cur.fetchone()
    cur.close()
    conn.close()
    if not patient:
        return "Patient not found", 404
    return render_template('edit_schedule.html', patient=patient)

# Success page from manual dispenser check
@app.route('/dispense/<int:patient_id>', methods=['POST'])
def dispense(patient_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    logger.info(f"Success dispense confirm for patient ID {patient_id}.") # Changed to logger
    return render_template('success_dispense.html', patient_id=patient_id)

# ---------- INVENTORY ROUTE (NEW) ----------
@app.route('/inventory')
def inventory():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = create_connection()
    if not conn:
        return "Database connection failed", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM inventory")
    inventory_rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('inventory.html', inventory=inventory_rows, username=session.get('username'))

# ---------- ARCHIVE ROUTES ----------
@app.route('/archive/<int:patient_id>', methods=['POST'])
def archive_patient(patient_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = create_connection()
    if not conn:
        return "Database connection failed", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM patient_records WHERE id=%s", (patient_id,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "INSERT INTO removed_patients (name, age, medicine, schedule_time) VALUES (%s,%s,%s,%s)",
            (row['name'], row['age'], row['medicine'], row['schedule_time'])
        )
        cur.execute("DELETE FROM patient_records WHERE id=%s", (patient_id,))
        conn.commit()
        logger.info(f"Patient {row['name']} archived.") # Changed to logger
    cur.close()
    conn.close()
    return redirect(url_for('patients'))

@app.route('/removed_patients')
def removed_patients():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = create_connection()
    if not conn:
        return "Database connection failed", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM removed_patients")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('removed_patients.html', patients=rows, username=session.get('username'))

@app.route('/restore_patient/<int:patient_id>', methods=['POST'])
def restore_patient(patient_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = create_connection()
    if not conn:
        return "Database connection failed", 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM removed_patients WHERE id=%s", (patient_id,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "INSERT INTO patient_records (name, age, medicine, schedule_time) VALUES (%s,%s,%s,%s)",
            (row['name'], row['age'], row['medicine'], row['schedule_time'])
        )
        cur.execute("DELETE FROM removed_patients WHERE id=%s", (patient_id,))
        conn.commit()
        logger.info(f"Patient {row['name']} restored from archives.") # Changed to logger
    cur.close()
    conn.close()
    return redirect(url_for('removed_patients'))

# ---------- ALARM CHECKING ROUTE ----------
@app.route('/check_alarm')
def check_alarm():
    global triggered_events

    if 'user_id' not in session:
        return jsonify(triggered_patients=[])

    now_ph = get_ph_time()
    current_time_ph = now_ph.strftime('%H:%M')
    current_date_str = now_ph.strftime('%Y-%m-%d')

    conn = create_connection()
    if not conn:
        return jsonify(triggered_patients=[])
    cur = conn.cursor(dictionary=True)
    
    # UPDATED: Added 'medicine' to the database select statement
    cur.execute("SELECT id, name, medicine, schedule_time FROM patient_records WHERE schedule_time IS NOT NULL")
    patients = cur.fetchall()
    cur.close()
    conn.close()

    triggered_patients = []
    
    for row in patients:
        raw_time = str(row['schedule_time']).strip()
        if not raw_time:
            continue

        try:
            if len(raw_time) == 5:
                t = datetime.datetime.strptime(raw_time, "%H:%M")
            else:
                t = datetime.datetime.strptime(raw_time, "%H:%M:00")
            
            schedule_time = t.strftime("%H:%M")

            event_key = (row['id'], current_date_str)
            if schedule_time == current_time_ph and event_key not in triggered_events:
                # UPDATED: Included medicine key in payload passed to hardware
                triggered_patients.append({
                    'id': row['id'],
                    'name': row['name'],
                    'medicine': row['medicine'], 
                    'schedule_time': schedule_time
                })
                triggered_events.add(event_key)

                # NEW: Automatically message the caregiver on Telegram when matched!
                send_telegram_alert(
                    patient_name=row['name'],
                    medicine_name=row['medicine'],
                    scheduled_time=schedule_time
                )

        except ValueError as e:
            logger.error(f"Time format error for patient {row['name']}: {raw_time} | Error: {e}")

    if triggered_patients:
        try:
            logger.info(f"New patient schedules matched! Sending to hardware: {triggered_patients}")
            requests.post(
                "http://localhost:5001/hardware/start_alarm", 
                json={"patients": triggered_patients},
                timeout=5
            )
        except Exception as e:
            logger.error(f"Failed to communicate with hardware server: {e}")
            for p in triggered_patients:
                triggered_events.discard((p['id'], current_date_str))

    return jsonify(triggered_patients=triggered_patients)

# ---------- NEW GOOGLE SHEETS LOG ROUTE ----------
@app.route('/save_logs', methods=['POST'])
def handle_save_logs():
    """Route handled by the front-end AJAX button press."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    logger.info("Save to Google Sheets request received from frontend.") 
    result = save_logs_to_sheets()
    return jsonify(result)

# ---------- MAIN RUN ----------
if __name__ == '__main__':
    ensure_tables()
    app.run(host='0.0.0.0', port=5000, debug=True)
