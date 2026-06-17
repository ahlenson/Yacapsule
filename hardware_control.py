import time
import logging
import threading
from flask import Flask, request, jsonify
import mysql.connector
import requests
import datetime
import pytz

# Setup physical peripherals safely with emulated fallbacks
HARDWARE_AVAILABLE = False
logger_msg = ""
pwm = None
reader = None
bz = None

try:
    import RPi.GPIO as GPIO
    from mfrc522 import SimpleMFRC522
    import Adafruit_PCA9685
    from gpiozero import Buzzer  # Modern, thread-safe library for passive/active buzzers
    
    # Initialize PCA9685 Servo Controller
    pwm = Adafruit_PCA9685.PCA9685(address=0x40, busnum=1)
    pwm.set_pwm_freq(50)
    
    # 1. INITIALIZE THE BUZZER ON GPIO 13 (Physical Pin 33) - FIXED & PRESERVED
    BUZZER_PIN = 13 
    bz = Buzzer(BUZZER_PIN)
    bz.off()  # Keep it quiet at system start

    # 2. INITIALIZE THE RFID READER
    reader = SimpleMFRC522()
    
    HARDWARE_AVAILABLE = True
    logger_msg = "SUCCESS: All physical peripherals (PCA9685, MFRC522, GPIOZero Buzzer) bound successfully."

except Exception as e:
    HARDWARE_AVAILABLE = False
    logger_msg = f"CRITICAL INITIALIZATION ERROR: {str(e)}"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("hardware.log"), logging.StreamHandler()]
)
logger = logging.getLogger("HARDWARE_SERVICE")
print(logger_msg)

app = Flask(__name__)

# Core tracking queues
hardware_queue = []
queue_lock = threading.Lock()

SERVO_OPEN_PULSE = 400
SERVO_CLOSE_PULSE = 150

def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='ahlencarlronnel',
        database='ahlencarlronnel'
    )

def rotate_servo_channel(channel):
    if not HARDWARE_AVAILABLE:
        logger.info(f"[EMULATION] Rotating servo channel {channel} smoothly.")
        time.sleep(1.0)
        return
    try:
        logger.info(f"Engaging physical PCA9685 I2C register on channel {channel}")
        pwm.set_pwm(channel, 0, SERVO_OPEN_PULSE)
        time.sleep(1.2)
        pwm.set_pwm(channel, 0, SERVO_CLOSE_PULSE)
        time.sleep(0.5)
    except Exception as hardware_err:
        logger.error(f"Physical I2C Bus Exception on channel {channel}: {hardware_err}")

def log_dispense_to_db(patient_name, medicine_name, channel, dispense_type):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO dispense_records (patient_name, medicine_name, channel_used, dispense_type, timestamp)
            VALUES (%s, %s, %s, %s, NOW())
        """, (patient_name, medicine_name, channel, dispense_type))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Successfully stored database record for {patient_name}.")
    except Exception as db_err:
        logger.error(f"Failed to record dispense to DB: {db_err}")

def sync_to_central_cloud(patient_name, medicine_name, channel, dispense_type):
    payload = {
        "name": patient_name,
        "medicine": medicine_name,
        "channel": channel,
        "type": dispense_type
    }
    try:
        res = requests.post("http://localhost:5000/api/log_success", json=payload, timeout=3.0)
        if res.status_code == 200:
            logger.info("Cloud sheets sync report pushed successfully.")
        else:
            logger.warning(f"Central interface returned code: {res.status_code}")
    except Exception as e:
        logger.error(f"Cloud web synchronizer pipeline unreachable: {e}")

def pipeline_worker_thread():
    global hardware_queue, bz
    while True:
        tasks_to_process = []
        
        with queue_lock:
            if hardware_queue:
                tasks_to_process = list(hardware_queue)
                hardware_queue.clear()
        
        if tasks_to_process:
            logger.info(f"Alarm batch hit! Processing {len(tasks_to_process)} patient tasks collectively...")
            
            if HARDWARE_AVAILABLE:
                try:
                    # Force BCM mode and drive the pin high directly to bypass the RFID lock
                    GPIO.setmode(GPIO.BCM)
                    GPIO.setup(13, GPIO.OUT)
                    GPIO.output(13, GPIO.HIGH)
                    logger.info("Buzzer sounding for pending medications! Waiting for physical caregiver RFID tap...")
                except Exception as bz_err:
                    logger.error(f"Failed to sound buzzer via GPIOZero: {bz_err}")
            else:
                logger.info("[EMULATION] Buzzer is now BEEPING for the batch...")

            card_scanned = False
            while not card_scanned:
                if HARDWARE_AVAILABLE:
                    card_id, _ = reader.read_no_block()
                    if card_id is not None:
                        logger.info(f"Authorized RFID Tap Confirmed! ID: {card_id}")
                        card_scanned = True
                else:
                    time.sleep(3.0)
                    logger.info("[EMULATION] Mock RFID card tapped by supervisor.")
                    card_scanned = True
                
                time.sleep(0.1)

            if HARDWARE_AVAILABLE:
                try:
                    # Reset mode and pull low to completely silence it safely
                    GPIO.setmode(GPIO.BCM)
                    GPIO.setup(13, GPIO.OUT)
                    GPIO.output(13, GPIO.LOW)
                    logger.info("Buzzer silenced via GPIOZero.")
                except Exception as bz_close_err:
                    logger.error(f"Failed to silence buzzer safely: {bz_close_err}")
            else:
                logger.info("[EMULATION] Buzzer silenced.")

            for task in tasks_to_process:
                name = task.get('name')
                medicine = task.get('medicine')
                channel = task.get('hardware_channel', 0)
                dispense_type = task.get('type', 'scheduled')

                logger.info(f"Executing sequential rotation cycle on channel {channel} for {medicine} ({name})...")
                rotate_servo_channel(channel)
                
                log_dispense_to_db(name, medicine, channel, dispense_type)
                sync_to_central_cloud(name, medicine, channel, dispense_type)
                time.sleep(0.5)
            
        time.sleep(0.5)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify(status="healthy", hardware_ready=HARDWARE_AVAILABLE), 200

@app.route('/hardware/start_alarm', methods=['POST'])
def start_alarm():
    global hardware_queue
    data = request.get_json() or {}
    patients_list = data.get('patients', [])

    if not patients_list:
        return jsonify(success=False, error="Empty payload elements"), 400

    with queue_lock:
        for p in patients_list:
            p['type'] = p.get('type', 'scheduled')
            hardware_queue.append(p)
            logger.info(f"Task added to execution pipeline for {p.get('name')}")

    return jsonify(success=True, message=f"Queued {len(patients_list)} tasks successfully.")

if __name__ == '__main__':
    worker = threading.Thread(target=pipeline_worker_thread, daemon=True)
    worker.start()
    
    logger.info("Yacapsule Hardware Control Daemon starting on port 5001...")
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
