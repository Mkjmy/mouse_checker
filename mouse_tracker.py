import glob
import os
import select
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

POS_FILE = Path(__file__).resolve().parent / "positions.txt"
KEY_N = 46
EV_KEY = 1
EVENT_SIZE = struct.calcsize("llHHi")

current_pos = None
lock = threading.Lock()
print_lock = threading.Lock()


def get_cursor_pos():
    try:
        out = subprocess.run(
            ["hyprctl", "cursorpos"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        if out:
            x, y = out.split(",")
            return int(x.strip()), int(y.strip())
    except Exception:
        pass
    return None


def track_cursor():
    global current_pos
    while True:
        p = get_cursor_pos()
        if p:
            with lock:
                current_pos = p
        time.sleep(0.02)


saved_positions = []


def save_position():
    global saved_positions
    with lock:
        p = current_pos
    if p:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(POS_FILE, "a") as f:
            f.write(f"{stamp}  x={p[0]}  y={p[1]}\n")
        saved_positions.append((stamp, p[0], p[1]))
        with print_lock:
            sys.stdout.write("\n")
            print(f"*** SAVED #{len(saved_positions)}  {stamp}  x={p[0]}  y={p[1]} ***")
            for i, (t, x, y) in enumerate(saved_positions, 1):
                print(f"   {i}. {t}  x={x}  y={y}")
            sys.stdout.write(f"\r\033[2KCursor: x={p[0]}  y={p[1]}   |   press N to save")
            sys.stdout.flush()


def read_keys():
    fds = {}
    for dev in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
            fds[fd] = b""
        except OSError:
            continue
    if not fds:
        print("Cannot read input devices. Run as root or join the 'input' group.")
        return
    print(f"Listening on {len(fds)} input device(s).", file=sys.stderr)
    while True:
        try:
            r, _, _ = select.select(list(fds), [], [])
            for fd in r:
                try:
                    fds[fd] += os.read(fd, 1024)
                except (BlockingIOError, InterruptedError):
                    continue
                except OSError as e:
                    print(f"Device dropped ({e}), reopening...", file=sys.stderr)
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    del fds[fd]
                    for dev in sorted(glob.glob("/dev/input/event*")):
                        try:
                            nfd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
                            fds[nfd] = b""
                        except OSError:
                            continue
                    if not fds:
                        time.sleep(0.5)
                        return read_keys()
                    continue
                while len(fds[fd]) >= EVENT_SIZE:
                    _, _, ev_type, code, value = struct.unpack("llHHi", fds[fd][:EVENT_SIZE])
                    if ev_type == EV_KEY and code == KEY_N and value in (1, 2):
                        save_position()
                    fds[fd] = fds[fd][EVENT_SIZE:]
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            time.sleep(0.1)


def display_cursor():
    while True:
        with lock:
            p = current_pos
        if p:
            with print_lock:
                sys.stdout.write(f"\r\033[2KCursor: x={p[0]}  y={p[1]}   |   press N to save")
                sys.stdout.flush()
        time.sleep(0.05)


def main():
    print(f"Saving positions to: {POS_FILE}")
    print("Move the mouse, then press N to save the position. Ctrl+C to quit.")
    threading.Thread(target=track_cursor, daemon=True).start()
    threading.Thread(target=read_keys, daemon=True).start()
    display_cursor()


if __name__ == "__main__":
    main()
