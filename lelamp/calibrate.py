#!/usr/bin/env python

import argparse
import logging
import json
import os
from .follower import LeLampFollower, LeLampFollowerConfig
from .leader import LeLampLeader, LeLampLeaderConfig
from .service.config_utils import save_config

LAMP_ID = "lelamp"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calibrate_all(port: str) -> None:

    logger.info(f"Starting calibration on port: {port}")

    follower_config = LeLampFollowerConfig(
        port=port,
        id=LAMP_ID,
    )
    follower = LeLampFollower(follower_config)

    try:
        follower.connect(calibrate=False)
        follower.calibrate()

        logger.info(f"Calibration data saved to {follower.calibration_fpath}")
        logger.info("Calibration completed successfully")
        logger.info("Both follower and leader will use the same calibration file")

    except Exception as e:
        logger.error(f"Calibration failed: {e}")
        raise
    finally:
        if follower.is_connected:
            follower.disconnect()


def calibrate_arm(port: str) -> None:
    """Calibrate the robot arm (applies to both leader and follower)."""
    logger.info(f"Starting arm calibration on port: {port}")

    config = LeLampFollowerConfig(
        port=port,
        id=LAMP_ID,
    )

    arm = LeLampFollower(config)

    try:
        # Connect and calibrate
        arm.connect(calibrate=False)
        arm.calibrate()
        logger.info("Arm calibration completed successfully")
    except Exception as e:
        logger.error(f"Arm calibration failed: {e}")
        raise
    finally:
        if arm.is_connected:
            arm.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Calibrate LeLamp robot follower and leader")
    parser.add_argument('--port', type=str, required=True, help='Serial port for the lamp')
    parser.add_argument('--config-only', action='store_true', help='Only update config file with port, skip calibration')
    args = parser.parse_args()

    try:
        if args.config_only:
            # Just save the config without running calibration
            print("\n" + "="*50)
            print("UPDATING CONFIG")
            print("="*50)
            save_config(args.port)
            print("\n" + "="*50)
            print("CONFIG UPDATED SUCCESSFULLY")
            print("="*50)
        else:
            # Run full calibration
            print("\n" + "="*50)
            print("DEFAULT CALIBRATION")
            print("="*50)
            calibrate_all(args.port)
            save_config(args.port)

            print("\n" + "="*50)
            print("CALIBRATION COMPLETED SUCCESSFULLY")
            print("="*50)

    except Exception as e:
        logger.error(f"Process failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())