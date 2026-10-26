"""Compatibility helpers for OpenCV 3 and 4 APIs."""

import cv2


def find_contours(image, mode, method):
    result = cv2.findContours(image, mode, method)
    if len(result) == 3:
        _, contours, hierarchy = result
    else:
        contours, hierarchy = result
    return contours, hierarchy
