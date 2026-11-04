#!/usr/bin/env python
"""Kaggle side: pull MV assets from private repo mv-media and rebuild the full video.

Prereq: /kaggle/working/token.txt contains a GitHub PAT with repo scope.

Result:
  /kaggle/working/media/mv_clean_25fps.mp4   (194s, 25fps, 1080p)
  /kaggle/working/media/vocal_16k.wav        (16k mono dry vocal)
"""
import os, sys, json, shutil, subprocess, urllib.request, hashlib, glob, re

REPO = "zhangpengjuGitHub/mv-media"
WORK = "/kaggle/working"
MEDIA = WORK + "/media"
TOKEN_FILE = WORK + "/token.txt"
os.makedirs(MEDIA, exist_ok=True)


def api_download(tok):
    """Fallback: fetch raw bytes chunk-by-chunk through api.github.com."""
    def raw(path):
        req = urllib.request.Request(
            "https://api.github.com/repos/%s/contents/%s" % (REPO, path))
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("Accept", "application/vnd.github.raw")
        req.add_header("User-Agent", "mv-media-dl")
        with urllib.request.urlopen(req, timeout=900) as r:
            return r.read()

    manifest = json.loads(raw("manifest.json"))
    ok = True
    for f in manifest["files"]:
        buf = b""
        for c in f["chunks"]:
            d = raw(c["name"])
            if hashlib.sha256(d).hexdigest() != c["sha256"]:
                print("SHA MISMATCH", c["name"], flush=True)
                ok = False
            buf += d
        out = os.path.join(MEDIA, f["file"])
        with open(out, "wb") as fp:
            fp.write(buf)
        print("rebuilt", f["file"], len(buf), "expected", f["size"], flush=True)
        if len(buf) != f["size"]:
            ok = False
    # dry vocal is not in the manifest (uploaded by the test run)
    with open(os.path.join(MEDIA, "vocal_16k.wav"), "wb") as fp:
        fp.write(raw("input/vocal_16k.part000"))
    print("vocal_16k.wav ok", flush=True)
    return ok


def rebuild_from_parts(src):
    """Join *.partNNN byte chunks back into the original files."""
    groups = {}
    for p in sorted(glob.glob(os.path.join(src, "*.part*"))):
        base = re.sub(r"\.part\d+$", "", os.path.basename(p))
        groups.setdefault(base, []).append(p)
    for base, parts in groups.items():
        parts.sort(key=lambda x: int(x.rsplit(".part", 1)[1]))
        target = base + (".wav" if base.startswith("vocal") else ".mp4")
        out = os.path.join(MEDIA, target)
        with open(out, "wb") as w:
            for p in parts:
                with open(p, "rb") as r:
                    shutil.copyfileobj(r, w, 1024 * 1024)
        print("joined", target, os.path.getsize(out), flush=True)


def main():
    tok = open(TOKEN_FILE).read().strip()
    clone_dir = WORK + "/mv-media"
    if os.path.isdir(clone_dir):
        shutil.rmtree(clone_dir)
    # Kaggle has unrestricted access to github.com, so a plain clone is fastest.
    r = subprocess.run(
        ["git", "clone", "-q", "https://%s@github.com/%s.git" % (tok, REPO), clone_dir],
        capture_output=True, text=True, timeout=1200)
    if r.returncode == 0:
        print("git clone OK", flush=True)
        rebuild_from_parts(os.path.join(clone_dir, "input"))
    else:
        print("git clone failed, fallback to Contents API:", r.stderr[-300:], flush=True)
        api_download(tok)

    # Reassemble the 4 lossless mp4 segments into one continuous video.
    segs = sorted(glob.glob(os.path.join(MEDIA, "mv_part_*.mp4")))
    if len(segs) != 4:
        print("FATAL: expect 4 segments, got", len(segs), flush=True)
        sys.exit(1)
    lst = WORK + "/concat.txt"
    with open(lst, "w") as f:
        for s in segs:
            f.write("file '%s'\n" % s)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    full = os.path.join(MEDIA, "mv_clean_25fps.mp4")
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", full],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    print("video rebuilt:", full, os.path.getsize(full), flush=True)

    vocal = os.path.join(MEDIA, "vocal_16k.wav")
    print("vocal:", vocal, os.path.getsize(vocal), flush=True)
    print("FETCH_MEDIA_DONE", flush=True)


if __name__ == "__main__":
    main()
