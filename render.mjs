// Renders index.html to out/rest-starts-here.mp4 (1080x1920, 30fps, 15s).
// Usage: node render.mjs [--stills]   (FFMPEG env var overrides the ffmpeg binary)
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, "out");
const FPS = 30, W = 1080, H = 1920;
const FFMPEG = process.env.FFMPEG || "ffmpeg";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: W, height: H } });
await page.goto(pathToFileURL(path.join(here, "index.html")).href + "?still");
await page.evaluate(() => window.__ready);
const duration = await page.evaluate(() => window.__DURATION);
const stage = page.locator("#stage");

if (process.argv.includes("--stills")) {
  for (const t of [1.8, 4.0, 6.5, 8.8, 11.0, 14.5]) {
    await page.evaluate(t => window.render(t), t);
    await stage.screenshot({ path: path.join(out, `still-${t.toFixed(1)}.png`) });
  }
  await browser.close();
  process.exit(0);
}

// --- ambient pad: warm A-major-ish drone that swells with the breath ---
const SR = 48000, N = Math.round(SR * duration);
const pcm = new Int16Array(N * 2);
const notes = [110, 164.81, 220, 277.18, 329.63]; // A2 E3 A3 C#4 E4
const breath = t => t < 5 ? 0 : t < 8.5 ? (1 - Math.cos(Math.PI * (t - 5) / 3.5)) / 2
  : t < 9.3 ? 1 : t < 12.3 ? (1 + Math.cos(Math.PI * (t - 9.3) / 3)) / 2 : 0;
for (let i = 0; i < N; i++) {
  const t = i / SR;
  const env = Math.min(1, t / 2.5) * Math.min(1, (duration - t) / 1.5);
  const swell = 0.75 + 0.25 * breath(t);
  let l = 0, r = 0;
  notes.forEach((f, k) => {
    const amp = 0.11 / (1 + k * 0.6);
    const lfo = 0.8 + 0.2 * Math.sin(2 * Math.PI * (0.07 + k * 0.03) * t + k);
    l += amp * lfo * Math.sin(2 * Math.PI * f * t);
    r += amp * lfo * Math.sin(2 * Math.PI * f * 1.0025 * t + 0.6);
  });
  // gentle chime at the closing line
  const ct = t - 12.7;
  const chime = ct > 0 ? 0.06 * Math.exp(-ct * 1.4) * (Math.sin(2 * Math.PI * 880 * ct) + 0.5 * Math.sin(2 * Math.PI * 1318.5 * ct)) : 0;
  pcm[2 * i] = Math.round(32767 * Math.tanh((l * swell + chime) * env * 0.9));
  pcm[2 * i + 1] = Math.round(32767 * Math.tanh((r * swell + chime) * env * 0.9));
}
const wavPath = path.join(out, "pad.wav");
const hdr = Buffer.alloc(44);
hdr.write("RIFF", 0); hdr.writeUInt32LE(36 + pcm.byteLength, 4); hdr.write("WAVEfmt ", 8);
hdr.writeUInt32LE(16, 16); hdr.writeUInt16LE(1, 20); hdr.writeUInt16LE(2, 22);
hdr.writeUInt32LE(SR, 24); hdr.writeUInt32LE(SR * 4, 28); hdr.writeUInt16LE(4, 32); hdr.writeUInt16LE(16, 34);
hdr.write("data", 36); hdr.writeUInt32LE(pcm.byteLength, 40);
writeFileSync(wavPath, Buffer.concat([hdr, Buffer.from(pcm.buffer)]));

// --- frames -> ffmpeg ---
const mp4 = path.join(out, "rest-starts-here.mp4");
const ff = spawn(FFMPEG, [
  "-y", "-loglevel", "error",
  "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
  "-i", wavPath,
  "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-tune", "grain", "-pix_fmt", "yuv420p",
  "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", mp4,
], { stdio: ["pipe", "inherit", "inherit"] });

const frames = Math.round(duration * FPS);
for (let f = 0; f < frames; f++) {
  await page.evaluate(t => window.render(t), f / FPS);
  const png = await stage.screenshot({ type: "png" });
  if (!ff.stdin.write(png)) await new Promise(r => ff.stdin.once("drain", r));
  if (f % 30 === 0) process.stdout.write(`\rframe ${f}/${frames}`);
}
ff.stdin.end();
await new Promise((res, rej) => ff.on("close", c => c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`))));
await browser.close();
console.log(`\nwrote ${mp4}`);
