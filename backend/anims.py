import argparse
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from service.motors import MotorsService
from service.base import Priority

def frequency_reached_animation():

    motors_service = MotorsService("/dev/ttyACM0")
    # port=args.port
    # "/dev/ttyACM0"
    motors_service.start()
    try:
        recordings = motors_service.get_available_recordings()
        if recordings:
            print(f"Available recordings: {recordings}")
            index = 0
            for recording in recordings:
                print(f"{index} : {recording}")
                index += 1
            print("Getting available recordings...")
            recordings = motors_service.get_available_recordings()
            print(f"Playing first recording: {recordings[4]}")
            motors_service.dispatch("play", recordings[4])
            
            # Wait for playback to complete
            motors_service.wait_until_idle(timeout=5)
            print("Playback completed!")
        else:
            print("No recordings found. Create some recordings first.")
       
        
        # Wait for playback to complete
        motors_service.wait_until_idle(timeout=5)
        print("Playback completed!")
        
    finally:
        motors_service.stop()
        
if __name__ == "__main__":
    frequency_reached_animation()