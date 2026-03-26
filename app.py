from flask import Flask, render_template, request, redirect, session, jsonify, url_for
import mysql.connector
import requests
import datetime
import pytz  # Import pytz for handling time zones

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

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

# Function to get the current time in the Philippines
def getCurrentTimePH():
    philippines_tz = pytz.timezone('Asia/Manila')  # Set the Philippines time zone
    now = datetime.datetime.now(philippines_tz)    # Get current time in PH time zone
    return now.strftime('%H:%M')                    # Format as 'HH:MM'

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
    try:
        # Send request to stop the buzzer
        requests.post("http://localhost:5001/hardware/stop_alarm")
        # Continue with the dispensing logic
        r = requests.post("http://localhost:5001/hardware/dispense", timeout=5)
        if r.ok and r.json().get('success') is True:
            return render_template('success_dispense.html', patient_id=patient_id)
        return "Dispensing error", 400
    except Exception as e:
        return f"Hardware call failed: {e}", 500

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

# Alarm logic
triggered = False  # Add a flag to track if the alarm was triggered
@app.route('/check_alarm')
def check_alarm():
    global triggered
    if 'user_id' not in session:
        return jsonify(triggered_patients=[])
    
    current_time = getCurrentTimePH()  # HH:MM
    connection = create_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, name, schedule_time FROM patient_records WHERE schedule_time IS NOT NULL
    """)
    patients = cursor.fetchall()
    cursor.close()
    connection.close()
    
    triggered_patients = []
    for row in patients:
        schedule_time = row['schedule_time']
        formatted_schedule_time = None
        if isinstance(schedule_time, datetime.timedelta):
            hours, remainder = divmod(schedule_time.seconds, 3600)
            minutes = remainder // 60
            formatted_schedule_time = f"{hours:02}:{minutes:02}"
        elif isinstance(schedule_time, str):
            formatted_schedule_time = schedule_time[:5]

        if formatted_schedule_time and formatted_schedule_time == current_time and not triggered:
            triggered_patients.append({
                'id': row['id'],
                'name': row['name'],
                'schedule_time': formatted_schedule_time
            })
            try:
                # Trigger hardware to start physical buzzer and enable RFID
                requests.post("http://localhost:5001/hardware/start_alarm")
                triggered = True  # prevent multiple triggers
            except Exception as e:
                print(f"Failed to trigger alarm: {e}")
    
    return jsonify(triggered_patients=triggered_patients)

if __name__ == '__main__':
    ensure_tables()
    app.run(host='0.0.0.0', port=5000, debug=True)
