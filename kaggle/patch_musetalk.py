# -*- coding: utf-8 -*-
"""Patch MuseTalk scripts/inference.py so a bad face bbox cannot break the output.

Symptom (verified 2026-11-04 on Kaggle T4):
  log shows `error bbox: (... y2 > 1080)`, then inference exits 0 but the
  resulting mp4 contains only 8 frames instead of 250 for a 10s / 25fps clip.

Cause:
  inference.py padding loop does
      try: cv2.resize(res_frame, (x2-x1, y2-y1))
      except: continue
  A skipped index leaves a hole in the %08d.png sequence; ffmpeg image2
  stops reading at the first missing number, so every later frame is lost.

Fix:
  On resize failure, write the untouched original frame at that exact index.
  That frame simply keeps its original mouth, which is visually harmless
  compared with truncating the whole video.
"""
import os
import shutil
import sys

P = os.environ.get("MT_INFERENCE", "/kaggle/working/musetalk/scripts/inference.py")

OLD = """                try:
                    res_frame = cv2.resize(res_frame.astype(np.uint8), (x2-x1, y2-y1))
                except:
                    continue
"""

NEW = """                try:
                    res_frame = cv2.resize(res_frame.astype(np.uint8), (x2-x1, y2-y1))
                except:
                    # MV-LIP PATCH: keep %08d.png contiguous. A skipped index makes
                    # ffmpeg image2 stop early (250-frame clip -> 8-frame output).
                    cv2.imwrite(f"{result_img_save_path}/{str(i).zfill(8)}.png", ori_frame)
                    continue
"""


def main():
    if not os.path.exists(P):
        raise SystemExit("not found: " + P)
    s = open(P, encoding="utf-8").read()
    if "MV-LIP PATCH" in s:
        print("ALREADY_PATCHED")
        return
    if OLD not in s:
        print("PATTERN_NOT_FOUND - MuseTalk version differs, patch manually")
        sys.exit(2)
    shutil.copy2(P, P + ".bak")
    open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW, 1))
    print("PATCHED", P)


if __name__ == "__main__":
    main()
