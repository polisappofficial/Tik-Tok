"""Final pass: double-chin touch-up + emphasis captions (white, red offset shadow)
composited BEHIND the speaker. Each word appears on the frame it is spoken.
Usage: captions_behind.py base.mp4 base.segments.json out.mp4 face_model.task seg_model.tflite [--frames a,b]"""
import sys, json, re, subprocess, numpy as np, cv2, av
import mediapipe as mp
from mediapipe.tasks.python import vision, BaseOptions
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from face_slim import warp, face_moves, make_landmarker

src, segf, dst, face_model, seg_model = sys.argv[1:6]
only = [int(x) for x in sys.argv[7].split(",")] if len(sys.argv) > 7 else None
ROOT = __file__.rsplit("/", 2)[0]
FONT = ROOT + "/assets/ArchivoBlack-Regular.ttf"
WORDS = json.load(open(ROOT + "/assets/word_timings.json"))
SEGS = json.load(open(segf))
FPS = 30000 / 1001
LEAD = 0.033            # show a word one frame before its acoustic onset so it never feels late
WHITE, RED = (255, 255, 255), (228, 30, 42)
BASE, HERO, MAXW = 118, 190, 960

# Emphasis phrases per clip, in spoken order. Lines separated by "|", "*" marks the hero line.
# Each display token is timed to the next matching spoken word (words may be skipped).
PHRASES = {
 "c1cd4e31-Adobe_Express_-_IMG_6284-2.mp4": ["*CANADA", "BEAUTIFUL|*COUNTRY", "AMAZING|*COMMUNITY",
     "*DEMOCRACY", "EVERY|*FOUR YEARS", "*VOTE", "THAT WAS|*IT"],
 "fad40645-Adobe_Express_-_IMG_6289.mp4": ["BUT WHAT|*ABOUT", "*IN BETWEEN?", "*EDUCATION", "*HOUSING", "*JOBS",
     "*NO ONE", "EVERY|*FOUR YEARS"],
 "1e66f8dc-Adobe_Express_-_IMG_6292.mp4": ["*BETTER WAYS", "*PROTESTING", "PRIVATE|*EMAILS", "*POLITICIANS",
     "VOICE OUR|*OPINIONS"],
 "5c3a5051-Adobe_Express_-_IMG_6299.mp4": ["*POLIS", "BUILDING|*AN APP", "CANADIANS|*VOTE", "*SUPPORT", "OR|*OPPOSE",
     "REAL|*BILLS", "*RIGHT NOW", "EXACTLY|*HOW WE FEEL"],
 "d0e8cbfe-Adobe_Express_-_IMG_6301.mp4": ["*INTERESTED?", "JOIN OUR|*WAITLIST", "LINK IN|*BIO", "BE THE|*FIRST"],
}
ALIAS = {"waitlist": "wait"}

def src_to_out(clip, t):
    best = None
    for f, a, b, o in SEGS:
        if f != clip: continue
        if a <= t < b: return o + t - a
        if t < a and (best is None or a < best[0]): best = (a, o)   # word onset inside trimmed pad -> segment start
    return best[1] if best else None

font_cache = {}
def font(sz):
    if sz not in font_cache: font_cache[sz] = ImageFont.truetype(FONT, sz)
    return font_cache[sz]

def render_token(text, sz):
    f = font(sz); off = max(4, round(sz * 0.07))
    l, t, r, b = f.getbbox(text)
    w, h = r - l + off + 8, b - t + off + 8
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.text((4 - l + off, 4 - t + off), text, font=f, fill=RED + (255,))
    d.text((4 - l, 4 - t), text, font=f, fill=WHITE + (255,))
    return np.array(im), (r - l), (b - t)

# ---- build timed layout
phrases = []
for clip, plist in PHRASES.items():
    words = WORDS[clip]; cur = 0
    for spec in plist:
        lines = []
        for line in spec.split("|"):
            hero = line.startswith("*"); line = line.lstrip("*")
            toks = []
            for tok in line.split(" "):
                key = ALIAS.get(re.sub(r"[^a-z']", "", tok.lower()), re.sub(r"[^a-z']", "", tok.lower()))
                while words[cur]["w"] != key: cur += 1
                toks.append((tok, src_to_out(clip, words[cur]["start"]) - LEAD, src_to_out(clip, words[cur]["end"])))
                cur += 1
            lines.append((toks, hero))
        phrases.append(lines)
# sizes / positions (relative to block top)
blocks = []
for lines in phrases:
    items, y = [], 0
    for toks, hero in lines:
        sz = HERO if hero else BASE
        while True:
            rend = [render_token(t[0], sz) for t in toks]
            space = sz * 0.33
            wtot = sum(r[1] for r in rend) + space * (len(rend) - 1)
            if wtot <= MAXW or sz < 60: break
            sz = int(sz * 0.93)
        x = (1080 - wtot) / 2
        for (tok, t0, t1), (img, w, h) in zip(toks, rend):
            items.append({"img": img, "x": x, "y": y, "t0": t0})
            x += w + space
        y += sz * 0.98
    start = min(i["t0"] for i in items)
    blocks.append({"items": items, "h": y, "start": start, "last_end": max(t[2] for l in lines for t in l[0])})
for i, b in enumerate(blocks):
    nxt = blocks[i + 1]["start"] if i + 1 < len(blocks) else 1e9
    b["end"] = min(nxt - 0.001, b["last_end"] + 0.55)
    b["top"] = None

seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
    base_options=BaseOptions(model_asset_path=seg_model), running_mode=vision.RunningMode.VIDEO,
    output_confidence_masks=True))
lm = make_landmarker(face_model)

def choose_top(b, person):
    """Sit the block just behind the head: as low as possible while <=12% of its ink is hidden."""
    for top in range(430, 159, -30):
        cov, tot = 0.0, 0.0
        for it in b["items"]:
            a = it["img"][..., 3] > 0; h, w = a.shape
            y0, x0 = int(top + it["y"]), int(it["x"])
            m = person[y0:y0 + h, x0:x0 + w]
            cov += (m[:a.shape[0], :a.shape[1]] * a[:m.shape[0], :m.shape[1]]).sum(); tot += a.sum()
        if cov / tot <= 0.12: return top, False
    return 190, True      # head fills the top of frame (punch-in): keep text readable in front

inp = av.open(src); W, H = 1080, 1920
enc = None if only else subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
    "-s", f"{W}x{H}", "-r", "30000/1001", "-i", "-", "-i", src, "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
    "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", dst],
    stdin=subprocess.PIPE)
prevP, prevM = None, None
for i, fr in enumerate(inp.decode(video=0)):
    t = i / FPS
    img = fr.to_ndarray(format="rgb24")
    mpimg = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img))
    ts = int(i * 1001 / 30)
    res = lm.detect_for_video(mpimg, ts)
    if res.face_landmarks:
        P = np.array([[p.x * W, p.y * H] for p in res.face_landmarks[0]], np.float32)
        fw = np.linalg.norm(P[234] - P[454])
        if prevP is not None and np.abs(P - prevP).max() < 0.08 * fw: P = 0.55 * P + 0.45 * prevP
        prevP = P
        img = warp(img, face_moves(P))
    else:
        prevP = None
    active = [b for b in blocks if b["start"] <= t < b["end"]]
    if active or (only and i in only):
        sres = seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)), ts)
        person = 1.0 - sres.confidence_masks[0].numpy_view().astype(np.float32)
        person = cv2.resize(person, (W, H)) if person.shape != (H, W) else person
        if prevM is not None: person = np.maximum(person, 0.5 * person + 0.5 * prevM)
        prevM = person
        layer = np.zeros((H, W, 4), np.float32); front = np.zeros((H, W, 1), np.float32)
        for b in active:
            if b["top"] is None: b["top"], b["front"] = choose_top(b, person)
            for it in b["items"]:
                if t < it["t0"]: continue
                k = int(round((t - it["t0"]) * FPS))           # frames since the word appeared
                s = 1.0 + 0.18 * max(0, 1 - k / 3) ** 2          # quick pop, full size by frame 3
                im = it["img"]
                if s != 1.0: im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
                h, w = im.shape[:2]; h0, w0 = it["img"].shape[:2]
                y0 = int(b["top"] + it["y"] - (h - h0) / 2); x0 = int(it["x"] - (w - w0) / 2)
                ys, xs = max(0, y0), max(0, x0); ye, xe = min(H, y0 + h), min(W, x0 + w)
                src_ = im[ys - y0:ye - y0, xs - x0:xe - x0].astype(np.float32) / 255
                a = src_[..., 3:4]; dstl = layer[ys:ye, xs:xe]
                dstl[..., :3] = src_[..., :3] * a + dstl[..., :3] * (1 - a)
                dstl[..., 3:4] = a + dstl[..., 3:4] * (1 - a)
                if b["front"]: front[ys:ye, xs:xe] = np.maximum(front[ys:ye, xs:xe], a)
        a = layer[..., 3:4] * (1 - person[..., None] * (1 - front))   # speaker in front of the text
        img = (img.astype(np.float32) * (1 - a) + layer[..., :3] * 255 * a).clip(0, 255).astype(np.uint8)
    else:
        prevM = None
    if only is not None:
        if i in only: cv2.imwrite(f"{dst}_{i}.png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        if i >= max(only): break
    else:
        enc.stdin.write(img.tobytes())
if enc: enc.stdin.close(); enc.wait()
print("phrases:", len(blocks))
for b in blocks: print(f"  {b['start']:6.2f}-{b['end']:6.2f} top={b['top']} front={b.get('front')} " + " ".join(f"{it['t0']:.2f}" for it in b['items']))
