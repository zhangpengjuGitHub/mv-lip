#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Kaggle side: rescue the OOM-killed full run.

What it does
  1. Kill any leftover 1080p inference (it ate 30.8GB RAM and got OOM-restarted).
  2. Downscale the input to 1280x720 (RAM 30.8GB -> ~15GB, no quality loss in
     the mouth region since MuseTalk only generates a 256x256 crop anyway).
  3. Reuse the already-saved face coordinates (4853 frames, 39 min of face
     detection already done) by scaling every bbox by 2/3.
  4. Launch MuseTalk 1.5 with --use_saved_coord --saved_coord, detached from
     the Jupyter kernel so a kernel restart cannot kill it.
  5. Every 60s: refresh rescue_status.json on the private mv-media repo,
     check the inference process, and when the mp4 is finished upload it in
     20MB chunks + a sha256 manifest (remote name: final_lip).

Launch from the Kaggle console (detached from the kernel):

  !curl -fsSL -o /kaggle/working/rescue_run.py https://raw.githubusercontent.com/zhangpengjuGitHub/mv-lip/main/kaggle/rescue_run.py
  !python3 -c "import subprocess; subprocess.Popen('python3 -u /kaggle/working/rescue_run.py > /kaggle/temp/rescue.log 2>&1', shell=True, start_new_session=True)"

Only stdlib is used, so the system python is fine.
"""
import os
import re
import sys
import json
import time
import glob
import base64
import pickle
import shutil
import hashlib
import subprocess
import urllib.request
import urllib.error

WORK = "/kaggle/working"
MT = WORK + "/musetalk"
TEMP = "/kaggle/temp"
RESULTS = MT + "/results"                 # symlink -> /kaggle/temp/mt_results
PKL = RESULTS + "/mv_clean_25fps.pkl"
PKL_BAK = PKL + ".1080.bak"
SRC = WORK + "/media/mv_clean_25fps.mp4"
VOCAL = WORK + "/media/vocal_16k.wav"
DST_DIR = TEMP + "/mv720"
DST = DST_DIR + "/mv_clean_25fps.mp4"    # same basename -> same pkl name
INFER_LOG = TEMP + "/infer720.log"
TOKEN_FILE = WORK + "/token.txt"
PY = WORK + "/mtenv/bin/python"
REPO = "zhangpengjuGitHub/mv-media"
BRANCH = "main"
SCALE = 2.0 / 3.0                        # 1920x1080 -> 1280x720
CHUNK = 20 * 1024 * 1024
V15 = RESULTS + "/mv_lip/v15"
TARGET = V15 + "/mv_clean_25fps_vocal_16k.mp4"

TOK = open(TOKEN_FILE).read().strip()


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(TEMP + "/rescue.log", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def api(path, method="GET", body=None, timeout=600):
    url = "https://api.github.com/repos/%s/contents/%s" % (REPO, path)
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", "Bearer " + TOK)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "mv-rescue")
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def put(path, data, message):
    st, old = api(path + "?ref=" + BRANCH)
    sha = old.get("sha") if st == 200 else None
    body = {"message": message, "branch": BRANCH,
            "content": base64.b64encode(data).decode()}
    if sha:
        body["sha"] = sha
    st, resp = api(path, "PUT", body)
    if st not in (200, 201):
        raise RuntimeError("PUT %s -> %s %s" % (path, st, resp))
    return st


def status(**kw):
    kw["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        put("rescue_status.json",
            json.dumps(kw, ensure_ascii=False, indent=1).encode(),
            "rescue status " + str(kw.get("stage", "")))
    except Exception as e:
        log("status upload failed: %s" % e)


def progress():
    """Last tqdm step of the UNet loop (x/607). -1 = not started yet."""
    try:
        with open(INFER_LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8192))
            data = f.read().decode("utf-8", "ignore")
        m = re.findall(r"(\d+)/607", data.replace("\r", "\n"))
        return int(m[-1]) if m else -1
    except Exception:
        return -1


def frame_count(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-count_frames", "-show_entries", "stream=nb_read_frames",
         "-of", "csv=p=0", p], capture_output=True, text=True)
    try:
        return int(r.stdout.strip().split(",")[0])
    except Exception:
        return -1


def scale_coords():
    if os.path.exists(PKL_BAK):
        log("coords already scaled, skip")
        return
    shutil.copy2(PKL, PKL_BAK)
    with open(PKL, "rb") as f:
        coords = pickle.load(f)
    out = []
    for c in coords:
        if isinstance(c, (list, tuple)) and len(c) >= 4:
            try:
                v = [int(round(float(x) * SCALE)) for x in c[:4]] + list(c[4:])
                out.append(tuple(v) if isinstance(c, tuple) else v)
                continue
            except Exception:
                pass
        out.append(c)
    with open(PKL, "wb") as f:
        pickle.dump(out, f)
    log("scaled %d face coords by 2/3" % len(out))


def upload_mp4(path):
    size = os.path.getsize(path)
    n = max(1, (size + CHUNK - 1) // CHUNK)
    chunks = []
    with open(path, "rb") as f:
        for i in range(n):
            data = f.read(CHUNK)
            name = "final_lip.part%03d" % i
            put(name, data, "chunk " + name)
            chunks.append({"name": name, "size": len(data),
                           "sha256": hashlib.sha256(data).hexdigest()})
            log("uploaded %s (%.1f MB)" % (name, len(data) / 1048576.0))
    n_in, n_out = frame_count(DST), frame_count(path)
    manifest = {"file": "lipsynced.mp4", "remote": "final_lip",
                "size": size, "chunks": chunks,
                "frames_in": n_in, "frames_out": n_out,
                "resolution": "1280x720"}
    put("manifest_final_lip.json",
        json.dumps(manifest, indent=1).encode(), "manifest final_lip")
    log("frames %s -> %s, manifest written" % (n_in, n_out))
    return n_in, n_out, size


def main():
    log("=== rescue start ===")
    status(stage="START", note="killing old 1080p inference")

    subprocess.run("pkill -9 -f 'scripts.inference' || true; "
                   "pkill -9 -f 'run_lipsync.py' || true", shell=True)
    time.sleep(3)

    for p in (PKL, SRC, VOCAL, PY):
        if not os.path.exists(p):
            log("FATAL missing " + p)
            status(stage="FAILED", error="missing " + p)
            return

    os.makedirs(DST_DIR, exist_ok=True)
    if not os.path.exists(DST) or os.path.getsize(DST) < 1000000:
        log("downscale 1080p -> 720p ...")
        status(stage="DOWNSCALE")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", SRC,
             "-vf", "scale=1280:720:flags=lanczos",
             "-r", "25", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "18", "-pix_fmt", "yuv420p", "-an", DST],
            check=True)
    log("720p input %.1f MB" % (os.path.getsize(DST) / 1048576.0))

    scale_coords()

    # Old 1080p PNG frames and the broken 8-frame result MUST go, otherwise
    # inference would read 1080p frames with 720p coordinates.
    shutil.rmtree(V15, ignore_errors=True)
    os.makedirs(V15, exist_ok=True)

    cfg = MT + "/configs/inference/mv_lip.yaml"
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("task_0:\n")
        f.write('  video_path: "%s"\n' % DST)
        f.write('  audio_path: "%s"\n' % VOCAL)

    model = MT + "/models/musetalkV15/unet.pth"
    mcfg = MT + "/models/musetalkV15/musetalk.json"
    for p in (model, mcfg):
        if not os.path.exists(p):
            log("FATAL missing weight " + p)
            status(stage="FAILED", error="missing " + p)
            return

    cmd = [PY, "-m", "scripts.inference",
           "--inference_config", cfg,
           "--result_dir", RESULTS + "/mv_lip",
           "--unet_model_path", model,
           "--unet_config", mcfg,
           "--version", "v15",
           "--bbox_shift", "0",
           "--use_saved_coord", "--saved_coord",
           "--batch_size", "8"]
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"
    lf = open(INFER_LOG, "w")
    proc = subprocess.Popen(cmd, cwd=MT, stdout=lf,
                            stderr=subprocess.STDOUT,
                            start_new_session=True, env=env)
    log("inference pid=%d" % proc.pid)
    status(stage="INFER", pid=proc.pid, progress=0,
           note="720p + saved coords, RAM ~15GB")

    # Watch loop: 60s tick, status pushed every 5 min.
    last_size, stable = -1, 0
    for tick in range(300):                # up to 5h
        time.sleep(60)
        pr = progress()
        alive = proc.poll() is None
        size = os.path.getsize(TARGET) if os.path.exists(TARGET) else 0
        stable = stable + 1 if (size > 0 and size == last_size) else 0
        last_size = size
        if tick % 5 == 0 or not alive:
            status(stage="INFER", progress=pr, alive=alive,
                   out_mb=round(size / 1048576.0, 1), minute=tick,
                   pid=proc.pid)
        log("tick=%d step=%s alive=%s out=%.1fMB stable=%d"
            % (tick, pr, alive, size / 1048576.0, stable))
        if not alive:
            break
        if size > 0 and stable >= 2:
            break

    time.sleep(20)
    if not os.path.exists(TARGET) or os.path.getsize(TARGET) < 1000000:
        log("FAILED: no output mp4")
        status(stage="FAILED", progress=progress(),
               error="inference ended without mp4, see infer720.log")
        return

    n_in, n_out = frame_count(DST), frame_count(TARGET)
    if 0 < n_out < n_in * 0.95:
        log("FAILED: frame count %s/%s" % (n_out, n_in))
        status(stage="FAILED", error="frame count %s/%s" % (n_out, n_in))
        return

    status(stage="UPLOAD", progress=progress(),
           note="mp4 ready, uploading 20MB chunks")
    a, b, size = upload_mp4(TARGET)
    status(stage="DONE", frames_in=a, frames_out=b, size=size,
           note="final_lip manifest uploaded")
    log("=== ALL DONE ===")


if __name__ == "__main__":
    main()
