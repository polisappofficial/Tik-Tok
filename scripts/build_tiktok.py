"""Build the multi-clip TikTok cut: pauses removed (alternating punch-in jump cuts),
clips colour/loudness matched to IMG_6284, joined with smooth zoom-dissolves."""
import subprocess, sys
S = "/root/.claude/uploads/702fee8f-3cbe-5239-af99-f1b2098d7a56/"
OUT = sys.argv[1]
FR = 1001 / 30000
q = lambda x: round(x / FR) * FR
PRE, POST = 0.06, 0.09      # padding kept before/after speech
D = 0.30                     # transition length (video overlap, centred on the audio cut)
EXT = D / 2
PUNCH, TZ = 1.12, 0.10       # jump-cut punch-in, extra zoom during transitions
clips = [  # file, speech islands (pauses <0.25s kept), grade, gain
    ("c1cd4e31-Adobe_Express_-_IMG_6284-2.mp4",
     [(2.227, 3.720), (4.100, 5.136), (5.780, 7.640), (7.969, 11.027), (11.541, 12.068)], None, 0),
    ("fad40645-Adobe_Express_-_IMG_6289.mp4", [(2.068, 7.382), (7.803, 10.657)],
     "eq=saturation=0.82:contrast=1.07:brightness=-0.012:gamma=0.98,lutyuv=u=val+0.3:v=val+2", -1.7),
    ("1e66f8dc-Adobe_Express_-_IMG_6292.mp4", [(2.280, 6.619), (7.042, 8.830)],
     "eq=saturation=0.64:contrast=1.07:brightness=-0.015:gamma=0.98,lutyuv=u=val-4:v=val+4", -0.3),
    ("5c3a5051-Adobe_Express_-_IMG_6299.mp4",
     [(1.982, 3.204), (3.508, 6.430), (6.723, 8.594), (8.890, 11.297)],
     "eq=saturation=0.92:contrast=1.05:brightness=-0.008:gamma=0.98,lutyuv=u=val+2.5:v=val+2.5", -1.3),
]
ease = "(3*pow({x},2)-2*pow({x},3))"   # smoothstep

def zoomv(expr):
    return (f"scale=w='2*trunc(540*({expr}))':h='2*trunc(960*({expr}))':eval=frame,"
            f"crop=1080:1920:x='(iw-1080)*0.5':y='(ih-1920)*0.33',setsar=1")

fc, cut_times, clip_len = [], [], []
t_audio = 0.0
for ci, (f, speech, grade, gain) in enumerate(clips):
    vs, as_ = [], []
    n = len(speech)
    for si, (s, e) in enumerate(speech):
        a, b = q(s - PRE), q(e + POST)
        va, vb = a, b
        if si == 0 and ci > 0: va = q(a - EXT)
        if si == n - 1 and ci < len(clips) - 1: vb = q(b + EXT)
        base = PUNCH if si % 2 else 1.0
        L = vb - va
        z = f"{base}"
        if si == n - 1 and ci < len(clips) - 1:   # ease into zoom while dissolving out
            x = f"max(0,(t-{L - D:.4f})/{D})"
            z = f"{base}*(1+{TZ}*{ease.format(x=x)})"
        if si == 0 and ci > 0:                      # ease out of zoom while dissolving in
            x = f"max(0,1-t/{D})"
            z = f"{base}*(1+{TZ}*{ease.format(x=x)})"
        k = f"{ci}_{si}"
        fc.append(f"[{ci}:v]trim=start_frame={round(va/FR)}:end_frame={round(vb/FR)},"
                  f"setpts=N/(30000/1001)/TB," + (grade + "," if grade else "") + zoomv(z) +
                  f",setpts=N/(30000/1001)/TB,format=yuv420p[v{k}]")
        fc.append(f"[{ci}:a]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS,volume={gain}dB,"
                  f"afade=t=in:d=0.012,afade=t=out:st={b - a - 0.015:.4f}:d=0.015[a{k}]")
        vs.append(f"[v{k}]"); as_.append(f"[a{k}]")
        t_audio += b - a
    fc.append("".join(vs) + f"concat=n={n}:v=1:a=0,fps=30000/1001[cv{ci}]")
    fc.append("".join(as_) + f"concat=n={n}:v=0:a=1[ca{ci}]")
    cut_times.append(t_audio)
# video: chain of dissolves; each overlap is centred on the audio cut
prev, off = "cv0", 0.0
for ci in range(1, len(clips)):
    off = cut_times[ci - 1] - EXT
    fc.append(f"[{prev}][cv{ci}]xfade=transition=fade:duration={D}:offset={off:.4f}[x{ci}]")
    prev = f"x{ci}"
fc.append(f"[{prev}]settb=1001/30000,setpts=N,fps=30000/1001[v]")
fc.append("".join(f"[ca{ci}]" for ci in range(len(clips))) + f"concat=n={len(clips)}:v=0:a=1[sp]")
# soft whoosh under each transition
wl = []
for i, t in enumerate(cut_times[:-1]):
    ms = int((t - 0.28) * 1000)
    fc.append(f"anoisesrc=color=pink:d=0.5:a=0.5:r=48000:seed={i+1},highpass=f=400,lowpass=f=3000,"
              f"afade=t=in:d=0.28:curve=qsin,afade=t=out:st=0.28:d=0.22:curve=qsin,volume=-20dB,"
              f"aformat=channel_layouts=stereo,adelay={ms}|{ms}[wh{i}]")
    wl.append(f"[wh{i}]")
fc.append("[sp]highpass=f=80,acompressor=threshold=-24dB:ratio=2.5:attack=10:release=150:makeup=2[spc]")
fc.append("[spc]" + "".join(wl) + f"amix=inputs={1+len(wl)}:duration=first:normalize=0,"
          "loudnorm=I=-14:TP=-1.5:LRA=7[a]")
cmd = ["ffmpeg", "-v", "error", "-y"] + sum([["-i", S + c[0]] for c in clips], []) + [
    "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-ar", "48000", "-r", "30000/1001",
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", OUT]
print("cuts at", [round(t, 3) for t in cut_times[:-1]], "total", round(t_audio, 3))
subprocess.run(cmd, check=True)
