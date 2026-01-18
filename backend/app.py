# imports
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import anims

from ultralytics import YOLO
import cv2
import math
import time

# ---- FLASK SETUP ----
app = Flask(__name__)
CORS(app)

#global TARGET_CLASS_ID

@app.route("/api/habits", methods=["POST"]) 
def receive_data(): 
    global TARGET_CLASS_ID 
    data = request.json 
    TARGET_CLASS_ID = data.get("target", TARGET_CLASS_ID) 
    print("New target class:", TARGET_CLASS_ID) 
    return jsonify({ "status": "received", "target": TARGET_CLASS_ID })

def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False)

threading.Thread(target=run_flask, daemon=True).start()
# start webcam
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

# model
model = YOLO("yolo-Weights/yolov8n.pt", verbose=False)

# object classes
classNames = ["person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck", "boat",
              "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
              "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
              "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat",
              "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
              "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli",
              "carrot", "hot dog", "pizza", "donut", "cake", "chair", "sofa", "pottedplant", "bed",
              "diningtable", "toilet", "tvmonitor", "laptop", "mouse", "remote", "keyboard", "cell phone",
              "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
              "teddy bear", "hair drier", "toothbrush"
              ]
COOLDOWN = 3   # seconds
last_increment_time = 0

prev_object_present = False

TARGET_CLASS_ID = "bottle"
goal_frequency = 5

counter = 0



detections = []
while True:
    success, img = cap.read()
    results = model(img, stream=True)

    # coordinates
    for r in results:
        boxes = r.boxes

        for box in boxes:
            # bounding box
            x1, y1, x2, y2 = box.xyxy[0]
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2) # convert to int values

            # put box in cam
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 3)

            # confidence
            confidence = math.ceil((box.conf[0]*100))/100
            #print("Confidence --->",confidence)

            # habit counter

            # class name
            cls = int(box.cls[0])
            print("Class name -->", classNames[cls])
            if TARGET_CLASS_ID ==  classNames[cls]:
                print("found")

            # object details
            org = [x1, y1]
            font = cv2.FONT_HERSHEY_SIMPLEX
            fontScale = 1
            color = (255, 0, 0)
            thickness = 2

            cv2.putText(img, classNames[cls], org, font, fontScale, color, thickness)
            #print(time.time())

            


            # ---- YOUR DETECTION CODE ----
            # Example: detections = YOLO output filtered to your object

            cls_id = int(box.cls[0])
            label = model.names[cls_id]
            conf = float(box.conf[0])

            object_present = False

            if confidence > 0.6 and classNames[cls] == TARGET_CLASS_ID:
                object_present = True


            current_time = time.time()

            object_just_appeared = object_present and not prev_object_present

            current_time = time.time()

            object_just_appeared = object_present and not prev_object_present

            if object_just_appeared and current_time - last_increment_time >= COOLDOWN:
                counter += 1
                last_increment_time = current_time
                print("Counter:", counter)

            prev_object_present = object_present

            prev_object_present = object_present
            cv2.putText(img, str(counter), org, font, fontScale, color, thickness)

            if counter == goal_frequency:
                anims.frequency_reached_animation()

    cv2.imshow('Webcam', img)
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()