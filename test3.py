import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from lelamp.service.rgb import RGBService
from lelamp.service.base import Priority
from lelamp.functions.animation_functions import AnimationFunctions
from lelamp.functions.vision_functions import VisionFunctions
from lelamp.service.motors import MotorsService
from lelamp.service.base import Priority

def habit_completed():
    # print("Task completed!")
    
    rgb_service = RGBService()
    rgb_service.start()
    animationFunction = AnimationFunctions()
    visionFunctions = VisionFunctions()
    
    try:
        print("Testing solid orange...")
        rgb_service.dispatch("solid", (235, 96, 21))
        time.sleep(2)

        print("Testing solid orange...")
        rgb_service.dispatch("solid", (235, 96, 21))
        time.sleep(2)

        print("Testing solid light blue...")
        rgb_service.dispatch("solid", (21, 231, 235))
        time.sleep(2)

    #     # tried and failed
    #     # print("Starting dance animation...")
    #     # animationFunction.start_dancing()
    #     # time.sleep(5)
    #     # animationFunction.stop_dancing()
    #     # animationFunction.play_recording("happy-wiggle")
    #     # time.sleep(5)
    #     # animationFunction.stop_dancing()
    #     # animationFunction.play_recording("dancing1")
    #     # time.sleep(5)

    #     visionFunctions.describe_scene()
    #     time.sleep(2)

    #     visionFunctions.get_scene_details()
    #     time.sleep(2)   

        
        
    #     # print("Testing paint pattern...")
    #     # colors = [
    #     #     (255, 0, 0),    # Red
    #     #     (0, 255, 0),    # Green
    #     #     (0, 0, 255),    # Blue
    #     #     (255, 255, 0),  # Yellow
    #     #     (255, 0, 255),  # Magenta
    #     # ] * 8  # Repeat pattern
        
    #     # rgb_service.dispatch("paint", colors)
    #     # time.sleep(3)
        
    #     # print("Testing priority - high priority solid should override paint...")
    #     # rgb_service.dispatch("paint", [(255, 255, 255)] * 40)  # White
    #     # rgb_service.dispatch("solid", (255, 0, 0), Priority.HIGH)  # High priority red
    #     # time.sleep(2)
        
    #     print("Clearing...")
    #     rgb_service.clear()
    #     time.sleep(1)
        
    finally:
         rgb_service.stop()
    #     animationFunction.stop_dancing()
    #     print("Task completed test finished!")

if __name__ == "__main__":
    habit_completed()