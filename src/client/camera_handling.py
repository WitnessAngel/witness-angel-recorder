import cv2
import numpy as np
import logging

logger = logging.getLogger()


def display_video_stream(camera_url: str):
    cap = cv2.VideoCapture(camera_url)
    assert cap.isOpened(), "Error opening video stream"

    while cap.isOpened():
        ret, frame = cap.read()

        cv2.imshow('frame', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
