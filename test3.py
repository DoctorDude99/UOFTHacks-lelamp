import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from lelamp.service.rgb import RGBService
from lelamp.service.base import Priority
from lelamp.functions.animation_functions import AnimationFunctions

def habit_completed():
    print("Task completed!")
    
    rgb_service = RGBService()
    rgb_service.start()
    animationFunction = AnimationFunctions()
    
    try:
        print("Testing solid green...")
        rgb_service.dispatch("solid", (0, 255, 0))
        time.sleep(2)

        print("Starting dance animation...")
        animationFunction.start_dancing()
        time.sleep(5)
        animationFunction.stop_dancing()
        animationFunction.play_recording("happy-wiggle")
        time.sleep(5)
        animationFunction.stop_dancing()
        animationFunction.play_recording("dancing1")
        time.sleep(5)
        
        # print("Testing paint pattern...")
        # colors = [
        #     (255, 0, 0),    # Red
        #     (0, 255, 0),    # Green
        #     (0, 0, 255),    # Blue
        #     (255, 255, 0),  # Yellow
        #     (255, 0, 255),  # Magenta
        # ] * 8  # Repeat pattern
        
        # rgb_service.dispatch("paint", colors)
        # time.sleep(3)
        
        # print("Testing priority - high priority solid should override paint...")
        # rgb_service.dispatch("paint", [(255, 255, 255)] * 40)  # White
        # rgb_service.dispatch("solid", (255, 0, 0), Priority.HIGH)  # High priority red
        # time.sleep(2)
        
        print("Clearing...")
        rgb_service.clear()
        time.sleep(1)
        
    finally:
        rgb_service.stop()
        animationFunction.stop_dancing()
        print("Task completed test finished!")

if __name__ == "__main__":
    habit_completed()