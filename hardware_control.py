from flask import Flask, jsonify
from flask_cors import CORS
import RPi.GPIO as GPIO
from mfrc522 import MFRC522
import threading
import time

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
rfid_active = False

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
    global rfid_active
    print("RFID scanner ready (inactive until alarm)")
    while True:
        (status, TagType) = reader.MFRC522_Request(reader.PICC_REQIDL)
        if status == reader.MI_OK:
            (status, uid) = reader.MFRC522_Anticoll()
            if status == reader.MI_OK:
                card_id = int("".join([str(i) for i in uid]))
                if rfid_active:
                    if card_id == AUTHORIZED_CARD:
                        print("Access Granted")
                        dispense_medicine()
                        time.sleep(2)
                    else:
                        print("Access Denied")
                        time.sleep(1)
                else:
                    time.sleep(0.1)
        time.sleep(0.1)

# Start RFID scanning in background
threading.Thread(target=rfid_loop, daemon=True).start()

# ----------------------------
# Flask Routes
# ----------------------------
@app.route('/')
def index():
    return "Hardware Control API Running"

@app.route('/hardware/start_alarm', methods=['POST'])
def api_start_alarm():
    global rfid_active
    try:
        print("ALARM ON: Physical buzzer active, RFID enabled")
        rfid_active = True
        GPIO.output(buzzer_pin, True)
        time.sleep(5)  # buzzer duration
        GPIO.output(buzzer_pin, False)
        rfid_active = False
        print("ALARM OFF: RFID disabled")
        return jsonify({'success': True, 'message': 'Buzzer triggered and RFID active'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/hardware/dispense', methods=['POST'])
def api_dispense():
    success = dispense_medicine()
    return jsonify({'success': success})

@app.route('/hardware/stop_alarm', methods=['POST'])
def api_stop_alarm():
    GPIO.output(buzzer_pin, False)
    return jsonify({'success': True, 'message': 'Buzzer stopped'})

# ----------------------------
# Run Flask
# ----------------------------
if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5001, debug=True)
    finally:
        pwm_servo.stop()
        GPIO.cleanup()
