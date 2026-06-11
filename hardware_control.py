from flask import Flask, jsonify
from flask_cors import CORS
import RPi.GPIO as GPIO
from mfrc522 import MFRC522
import threading
import time
from flask import request
from collections import deque
import logging  # Import logging module
import mysql.connector # NEW: MySQL Connector imported for inventory updates

# ---------- LOGGING CONFIGURATION ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("yacapsule.log"), 
        logging.StreamHandler()              
    ]
)
logger = logging.getLogger("HARDWARE_CONTROL_PY") 

app = Flask(__name__)
CORS(app)

# ----------------------------
# GPIO Setup
# ----------------------------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Servo (MG90S) on pin 18
servo_pin = 18
GPIO.setup(servo_pin, GPIO.OUT)
pwm_servo = GPIO.PWM(servo_pin, 50)
pwm_servo.start(0)

# Buzzer on pin 17
buzzer_pin = 17
GPIO.setup(buzzer_pin, GPIO.OUT)
GPIO.output(buzzer_pin, False) 

# RFID Setup
reader = MFRC522()
AUTHORIZED_CARD = 1383413209116

# State management 
patient_queue = deque()
rfid_active = False 
processing = False  

# ----------------------------
# NEW: MYSQL DATABASE UPDATES FOR INVENTORY
# ----------------------------
def create_db_connection():
    """Establishes database connection matching app.py parameters."""
    try:
        return mysql.connector.connect(
            host='localhost',
            user='root',
            password='ahlencarlronnel',
            database='ahlencarlronnel'
        )
    except mysql.connector.Error as e:
        logger.error(f"Hardware Database connection error: {e}")
        return None

def deduct_inventory(medicine_name):
    """Finds matching medicine entry and automatically reduces stock count by 1."""
    if not medicine_name:
        logger.warning("No medicine specified for deduction.")
        return

    conn = create_db_connection()
    if not conn:
        return

    try:
        cur = conn.cursor()
        # Using LOWER() matching to avoid problems with casing (e.g., 'metformin' vs 'Metformin')
        sql = "UPDATE inventory SET quantity = quantity - 1 WHERE LOWER(medicine_name) = LOWER(%s)"
        cur.execute(sql, (medicine_name.strip(),))
        conn.commit()
        logger.info(f"Inventory Auto-Deduction Complete: 1 pill of '{medicine_name}' removed.")
        cur.close()
    except Exception as e:
        logger.error(f"Failed to execute inventory deduction query for '{medicine_name}': {e}")
    finally:
        conn.close()

# ----------------------------
# Servo Functions
# ----------------------------
def set_servo_angle(angle):
    duty = 2 + (angle / 18)
    pwm_servo.ChangeDutyCycle(duty)
    time.sleep(0.5)
    pwm_servo.ChangeDutyCycle(0) 

def dispense_medicine():
    logger.info("Servo rotating: Dispensing medicine...") 
    set_servo_angle(90)
    time.sleep(1)
    set_servo_angle(0)
    logger.info("Servo reset: Dispensing complete") 
    return True

# ----------------------------
# RFID Thread
# ----------------------------
def rfid_loop():
    global rfid_active, patient_queue, processing

    logger.info("RFID scanner thread is running and ready...") 

    while True:
        if not rfid_active:
            time.sleep(0.5)
            continue

        (status, TagType) = reader.MFRC522_Request(reader.PICC_REQIDL)

        if status == reader.MI_OK:
            (status, uid) = reader.MFRC522_Anticoll()

            if status == reader.MI_OK:
                card_id = int("".join([str(i) for i in uid]))

                if card_id == AUTHORIZED_CARD:
                    logger.info(f"Authorized card detected (UID: {card_id}). Access Granted.") 

                    if patient_queue:
                        patient = patient_queue.popleft() 
                        logger.info(f"Dispensing for: {patient['name']} (Schedule: {patient['schedule_time']})") 

                        # Physically dispense pill
                        dispense_medicine()

                        # NEW: Run automatic database stock update
                        med_to_deduct = patient.get('medicine')
                        deduct_inventory(med_to_deduct)

                        logger.info(f"Dispense complete for {patient['name']}. Remaining queue: {len(patient_queue)}") 

                        if not patient_queue:
                            logger.info("Patient queue finished. Stopping system alarm and resetting state.") 
                            GPIO.output(buzzer_pin, False)
                            rfid_active = False
                            processing = False

                    else:
                        logger.warning("Queue empty already. No patient next in line for dispense.") 

                else:
                    logger.warning(f"Unauthorized card detected (UID: {card_id}). Access Denied.") 

                time.sleep(2)

        time.sleep(0.1)
        
        
@app.route('/')
def home():
    return "Hardware server is running"

# ----------------------------
# ROUTE FOR ALARM CONTROL
# ----------------------------
@app.route('/hardware/start_alarm', methods=['POST'])
def api_start_alarm():
    global rfid_active, patient_queue, processing

    try:
        data = request.get_json()
        patients = data.get("patients", [])

        if not patients:
            return jsonify({'success': False, 'message': 'No new patients received in request'})

        logger.info(f"Start Alarm request received. Patients added: {patients}") 

        for p in patients:
            patient_queue.append(p)

        logger.info(f"Updated patient queue size: {len(patient_queue)}") 

        if not rfid_active:
             logger.info("Activating system hardware: Buzzer ON, RFID Listening...") 
             rfid_active = True
             processing = True
             GPIO.output(buzzer_pin, True)

        return jsonify({'success': True, 'queue_length': len(patient_queue)})

    except Exception as e:
        logger.error(f"Hardware server error processing start_alarm: {str(e)}") 
        return jsonify({'success': False, 'error': str(e)})
    

# ----------------------------
# Main Hardware Server Run
# ----------------------------
if __name__ == '__main__':
    try:
        threading.Thread(target=rfid_loop, daemon=True).start()
        app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False) 
    finally:
        logger.info("Hardware server shutting down. GPIO cleanup...")
        pwm_servo.stop()
        GPIO.cleanup()
