"""OpenCV preprocessing to improve OCR on scans and photos."""
import cv2
import numpy as np


class ImageError(Exception):
    pass


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ImageError("Cannot decode image (corrupt or unsupported format)")
    return img


def load_multipage(data: bytes) -> list[np.ndarray]:
    """Decode all frames of a (multi-page) TIFF; single image for other formats."""
    arr = np.frombuffer(data, dtype=np.uint8)
    ok, frames = cv2.imdecodemulti(arr, cv2.IMREAD_COLOR)
    if ok and frames:
        return list(frames)
    return [decode_image(data)]


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def upscale_if_small(gray: np.ndarray, min_width: int = 1600) -> np.ndarray:
    h, w = gray.shape[:2]
    if w < min_width:
        scale = min_width / w
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    return gray


def estimate_skew(gray: np.ndarray) -> float:
    """Return skew angle in degrees (positive = counter-clockwise) using text-pixel min-area rect."""
    inv = cv2.bitwise_not(gray)
    thresh = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 100:
        return 0.0
    angle = cv2.minAreaRect(coords[:, ::-1].astype(np.float32))[-1]
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90
    return float(angle)


def deskew(gray: np.ndarray, max_angle: float = 15.0) -> tuple[np.ndarray, float]:
    angle = estimate_skew(gray)
    if abs(angle) < 0.3 or abs(angle) > max_angle:
        return gray, 0.0
    h, w = gray.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated, angle


def preprocess(img: np.ndarray) -> np.ndarray:
    """grayscale -> upscale -> denoise -> deskew -> adaptive threshold."""
    gray = to_gray(img)
    gray = upscale_if_small(gray)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    gray, _ = deskew(gray)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    return binary


def encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ImageError("PNG encoding failed")
    return buf.tobytes()
