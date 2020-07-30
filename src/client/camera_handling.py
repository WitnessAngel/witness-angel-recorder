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


def write_video_stream(camera_url: str):
    cap = cv2.VideoCapture(camera_url)
    assert cap.isOpened(), "Error opening video stream"

    frame_width = int(cap.get(3))
    frame_height = int(cap.get(4))
    out = cv2.VideoWriter('saved_video_stream/outpy.avi', cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), 10, (frame_width, frame_height))

    while cap.isOpened():
        ret, frame = cap.read()
        out.write(frame)
        cv2.imshow('frame', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    out.release()

    cv2.destroyAllWindows()
