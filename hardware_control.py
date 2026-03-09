from flask import Flask, jsonify
from flask_cors import CORS
import RPi.GPIO as GPIO
import subprocess
import time

app = Flask(__name__)
CORS(app)

# --- GPIO & Servo Setup ---
GPIO.setmode(GPIO.BCM)
servo_pin = 18
GPIO.setup(servo_pin, GPIO.OUT)
pwm_servo = GPIO.PWM(servo_pin, 50)
pwm_servo.start(0)

def dispense_medicine():
    try:
        print('Dispensing...')
        pwm_servo.ChangeDutyCycle(7.5)  # Move the servo to open position
        time.sleep(1)
        pwm_servo.ChangeDutyCycle(2.5)  # Move the servo back to closed position
        time.sleep(1)
        pwm_servo.ChangeDutyCycle(0)    # Stop PWM signal
        print('Dispensing complete.')
        return True
    except Exception as e:
        print(f"Dispensing error: {e}")
        return False

# Route to play alarm
@app.route('/hardware/alarm', methods=['POST'])
def play_alarm():
    try:
        print("Playing alarm sound...")
        subprocess.Popen(['ffplay', '-nodisp', '-autoexit', '/home/hp/static/alarm.mp3'])
        return jsonify({'success': True})
    except Exception as e:
        print(f"Alarm play error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/hardware/dispense', methods=['POST'])
def api_dispense():
    success = dispense_medicine()
    return jsonify({'success': success})

@app.route('/hardware/stop_alarm', methods=['POST'])
def stop_alarm():
    try:
        # Add logic to stop the buzzer here
        print("Buzzer stopped.")  # Replace with actual GPIO code to stop buzzer if needed
        return jsonify({'success': True, 'message': 'Buzzer stopped'})
    except Exception as e:
        print(f"Failed to stop buzzer: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/')
def index():
    return 'Hardware control API is running.'

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5001, debug=True)
    finally:
        pwm_servo.stop()    # Stop the PWM signal for the servo
        GPIO.cleanup()      # Clean up GPIO pins when the app is closed
