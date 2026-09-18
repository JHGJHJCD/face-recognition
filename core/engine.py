"""מנוע זיהוי הפנים — כל המודלים רצים מקומית (OpenVINO על המאיץ הגרפי, גיבוי ONNX Runtime).

  איתור פנים  : SCRFD-10G (InsightFace)            det_10g.onnx
  זהות         : ArcFace ResNet100 / Glint360K       glintr100.onnx  (וקטור 512; גיבוי: w600k_r50)
  גיל ומין     : FairFace ResNet34                   fairface.onnx
  הבעת פנים    : HSEmotion EfficientNet-B0 (8 רגשות) emotion.onnx
  הגנה מזיוף   : MiniFASNetV2 + MiniFASNetV1SE       (Silent-Face)
"""
import os
import threading

import cv2
import numpy as np

from .utils import MODELS_DIR, crop_square

ARCFACE_DST = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)

DET_SIZE = 640
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], np.float32)
AGE_MIDPOINTS = np.array([1, 6, 15, 25, 35, 45, 55, 65, 75], np.float32)
EMOTIONS = ["כועס", "בוז", "גועל", "מפוחד", "שמח", "רגוע", "עצוב", "מופתע"]


class Net:
    """מודל אחד. מעדיף OpenVINO על המאיץ הגרפי של אינטל (מהיר פי ~10 מהמעבד), עם נפילה ל-ONNX Runtime."""
    _core = None
    device = "CPU"

    def __init__(self, name, shape):
        self.lock = threading.Lock()
        self.ov = None
        path = os.path.join(MODELS_DIR, name)
        with open(path, "rb") as f:
            data = f.read()
        try:
            import openvino as ov
            if Net._core is None:
                Net._core = ov.Core()
                cache = os.path.join(os.environ.get("LOCALAPPDATA", MODELS_DIR), "FaceID_ov_cache")
                os.makedirs(cache, exist_ok=True)
                Net._core.set_property({"CACHE_DIR": cache})
                Net.device = "GPU" if "GPU" in Net._core.available_devices else "CPU"
            model = Net._core.read_model(model=data)
            model.reshape({model.inputs[0].any_name: shape})
            self.ov = Net._core.compile_model(model, Net.device, {"PERFORMANCE_HINT": "LATENCY"})
        except Exception:
            import onnxruntime as ort   # גיבוי בלבד (לא נארז ב-EXE — OpenVINO רץ גם על המעבד)
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            self.sess = ort.InferenceSession(data, opts, providers=["CPUExecutionProvider"])
            self.inp = self.sess.get_inputs()[0].name

    def __call__(self, blob):
        with self.lock:
            if self.ov is not None:
                res = self.ov(blob)
                return [res[i] for i in range(len(res))]
            return self.sess.run(None, {self.inp: blob})


def _umeyama(src, dst):
    """טרנספורמציית דמיון (סיבוב+קנה מידה+הזזה) בריבועים פחותים."""
    n = src.shape[0]
    mu_s, mu_d = src.mean(0), dst.mean(0)
    s, d = src - mu_s, dst - mu_d
    cov = d.T @ s / n
    U, S, Vt = np.linalg.svd(cov)
    D = np.ones(2)
    if np.linalg.det(cov) < 0:
        D[1] = -1
    R = U @ np.diag(D) @ Vt
    var = (s ** 2).sum() / n
    scale = (S * D).sum() / var if var > 0 else 1.0
    M = np.zeros((2, 3), np.float32)
    M[:, :2] = scale * R
    M[:, 2] = mu_d - scale * R @ mu_s
    return M


def align_face(img, kps, size=112):
    M = _umeyama(np.asarray(kps, np.float32), ARCFACE_DST * (size / 112.0))
    return cv2.warpAffine(img, M, (size, size), borderValue=0.0)


def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


class Face:
    __slots__ = ("bbox", "kps", "det", "emb", "norm", "age", "male", "emotion", "emotion_p", "real", "real_p")

    def __init__(self, bbox, kps, det):
        self.bbox, self.kps, self.det = bbox, kps, det
        self.emb = None
        self.norm = 0.0   # אורך הווקטור הגולמי (נמדד: לא מבדיל היטב בין חד למטושטש במודל הזה — לא משמש לסינון)
        self.age = self.male = self.emotion = self.emotion_p = self.real = self.real_p = None

    @property
    def size(self):
        return float(min(self.bbox[2] - self.bbox[0], self.bbox[3] - self.bbox[1]))

    @property
    def frontal(self):
        """0..1 — כמה הפנים חזיתיות (לפי מיקום האף בין העיניים)."""
        le, re, nose = self.kps[0], self.kps[1], self.kps[2]
        d = re[0] - le[0]
        if abs(d) < 1e-3:
            return 0.0
        r = (nose[0] - le[0]) / d
        return float(max(0.0, 1.0 - abs(r - 0.5) * 2))


class FaceEngine:
    def __init__(self):
        rec = "glintr100.onnx" if os.path.exists(os.path.join(MODELS_DIR, "glintr100.onnx")) else "w600k_r50.onnx"
        self.rec_name = rec.split(".")[0]
        self.det = Net("det_10g.onnx", [1, 3, DET_SIZE, DET_SIZE])
        self.rec = Net(rec, [1, 3, 112, 112])
        self.ga = Net("fairface.onnx", [1, 3, 224, 224])
        self.emo = Net("emotion.onnx", [1, 3, 224, 224])
        self.spoof = [(Net("MiniFASNetV2.onnx", [1, 3, 80, 80]), 2.7), (Net("MiniFASNetV1SE.onnx", [1, 3, 80, 80]), 4.0)]
        self.device = Net.device
        self._centers = {}

    # ---------- איתור ----------
    def detect(self, img, thresh=0.5, max_faces=0):
        size = DET_SIZE
        h, w = img.shape[:2]
        scale = size / max(h, w)
        nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        canvas = np.zeros((size, size, 3), np.uint8)
        canvas[:nh, :nw] = cv2.resize(img, (nw, nh))
        blob = cv2.dnn.blobFromImage(canvas, 1 / 128.0, (size, size), (127.5, 127.5, 127.5), swapRB=True)
        outs = self.det(blob)
        outs = sorted(outs, key=lambda o: (o.reshape(-1, o.shape[-1]).shape[1], -o.size))  # ציונים, תיבות, נקודות
        boxes, scores, kpss = [], [], []
        for i, stride in enumerate((8, 16, 32)):
            sc = outs[i].reshape(-1)
            bb = outs[i + 3].reshape(-1, 4) * stride
            kp = outs[i + 6].reshape(-1, 10) * stride
            key = (size, stride)
            if key not in self._centers:
                n = size // stride
                g = np.stack(np.mgrid[:n, :n][::-1], -1).astype(np.float32).reshape(-1, 2) * stride
                self._centers[key] = np.repeat(g, 2, axis=0)
            c = self._centers[key]
            keep = sc >= thresh
            if not keep.any():
                continue
            c, bb, kp, sc = c[keep], bb[keep], kp[keep], sc[keep]
            boxes.append(np.stack([c[:, 0] - bb[:, 0], c[:, 1] - bb[:, 1], c[:, 0] + bb[:, 2], c[:, 1] + bb[:, 3]], 1))
            kpss.append(kp.reshape(-1, 5, 2) + c[:, None, :])
            scores.append(sc)
        if not boxes:
            return []
        boxes, scores, kpss = np.vstack(boxes) / scale, np.hstack(scores), np.vstack(kpss) / scale
        xywh = np.column_stack([boxes[:, 0], boxes[:, 1], boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1]])
        idx = cv2.dnn.NMSBoxes(xywh.tolist(), scores.tolist(), thresh, 0.4)
        idx = np.array(idx).reshape(-1)
        faces = [Face(boxes[i].astype(np.float32), kpss[i].astype(np.float32), float(scores[i])) for i in idx]
        faces.sort(key=lambda f: -(f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        return faces[:max_faces] if max_faces else faces

    # ---------- זהות ----------
    def embed(self, img, faces, tta=True):
        if not faces:
            return
        crops = [align_face(img, f.kps) for f in faces]
        for f, crop in zip(faces, crops):
            e = np.zeros(512, np.float32)
            for c in ((crop, cv2.flip(crop, 1)) if tta else (crop,)):   # תמונה + תמונת ראי = וקטור יציב יותר
                blob = cv2.dnn.blobFromImage(c, 1 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
                e = e + np.array(self.rec(blob)[0][0], np.float32)
            f.norm = float(np.linalg.norm(e)) / (2 if tta else 1)
            f.emb = e / max(np.linalg.norm(e), 1e-9)

    # ---------- גיל ומין ----------
    def gender_age(self, img, face):
        x = cv2.cvtColor(crop_square(img, face.bbox, margin=0.5, size=224), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = (x - IMAGENET_MEAN) / IMAGENET_STD
        outs = self.ga(np.ascontiguousarray(x.transpose(2, 0, 1)[None]))
        gender = next(o for o in outs if o.shape[-1] == 2)[0]
        age = _softmax(next(o for o in outs if o.shape[-1] == 9)[0])
        face.male = bool(gender[0] > gender[1])
        face.age = float(age @ AGE_MIDPOINTS)   # תוחלת על פני 9 קבוצות הגיל

    # ---------- הבעה ----------
    def emotion(self, img, face):
        h, w = img.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in face.bbox]
        crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size == 0:
            return
        x = cv2.cvtColor(cv2.resize(crop, (224, 224)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = (x - IMAGENET_MEAN) / IMAGENET_STD
        out = self.emo(np.ascontiguousarray(x.transpose(2, 0, 1)[None]))[0][0]
        p = _softmax(out)
        face.emotion_p = p
        face.emotion = int(np.argmax(p))

    # ---------- הגנה מזיוף ----------
    def liveness(self, img, face):
        sh, sw = img.shape[:2]
        x1, y1, x2, y2 = face.bbox
        bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
        total = np.zeros(3, np.float32)
        for sess, sc in self.spoof:
            s = min((sh - 1) / bh, (sw - 1) / bw, sc)
            nw, nh = bw * s, bh * s
            cx, cy = x1 + bw / 2, y1 + bh / 2
            xa, ya = max(0, int(cx - nw / 2)), max(0, int(cy - nh / 2))
            xb, yb = min(sw - 1, int(cx + nw / 2)), min(sh - 1, int(cy + nh / 2))
            crop = img[ya:yb + 1, xa:xb + 1]
            if crop.size == 0:
                return
            x = np.ascontiguousarray(cv2.resize(crop, (80, 80)).astype(np.float32).transpose(2, 0, 1)[None])
            out = sess(x)[0][0]
            total += _softmax(out)
        total /= len(self.spoof)
        face.real_p = float(total[1])
        face.real = bool(np.argmax(total) == 1)

    def analyze(self, img, thresh=0.5, attributes=False):
        faces = self.detect(img, thresh)
        self.embed(img, faces)
        if attributes:
            for f in faces:
                self.gender_age(img, f)
                self.emotion(img, f)
        return faces


def sharpness(img, bbox):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if crop.size == 0:
        return 0.0
    g = cv2.cvtColor(cv2.resize(crop, (112, 112)), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def enhance_low_light(img):
    """תאורה חלשה פוגעת באיתור ובזיהוי — מבהירים (CLAHE על ערוץ הבהירות) רק כשהתמונה חשוכה."""
    mean = float(cv2.cvtColor(cv2.resize(img, (64, 36)), cv2.COLOR_BGR2GRAY).mean())
    if mean > 75:
        return img
    gamma = float(np.clip(np.log(110 / 255) / np.log(max(mean, 2) / 255), 0.35, 1.0))
    lut = (np.linspace(0, 1, 256) ** gamma * 255).astype(np.uint8)
    lab = cv2.cvtColor(cv2.LUT(img, lut), cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
