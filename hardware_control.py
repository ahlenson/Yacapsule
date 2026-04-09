from flask import Flask, jsonify, request
from flask_cors import CORS
import RPi.GPIO as GPIO
from mfrc522 import MFRC522
import threading
import time
from collections import deque

app = Flask(__name__)
CORS(app)

# ----------------------------
# GPIO Setup
# ----------------------------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Servo
servo_pin = 18
GPIO.setup(servo_pin, GPIO.OUT)
pwm_servo = GPIO.PWM(servo_pin, 50)
pwm_servo.start(0)

# Buzzer (physical)
buzzer_pin = 17
GPIO.setup(buzzer_pin, GPIO.OUT)
GPIO.output(buzzer_pin, False)

# RFID
reader = MFRC522()
AUTHORIZED_CARD = 384939185137

patient_queue = deque()
rfid_active = False 
processing = False

# ----------------------------
# Servo Functions
# ----------------------------
def set_servo_angle(angle):
    duty = 2 + (angle / 18)
    pwm_servo.ChangeDutyCycle(duty)
    time.sleep(0.5)
    pwm_servo.ChangeDutyCycle(0)

def dispense_medicine():
    print("Dispensing medicine...")
    set_servo_angle(180)
    time.sleep(1)
    set_servo_angle(0)
    print("Dispensing complete")
    return True

# ----------------------------
# RFID Thread
# ----------------------------
def rfid_loop():
    global rfid_active, patient_queue, processing
    print("RFID scanner ready...")

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
                    print("Access Granted")

                    if patient_queue:
                        patient = patient_queue.popleft()
                        print("Dispensing for:", patient['name'])

                        dispense_medicine()

                        print("Remaining queue:", len(patient_queue))

                        # If queue empty → stop system
                        if not patient_queue:
                            print("Queue finished. Stopping system.")
                            GPIO.output(buzzer_pin, False)
                            rfid_active = False
                            processing = False
                    else:
                        print("Queue empty already")
                else:
                    print("Access Denied")
                    
                time.sleep(2) # Cooldown to prevent spam reading the same card

        time.sleep(0.1)

# ----------------------------
# Routes
# ----------------------------
@app.route('/')
def home():
    return "Hardware server is running"

@app.route('/hardware/start_alarm', methods=['POST'])
def api_start_alarm():
    global rfid_active, patient_queue, processing

    try:
        data = request.get_json()
        patients = data.get("patients", [])

        if not patients:
            return jsonify({'success': False, 'message': 'No patients received'})

        print("Received patients:", patients)

        # Add to FIFO queue
        for p in patients:
            patient_queue.append(p)

        print("Queue size:", len(patient_queue))

        # Activate system
        rfid_active = True
        processing = True
        GPIO.output(buzzer_pin, True)

        return jsonify({'success': True, 'queue_length': len(patient_queue)})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ----------------------------
# Run Flask
# ----------------------------
if __name__ == '__main__':
    try:
        # Daemon thread closes automatically when the main program stops
        threading.Thread(target=rfid_loop, daemon=True).start()
        # use_reloader=False prevents Flask from running twice and crashing the GPIO threading
        app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
    finally:
        pwm_servo.stop()
        GPIO.cleanup()
