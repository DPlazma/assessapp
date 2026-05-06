"""Face detection and blur utilities using OpenCV YuNet DNN."""
import os
import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageOps

# Path to the YuNet ONNX model (bundled in the evidence app)
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
_YUNET_MODEL = os.path.join(_MODEL_DIR, "face_detection_yunet_2023mar.onnx")


def _auto_orient_cv(img_cv, image_path):
    """Apply EXIF orientation to an OpenCV image via PIL."""
    try:
        pil_img = Image.open(image_path)
        pil_oriented = ImageOps.exif_transpose(pil_img)
        if pil_oriented is None:
            return img_cv
        ow, oh = pil_img.size
        nw, nh = pil_oriented.size
        if (ow, oh) != (nw, nh) or pil_img.tobytes()[:100] != pil_oriented.tobytes()[:100]:
            arr = np.array(pil_oriented)
            if len(arr.shape) == 3 and arr.shape[2] == 3:
                return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            elif len(arr.shape) == 3 and arr.shape[2] == 4:
                return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)
            return arr
    except Exception:
        pass
    return img_cv


def detect_faces(image_path):
    """Detect faces using the YuNet DNN model (much more accurate than Haar).

    Falls back to Haar cascades if the YuNet model is unavailable.
    Returns a list of dicts: [{"x": int, "y": int, "w": int, "h": int}, ...]
    """
    img = cv2.imread(image_path)
    if img is None:
        return []

    img = _auto_orient_cv(img, image_path)
    h_orig, w_orig = img.shape[:2]

    # Scale down for faster detection on very large images
    max_dim = 1200
    scale = 1.0
    if max(h_orig, w_orig) > max_dim:
        scale = max_dim / max(h_orig, w_orig)
        img_det = cv2.resize(img, None, fx=scale, fy=scale,
                             interpolation=cv2.INTER_AREA)
    else:
        img_det = img

    h_det, w_det = img_det.shape[:2]

    # Try YuNet DNN first
    if os.path.isfile(_YUNET_MODEL):
        faces = _detect_yunet(img_det, w_det, h_det, scale)
        if faces:
            return faces

    # Fallback: Haar cascades
    return _detect_haar(img_det, w_det, h_det, scale)


def _detect_yunet(img, w, h, scale):
    """Run YuNet DNN face detector. Returns face dicts in original coords."""
    detector = cv2.FaceDetectorYN.create(_YUNET_MODEL, "", (w, h))
    detector.setScoreThreshold(0.7)

    _, detections = detector.detect(img)
    if detections is None or len(detections) == 0:
        return []

    inv = 1.0 / scale
    results = []
    for det in detections:
        x, y, bw, bh = int(det[0]), int(det[1]), int(det[2]), int(det[3])
        # Map back to original image size
        results.append({
            "x": max(0, int(x * inv)),
            "y": max(0, int(y * inv)),
            "w": int(bw * inv),
            "h": int(bh * inv),
        })
    return results


def _detect_haar(img, w, h, scale):
    """Fallback Haar cascade detector."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        return []

    rects = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=6, minSize=(40, 40),
        flags=cv2.CASCADE_SCALE_IMAGE,
    )
    if len(rects) == 0:
        return []

    inv = 1.0 / scale
    mapped = [[int(x * inv), int(y * inv), int(bw * inv), int(bh * inv)]
              for (x, y, bw, bh) in rects.tolist()]
    merged = _nms(mapped, overlap_thresh=0.3)
    return [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
            for (x, y, w, h) in merged]


def _nms(rects, overlap_thresh=0.4):
    """Simple non-maximum suppression on [x, y, w, h] rectangles."""
    if not rects:
        return []
    boxes = np.array(rects, dtype=float)
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 0] + boxes[:, 2]
    y2 = boxes[:, 1] + boxes[:, 3]
    areas = boxes[:, 2] * boxes[:, 3]

    order = areas.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / np.minimum(areas[i], areas[order[1:]])
        inds = np.where(iou <= overlap_thresh)[0]
        order = order[inds + 1]

    return boxes[keep].astype(int).tolist()


def apply_blur_to_faces(image_path, faces, keep_indices=None):
    """Apply Gaussian blur to specified face regions.

    Args:
        image_path: Path to the source image.
        faces: List of face dicts [{"x", "y", "w", "h"}, ...].
        keep_indices: Set of face indices to NOT blur (the subject).
                      If None, all faces are blurred.

    Returns:
        PIL Image with blurred faces.
    """
    if keep_indices is None:
        keep_indices = set()

    img = Image.open(image_path)
    img_array = np.array(img)

    for i, face in enumerate(faces):
        if i in keep_indices:
            continue

        x, y, w, h = face["x"], face["y"], face["w"], face["h"]

        # Add padding around face region
        pad = int(max(w, h) * 0.15)
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(img_array.shape[1], x + w + pad)
        y2 = min(img_array.shape[0], y + h + pad)

        # Extract face region, blur it, put it back
        face_region = img_array[y1:y2, x1:x2]
        face_pil = Image.fromarray(face_region)
        # Strong Gaussian blur
        blur_radius = max(w, h) // 3
        blurred = face_pil.filter(ImageFilter.GaussianBlur(radius=max(blur_radius, 15)))
        img_array[y1:y2, x1:x2] = np.array(blurred)

    return Image.fromarray(img_array)
