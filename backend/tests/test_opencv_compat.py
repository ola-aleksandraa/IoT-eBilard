import cv2

from app.engine.opencv_compat import find_contours


def test_find_contours_supports_opencv_three_return_values(monkeypatch):
    image = object()
    contours = [object()]
    hierarchy = object()
    monkeypatch.setattr(cv2, "findContours", lambda *args: (image, contours, hierarchy))

    assert find_contours(image, 1, 2) == (contours, hierarchy)


def test_find_contours_supports_opencv_four_return_values(monkeypatch):
    contours = [object()]
    hierarchy = object()
    monkeypatch.setattr(cv2, "findContours", lambda *args: (contours, hierarchy))

    assert find_contours(object(), 1, 2) == (contours, hierarchy)
