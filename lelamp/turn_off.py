import sys
import os
import argparse

sys.path.append(os.path.dirname(__file__))

from service.rgb import RGBService
from follower import LeLampFollower, LeLampFollowerConfig
from service.config_utils import load_config

LAMP_ID = "lelamp"

def turn_off(port: str):
    # Initialize robot connection
    robot_config = LeLampFollowerConfig(port=port, id=LAMP_ID)
    robot = LeLampFollower(robot_config)

    # Initialize RGB service
    rgb_service = RGBService()

    try:
        # Connect to robot
        print(f"Connecting to robot on port {port}...")
        robot.connect(calibrate=False)
        print("Robot connected successfully")

        # Start RGB service
        rgb_service.start()

        # Turn off LED
        print("Turning off LED")
        rgb_service.dispatch("solid", (0, 0, 0))

        print("Turn off complete")

    except Exception as e:
        print(f"Error during turn off: {e}")
    finally:
        # Clean up connections
        if robot.is_connected:
            print("Disconnecting robot...")
            robot.disconnect()
            print("Robot disconnected")

        rgb_service.stop()

def main():
    # Load saved config
    saved_port = load_config()

    parser = argparse.ArgumentParser(description="Turn off LeLamp LED and disconnect robot")
    parser.add_argument('--port', type=str, default=saved_port, help='Serial port for the lamp')
    args = parser.parse_args()

    if not args.port:
        parser.error("Please provide --port explicitly or run calibration first.")

    turn_off(args.port)

if __name__ == "__main__":
    main()
