"""
Module B - helper: grab one frame from the camera source and draw a coordinate
grid on it, so you can visually pick pixel coordinates for your zone polygon.

Usage:
    python grab_frame.py --source "http://192.168.1.5:8080/video"

This saves a file called grid_frame.jpg in the same folder. Open that image
and note the (x, y) pixel coordinates of the corners of your restricted zone
using the grid lines as a guide.
"""

import argparse
import cv2


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, required=True,
                         help="Same source string you use for track_test.py")
    parser.add_argument("--grid_spacing", type=int, default=50,
                         help="Pixels between grid lines (default 50)")
    return parser.parse_args()


def main():
    args = parse_args()
    source = 0 if args.source == "0" else args.source

    cap = cv2.VideoCapture(source)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("Couldn't read a frame from that source. Check the URL/connection.")
        return

    h, w = frame.shape[:2]
    print(f"Frame size: width={w}, height={h}")

    # Draw vertical grid lines + x-axis labels
    for x in range(0, w, args.grid_spacing):
        cv2.line(frame, (x, 0), (x, h), (0, 255, 0), 1)
        cv2.putText(frame, str(x), (x + 2, 15), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, (0, 255, 0), 1)

    # Draw horizontal grid lines + y-axis labels
    for y in range(0, h, args.grid_spacing):
        cv2.line(frame, (0, y), (w, y), (0, 255, 0), 1)
        cv2.putText(frame, str(y), (2, y + 12), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, (0, 255, 0), 1)

    cv2.imwrite("grid_frame.jpg", frame)
    print("Saved grid_frame.jpg - open it and read off coordinates using the "
          "green grid lines (labeled every {}px).".format(args.grid_spacing))


if __name__ == "__main__":
    main()
