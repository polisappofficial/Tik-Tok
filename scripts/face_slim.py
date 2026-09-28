"""Subtle face-slimming pass: tracks the face with MediaPipe Face Landmarker and
applies a smooth local liquify warp that pulls the cheeks / jaw inward and lifts
the soft area under the chin. Usage: face_slim.py in.mp4 out.mp4 model.task [--frames a,b,c]"""
import sys, subprocess, numpy as np, cv2, av
import mediapipe as mp
from mediapipe.tasks.python import vision, BaseOptions

src, dst, model = sys.argv[1:4]
only = [int(x) for x in sys.argv[5].split(",")] if len(sys.argv) > 5 else None
CHEEK, JAW, CHIN = 0.050, 0.035, 0.055    # strength (fraction of face width/height)
# mediapipe face-mesh contour indices (image-left side, image-right side)
CHEEK_L, CHEEK_R = [93, 132, 58], [323, 361, 288]
JAW_L, JAW_R = [172, 136, 150], [397, 365, 379]
CHIN_PTS = [176, 148, 152, 377, 400]

lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model), running_mode=vision.RunningMode.VIDEO,
    num_faces=1, min_face_detection_confidence=0.4, min_tracking_confidence=0.4))

def warp(img, moves):
    """moves: list of (cx, cy, vx, vy, r). Backward-mapped local translation warp."""
    h, w = img.shape[:2]
    x0 = int(max(0, min(m[0] - m[4] for m in moves))); x1 = int(min(w, max(m[0] + m[4] for m in moves)))
    y0 = int(max(0, min(m[1] - m[4] for m in moves))); y1 = int(min(h, max(m[1] + m[4] for m in moves)))
    gx, gy = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))
    dx = np.zeros_like(gx); dy = np.zeros_like(gy)
    for cx, cy, vx, vy, r in moves:
        d2 = ((gx - cx) ** 2 + (gy - cy) ** 2) / (r * r)
        wgt = np.clip(1 - d2, 0, 1) ** 2
        dx += vx * wgt; dy += vy * wgt
    out = img.copy()
    out[y0:y1, x0:x1] = cv2.remap(img, gx - dx, gy - dy, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    return out

inp = av.open(src); vs = inp.streams.video[0]
W, H = vs.codec_context.width, vs.codec_context.height
enc = None
if not only:
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", "30000/1001", "-i", "-", "-i", src, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow",
        "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", dst], stdin=subprocess.PIPE)
prev = None; found = 0
for i, fr in enumerate(inp.decode(video=0)):
    img = fr.to_ndarray(format="rgb24")
    res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)),
                              int(i * 1001 / 30))
    out = img
    if res.face_landmarks:
        P = np.array([[p.x * W, p.y * H] for p in res.face_landmarks[0]], np.float32)
        fw = np.linalg.norm(P[234] - P[454])
        # temporal smoothing; reset on big jumps (cuts / dissolves)
        if prev is not None and np.abs(P - prev).max() < 0.08 * fw: P = 0.55 * P + 0.45 * prev
        prev = P
        fh = np.linalg.norm(P[10] - P[152]); nose = P[1]
        moves = []
        for idx, s, rr in [(CHEEK_L + CHEEK_R, CHEEK, 0.16), (JAW_L + JAW_R, JAW, 0.14)]:
            for k in idx:
                v = nose - P[k]; v[1] *= 0.35; v /= np.linalg.norm(v) + 1e-6
                v *= s * fw / 2.2
                moves.append((P[k][0], P[k][1], v[0], v[1], rr * fw))
        down = (P[152] - P[10]) / fh
        for k in CHIN_PTS:
            c = P[k] + down * 0.07 * fh
            v = -down * CHIN * fh / 2.5
            moves.append((c[0], c[1], v[0], v[1], 0.13 * fh))
        out = warp(img, moves); found += 1
    else:
        prev = None
    if only is not None:
        if i in only:
            cv2.imwrite(f"{dst}_{i}.png", cv2.cvtColor(np.hstack([img, out]), cv2.COLOR_RGB2BGR))
        if i >= max(only): break
    else:
        enc.stdin.write(out.tobytes())
if enc: enc.stdin.close(); enc.wait()
print("frames with face:", found, "of", i + 1)
