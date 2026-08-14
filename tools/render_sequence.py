"""Render only the frames that are missing, one per timer tick, then quit.

Blender 3.3.1 on this machine segfaults intermittently part-way through a long
EEVEE sequence - macOS 15.6 against a 2022 build on an integrated GPU.  The
crash is not reproducible at a particular frame and not worth chasing, so this
script is built to be killed and restarted instead of to run perfectly once:

* it renders only frames with no PNG on disk, so a restart resumes rather than
  starting over;
* it renders one frame per application timer rather than in a single blocking
  loop, so the process stays responsive and a crash costs at most one frame;
* it quits when the last frame lands, which is the signal the supervising
  shell loop watches for.

Usage:

    blender scene.blend -P tools/render_sequence.py -- OUT_DIR FIRST LAST
"""

import os
import sys

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv else "//frames"
    first = int(argv[1]) if len(argv) > 1 else bpy.context.scene.frame_start
    last = int(argv[2]) if len(argv) > 2 else bpy.context.scene.frame_end
    return out_dir, first, last


def missing_frames(out_dir, first, last):
    return [f for f in range(first, last + 1)
            if not os.path.exists(os.path.join(out_dir, "f_%04d.png" % f))]


def main():
    out_dir, first, last = parse_args()
    os.makedirs(out_dir, exist_ok=True)

    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"

    todo = missing_frames(out_dir, first, last)
    print("[render_sequence] %d frames outstanding" % len(todo))
    if not todo:
        bpy.ops.wm.quit_blender()
        return

    state = {"todo": todo}

    def tick():
        remaining = state["todo"]
        if not remaining:
            print("[render_sequence] complete")
            bpy.ops.wm.quit_blender()
            return None
        frame = remaining.pop(0)
        # Re-check: a previous run may have written it after we listed.
        path = os.path.join(out_dir, "f_%04d" % frame)
        if os.path.exists(path + ".png"):
            return 0.01
        scene.frame_set(frame)
        scene.render.filepath = path
        try:
            bpy.ops.render.render(write_still=True)
        except Exception as error:  # noqa: BLE001 - keep going on a bad frame
            print("[render_sequence] frame %d failed: %s" % (frame, error))
        return 0.01

    bpy.app.timers.register(tick, first_interval=1.0)


if __name__ == "__main__":
    main()
