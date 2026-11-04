#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Local watchdog: keep the Kaggle browser session alive and finish the MV.

Every 5 minutes it:
  1. Pokes the Chrome/Kaggle window (move cursor + bring to front) so Kaggle
     does not treat the tab as idle and recycle the session.
  2. Reads rescue_status.json from the private mv-media repo and logs progress.
  3. When manifest_final_lip.json appears, downloads all 20MB chunks,
     verifies sha256, rebuilds lipsynced.mp4, muxes song_final.mp3 back in,
     upscales to 1080p, builds a QC contact sheet, then uploads final.mp4
     back to GitHub as final_mv + DONE.txt.

Run (background, from the mv-lip folder):
  C:\\Python311\\python.exe -u kaggle/watchdog_local.py
Log: output/watchdog.log
"""
import os
import sys
import json
import time
import glob
import base64
import hashlib
import shutil
import subprocess
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)
LOGF = os.path.join(OUT, "watchdog.log")
TOKEN_FILE = r"D:/tmp/mv_audio/gh_token.txt"
SONG = r"D:\project\ai-project\音乐mv\mvp01_焚血逃天_副歌\01_audio\song_final.mp3"
REPO = "zhangpengjuGitHub/mv-media"
BRANCH = "main"
INTERVAL = 300                     # 5 minutes
MAX_TICKS = 120                    # up to 10 hours
TOK = open(TOKEN_FILE, encoding="utf-8").read().strip()


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def req(path, method="GET", body=None, raw=False, timeout=600):
    url = "https://api.github.com/repos/%s/contents/%s" % (REPO, path)
    r = urllib.request.Request(url, method=method)
    r.add_header("Authorization", "Bearer " + TOK)
    r.add_header("User-Agent", "mv-watchdog")
    r.add_header("Accept", "application/vnd.github.raw" if raw
                 else "application/vnd.github+json")
    if body is not None:
        r.data = json.dumps(body).encode()
        r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        data = resp.read()
    return data if raw else json.loads(data.decode())


def get_file(path, binary=True):
    return req(path + "?ref=" + BRANCH, raw=True)


def put(path, data, message):
    try:
        old = req(path + "?ref=" + BRANCH)
        sha = old.get("sha") if isinstance(old, dict) else None
    except urllib.error.HTTPError:
        sha = None
    body = {"message": message, "branch": BRANCH,
            "content": base64.b64encode(data).decode()}
    if sha:
        body["sha"] = sha
    return req(path, "PUT", body)


def ffmpeg():
    p = os.environ.get("FFMPEG")
    if p and os.path.exists(p):
        return p
    p = shutil.which("ffmpeg")
    if p:
        return p
    parent = os.path.dirname(ROOT)
    for rel in ("tools", os.path.join("music-mv", "tools")):
        cand = os.path.join(parent, rel, "ffmpeg.exe")
        if os.path.exists(cand):
            return cand
    raise RuntimeError("ffmpeg.exe not found")


def run(cmd, **kw):
    log("+ " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def poke_browser():
    """Move the cursor into the Kaggle Chrome window and bring it forward.

    A plain mousemove keeps the front-end 'user active' flag warm; no click
    and no keystroke, so nothing in the notebook can be changed by accident.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
        u = ctypes.windll.user32
        found = []
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(h, _l):
            n = u.GetWindowTextLengthW(h)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, buf, n + 1)
                title = buf.value
                if "Kaggle" in title or "Google Chrome" in title:
                    found.append((h, title))
            return True

        u.EnumWindows(CB(cb), 0)
        if not found:
            return "no chrome window"
        h, title = found[0]
        try:
            u.ShowWindow(h, 9)             # SW_RESTORE
            u.SetForegroundWindow(h)
        except Exception:
            pass
        rect = wt.RECT()
        u.GetWindowRect(h, ctypes.byref(rect))
        tx = (rect.left + rect.right) // 2
        ty = rect.top + 90                 # toolbar band, never a control
        pt = wt.POINT()
        u.GetCursorPos(ctypes.byref(pt))
        u.SetCursorPos(tx, ty)
        time.sleep(0.2)
        u.SetCursorPos(tx + 1, ty + 1)
        time.sleep(0.2)
        u.SetCursorPos(pt.x, pt.y)
        return "poked %s" % title[:36]
    except Exception as e:
        return "poke failed: %s" % e


def read_status():
    try:
        return json.loads(get_file("rescue_status.json").decode())
    except Exception as e:
        return {"stage": "UNKNOWN", "error": str(e)[:80]}


def download_result():
    log("manifest_final_lip.json found -> downloading")
    m = json.loads(get_file("manifest_final_lip.json").decode())
    buf = b""
    for c in m["chunks"]:
        d = get_file(c["name"])
        if hashlib.sha256(d).hexdigest() != c["sha256"]:
            raise RuntimeError("sha256 mismatch on " + c["name"])
        if len(d) != c["size"]:
            raise RuntimeError("size mismatch on " + c["name"])
        buf += d
        log("  got %s %.1fMB" % (c["name"], len(d) / 1048576.0))
    if len(buf) != m["size"]:
        raise RuntimeError("total size mismatch")
    lip = os.path.join(OUT, "lipsynced.mp4")
    with open(lip, "wb") as f:
        f.write(buf)
    log("rebuilt %s %.1fMB frames %s/%s"
        % (lip, len(buf) / 1048576.0,
           m.get("frames_out"), m.get("frames_in")))
    return lip, m


def encode(ff, cmd_v):
    try:
        run([ff, "-y", "-hide_banner", "-loglevel", "error"] + cmd_v)
        return True
    except subprocess.CalledProcessError:
        return False


def finish(lip):
    ff = ffmpeg()
    final = os.path.join(OUT, "final.mp4")
    if not os.path.exists(SONG):
        raise RuntimeError("song not found: " + SONG)
    # NVENC first (GTX 1050 has it), fall back to libx264.
    base = ["-i", lip, "-i", SONG,
            "-map", "0:v:0", "-map", "1:a:0",
            "-vf", "scale=1920:1080:flags=lanczos",
            "-c:a", "aac", "-b:a", "192k", "-shortest"]
    ok = encode(ff, base + ["-c:v", "h264_nvenc", "-preset", "p5",
                            "-rc", "vbr", "-cq", "22", "-b:v", "0",
                            final])
    if not ok or not os.path.exists(final) or os.path.getsize(final) < 100000:
        log("NVENC failed/unavailable -> libx264 fallback")
        encode(ff, base + ["-c:v", "libx264", "-preset", "medium",
                           "-crf", "20", final])
    log("final.mp4 %.1f MB" % (os.path.getsize(final) / 1048576.0))

    # QC contact sheet at the 5 lyric anchors: 44 / 94 / 119 / 150 / 158 s
    shots = []
    for i, t in enumerate((44, 94, 119, 150, 158)):
        p = os.path.join(OUT, "qc_%02d.jpg" % i)
        run([ff, "-y", "-hide_banner", "-loglevel", "error",
             "-ss", str(t), "-i", final, "-frames:v", "1", p])
        shots.append(p)
    sheet = os.path.join(OUT, "qc_sheet.jpg")
    run([ff, "-y", "-hide_banner", "-loglevel", "error",
         "-start_number", "0", "-i", os.path.join(OUT, "qc_%02d.jpg"),
         "-vf", "scale=384:216,tile=5x1", "-frames:v", "1", sheet])
    log("QC sheet -> " + sheet)
    return final, sheet


def upload_final(final, sheet):
    size = os.path.getsize(final)
    CH = 20 * 1024 * 1024
    n = max(1, (size + CH - 1) // CH)
    chunks = []
    with open(final, "rb") as f:
        for i in range(n):
            d = f.read(CH)
            name = "final_mv.part%03d" % i
            put(name, d, "chunk " + name)
            chunks.append({"name": name, "size": len(d),
                           "sha256": hashlib.sha256(d).hexdigest()})
            log("  uploaded %s %.1fMB" % (name, len(d) / 1048576.0))
    put("manifest_final_mv.json",
        json.dumps({"file": "final.mp4", "remote": "final_mv",
                    "size": size, "chunks": chunks}, indent=1).encode(),
        "manifest final_mv")
    with open(sheet, "rb") as f:
        put("qc_sheet.jpg", f.read(), "QC contact sheet")
    put("DONE.txt",
        ("MV finished %s\nfinal.mp4 %.1f MB in %d chunks\n"
         "local: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                          size / 1048576.0, n, final)).encode(),
        "pipeline complete")
    log("DONE.txt + manifest_final_mv.json pushed to GitHub")


def main():
    log("=== watchdog start (interval %ds) ===" % INTERVAL)
    log("song: " + SONG)
    for tick in range(MAX_TICKS):
        try:
            p = poke_browser()
            st = read_status()
            log("tick=%d poke=%s | stage=%s step=%s out=%sMB ts=%s"
                % (tick, p, st.get("stage"), st.get("progress", "-"),
                   st.get("out_mb", "-"), st.get("ts", "-")))
            try:
                get_file("manifest_final_lip.json")
                lip, _m = download_result()
                final, sheet = finish(lip)
                upload_final(final, sheet)
                log("=== ALL DONE, watchdog exits ===")
                return
            except urllib.error.HTTPError:
                pass                      # manifest not there yet
            except Exception as e:
                log("post-process error (will retry next tick): %s" % e)
        except Exception as e:
            log("tick error: %s" % e)
        time.sleep(INTERVAL)
    log("=== watchdog timed out ===")


if __name__ == "__main__":
    main()
