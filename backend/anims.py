import argparse
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from lelamp.service.motors import MotorsService
from lelamp.service.base import Priority

def frequency_reached_animation():
    parser = argparse.ArgumentParser(description="Test Motors Service")
    parser.add_argument('--port', type=str, required=True, help='Serial port for the lamp')
    args = parser.parse_args()

    motors_service = MotorsService("/dev/ttyACM0")
    motors_service.start()
    try:
        print("Getting available recordings...")
        recordings = motors_service.get_available_recordings()
        print(f"Playing first recording: {recordings[int(4)]}")
        motors_service.dispatch("play", recordings[int(4)])
        
        # Wait for playback to complete
        motors_service.wait_until_idle(timeout=5)
        print("Playback completed!")
        
    finally:
        motors_service.stop()
        
