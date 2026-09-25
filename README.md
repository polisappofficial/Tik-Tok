# Rest starts here: meditation app intro

A 15-second vertical (1080×1920, 30fps) product intro for people who have trouble falling asleep.

**Output:** [`out/rest-starts-here.mp4`](out/rest-starts-here.mp4)

| Time | Beat |
|---|---|
| 0–3s | Fade up from black: *"Still awake at 2 a.m.?"* |
| 3–4.5s | *"Let your breath slow the night down."* |
| 4.5–12.5s | Breathing timer: the orb grows on *Breathe in*, holds, shrinks on *Breathe out*. A progress ring traces each phase and a 10:00 session clock counts down in real seconds. |
| 12.5–15s | Timer dissolves into a warm glow: **"Rest starts *here.*"** |

Audio is a quiet synthesized A-major pad that swells with each breath, with a soft chime on the closing line.

## Editing & re-rendering

`index.html` is the whole composition. All motion comes from one deterministic `render(t)` function. Open it in a browser for a looping live preview. Timings are in `render()` and the `T` breathing schedule.

```sh
node render.mjs            # full render -> out/rest-starts-here.mp4 (needs playwright + ffmpeg)
node render.mjs --stills   # key-frame PNGs for quick checks
```

Set `FFMPEG=/path/to/ffmpeg` if ffmpeg is not on your PATH. Fonts are Fraunces and Nunito Sans (SIL OFL), bundled in `fonts/`.
