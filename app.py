from flask import Flask, render_template, request, redirect, session, jsonify, url_for
import mysql.connector
import requests
import datetime
import pytz

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Track triggered events to prevent spamming the hardware. 
# Format: {(patient_id, 'YYYY-MM-DD')}
triggered_events = set()

def create_connection():
    try:
        return mysql.connector.connect(
            host='localhost',
            user='root',
            password='ahlencarlronnel',
            database='ahlencarlronnel'
        )
    except mysql.connector.Error as e:
        print(f"DB Error: {e}")
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
    conn.commit()
    cur.close()
    conn.close()

# Function to get the full datetime object in PH time
def get_ph_time():
    philippines_tz = pytz.timezone('Asia/Manila')
    return datetime.datetime.now(philippines_tz)

# ---------- ROUTES ----------
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
            return redirect(url_for('patients'))
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
            return redirect(url_for('login'))
        except mysql.connector.Error as e:
            return f"Registration error: {e}", 400
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

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
            
            # Remove from triggered events so it can trigger again today if edited to a new time
            now = get_ph_time()
            current_date_str = now.strftime('%Y-%m-%d')
            global triggered_events
            triggered_events.discard((patient_id, current_date_str))

            return redirect(url_for('patients'))
        except Exception as e:
            cur.close()
            conn.close()
            return f"Error updating schedule: {e}", 400
    cur.execute("SELECT * FROM patient_records WHERE id=%s", (patient_id,))
    patient = cur.fetchone()
    cur.close()
    conn.close()
    if not patient:
        return "Patient not found", 404
    return render_template('edit_schedule.html', patient=patient)

@app.route('/dispense/<int:patient_id>', methods=['POST'])
def dispense(patient_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('success_dispense.html', patient_id=patient_id)

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
    cur.close()
    conn.close()
    return redirect(url_for('removed_patients'))


@app.route('/check_alarm')
def check_alarm():
    global triggered_events

    if 'user_id' not in session:
        return jsonify(triggered_patients=[])

    now = get_ph_time()
    current_date_str = now.strftime('%Y-%m-%d')
    # Strip seconds for accurate minute-level comparison
    current_time_obj = now.replace(second=0, microsecond=0) 

    connection = create_connection()
    if not connection:
        return jsonify(triggered_patients=[])
    
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, name, schedule_time FROM patient_records WHERE schedule_time IS NOT NULL")
    patients = cursor.fetchall()
    cursor.close()
    connection.close()

    triggered_patients = []

    for row in patients:
        raw_time = str(row['schedule_time']).strip()
        if not raw_time:
            continue

        try:
            # Handle both formats seamlessly (HH:MM vs HH:MM:SS)
            if len(raw_time) == 5:
                t = datetime.datetime.strptime(raw_time, "%H:%M")
            else:
                t = datetime.datetime.strptime(raw_time, "%H:%M:%S")
            
            # Map database schedule to today's date
            sched_time_obj = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            
            # Calculate difference in minutes
            diff_minutes = (current_time_obj - sched_time_obj).total_seconds() / 60.0

            # Tolerant triggering: if current time is exactly on, or up to 5 minutes AFTER schedule
            if 0 <= diff_minutes <= 5:
                event_key = (row['id'], current_date_str)
                
                if event_key not in triggered_events:
                    triggered_patients.append({
                        'id': row['id'],
                        'name': row['name'],
                        'schedule_time': t.strftime("%H:%M")
                    })
                    triggered_events.add(event_key)

        except Exception as e:
            print(f"Time parse error for {row['name']}: {raw_time} | Error: {e}")

    # Process hardware triggers only if we found new valid alarms
    if triggered_patients:
        try:
            print("Sending patients to hardware:", triggered_patients)
            requests.post(
                "http://localhost:5001/hardware/start_alarm",
                json={"patients": triggered_patients},
                timeout=5
            )
        except Exception as e:
            print("Hardware error:", e)
            # If the hardware server is down, remove from triggered_events so it tries again next loop!
            for p in triggered_patients:
                triggered_events.discard((p['id'], current_date_str))

    return jsonify(triggered_patients=triggered_patients)

if __name__ == '__main__':
    ensure_tables()
    app.run(host='0.0.0.0', port=5000, debug=True)
