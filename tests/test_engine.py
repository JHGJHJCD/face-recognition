"""בדיקת עשן למנוע: איתור, זהות, גיל/מין, הבעה, הגנה מזיוף + זמני ריצה."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.engine import EMOTIONS, FaceEngine  # noqa: E402
from core.utils import MODELS_DIR, imread  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
print("models:", sorted(os.listdir(MODELS_DIR)))
t = time.time()
eng = FaceEngine()
print(f"load {time.time() - t:.1f}s")

for name in sorted(os.listdir(IMG)):
    img = imread(os.path.join(IMG, name))
    if img is None:
        print(name, "-> not an image")
        continue
    t = time.time()
    faces = eng.detect(img)
    t_det = time.time() - t
    t = time.time()
    eng.embed(img, faces)
    t_rec = time.time() - t
    print(f"{name} {img.shape[1]}x{img.shape[0]}: {len(faces)} faces  det {t_det * 1000:.0f}ms  rec {t_rec * 1000:.0f}ms")
    for f in faces:
        t = time.time()
        eng.gender_age(img, f)
        eng.emotion(img, f)
        eng.liveness(img, f)
        dt = time.time() - t
        print(f"   det={f.det:.2f} size={f.size:.0f} frontal={f.frontal:.2f} age={f.age:.0f} male={f.male} "
              f"emo={EMOTIONS[f.emotion]} real={f.real} ({f.real_p:.2f}) attrs {dt * 1000:.0f}ms")
    if len(faces) > 1:
        import numpy as np
        E = np.stack([f.emb for f in faces])
        S = E @ E.T
        np.fill_diagonal(S, -1)
        print(f"   max similarity between different faces: {S.max():.2f}")
