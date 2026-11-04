#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Kaggle -> private mv-media repo. Handles >100MB files by 20MB chunks.

Usage:
  python kaggle/upload_result.py \
      /kaggle/working/pc2_status.txt pc2_status.txt \
      /kaggle/working/media/lipsynced.mp4 final_lip

Each file becomes <remote_name>.partNNN plus a manifest_<remote_name>.json
with per-chunk sha256. Uses only stdlib so the system python is fine.
"""
import os
import sys
import json
import base64
import hashlib
import urllib.request
import urllib.error

REPO = "zhangpengjuGitHub/mv-media"
BRANCH = "main"
TOKEN_FILE = "/kaggle/working/token.txt"
CHUNK = 20 * 1024 * 1024


def api(path, method="GET", body=None, timeout=600):
    url = "https://api.github.com/repos/%s/contents/%s" % (REPO, path)
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", "Bearer " + TOK)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "mv-result-up")
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
        raise RuntimeError("upload failed %s -> %s %s" % (path, st, resp))
    return st


def upload(local, remote):
    size = os.path.getsize(local)
    n = max(1, (size + CHUNK - 1) // CHUNK)
    chunks = []
    with open(local, "rb") as f:
        for i in range(n):
            data = f.read(CHUNK)
            name = "%s.part%03d" % (remote, i)
            put(name, data, "chunk " + name)
            chunks.append({"name": name, "size": len(data),
                           "sha256": hashlib.sha256(data).hexdigest()})
            print("  %s %.1fMB OK" % (name, len(data) / 1048576.0), flush=True)
    manifest = {"file": os.path.basename(local), "remote": remote,
                "size": size, "chunks": chunks}
    put("manifest_" + remote + ".json",
        json.dumps(manifest, indent=1).encode(), "manifest " + remote)
    print("DONE", remote, size, "bytes in", n, "chunks", flush=True)


if __name__ == "__main__":
    TOK = open(TOKEN_FILE).read().strip()
    args = sys.argv[1:]
    if len(args) % 2 != 0:
        raise SystemExit("usage: upload_result.py <local> <remote> [<local> <remote> ...]")
    for i in range(0, len(args), 2):
        upload(args[i], args[i + 1])
    print("UPLOAD_ALL_DONE", flush=True)
