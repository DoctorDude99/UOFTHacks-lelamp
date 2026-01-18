import sys
import os

# Add project root to path so we can import lelamp module
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import argparse

LAMP_ID = "lelamp"

def check_port_exists(port: str) -> bool:
    """Check if the serial port exists."""
    return os.path.exists(port)

def main():
    parser = argparse.ArgumentParser(description="Setup motors for LeLamp follower")
    parser.add_argument('--port', type=str, required=True, help='Serial port for the lamp')
    parser.add_argument('--voltage', type=str, default='7.4', choices=['7.4', '12'],
                       help='Servo voltage: 7.4V or 12V (default: 7.4)')
    args = parser.parse_args()

    # Check if port exists first
    if not check_port_exists(args.port):
        print(f"\n❌ ERROR: Motor driver port not found: {args.port}")
        print("")
        print("Please check:")
        print("  1. Motor driver USB cable is connected to the Raspberry Pi")
        print("  2. Motor driver has external power connected (7.4V or 12V)")
        print("  3. The udev rules are installed (reboot after install)")
        print("")
        print("If the motor driver is connected, try:")
        print("  ls /dev/ttyUSB* /dev/ttyACM* /dev/lelamp 2>/dev/null")
        print("")
        sys.exit(1)

    # Convert voltage to min/max voltage limits
    if args.voltage == '7.4':
        min_voltage = 45  # 4.5V
        max_voltage = 80  # 8.0V
    else:  # 12V
        min_voltage = 95   # 9.5V
        max_voltage = 135  # 13.5V

    # Progress feedback during slow initialization
    print("Initializing motor bus connection...")
    print(f"  Port: {args.port}")
    print(f"  Voltage config: {args.voltage}V")
    print("  (This may take a few seconds...)")
    print("")
    sys.stdout.flush()

    try:
        # Import here to show progress before the slow import
        from lelamp.follower.lelamp_follower import LeLampFollower, LeLampFollowerConfig

        config = LeLampFollowerConfig(
            port=args.port,
            id=LAMP_ID,
        )

        print("Creating motor controller instance...")
        sys.stdout.flush()

        leader = LeLampFollower(config)

        print("Motor controller ready!")
        print("")
        sys.stdout.flush()

        leader.setup_motors(min_voltage_limit=min_voltage, max_voltage_limit=max_voltage)

    except IndexError as e:
        print(f"\n❌ ERROR: Failed to initialize motor controller")
        print("")
        print("This usually means:")
        print("  1. No motors are connected to the motor driver")
        print("  2. Motor driver doesn't have external power")
        print("  3. Motors are not responding on the bus")
        print("")
        print("Please check:")
        print("  - External power supply is connected to motor driver")
        print("  - At least one motor is connected to the bus")
        print("  - Motor cables are properly seated")
        print("")
        print(f"Technical error: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("")
        print("If the motor driver is connected but not detected:")
        print("  1. Try unplugging and replugging the USB cable")
        print("  2. Make sure external power is connected")
        print("  3. Reboot the Raspberry Pi")
        print("")
        sys.exit(1)

if __name__ == "__main__":
    main()
