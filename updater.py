import sys, os, json, hashlib, subprocess, threading, queue, urllib.request
from tkinter import messagebox
import version

API = f"https://api.github.com/repos/{version.REPO}/releases/latest"
EXE_NAME = "ChessHelper.exe"

def parse(v):
    return tuple(int(x) for x in v.strip().lstrip("vV").split(".") if x.isdigit())

def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "ChessHelper-updater"})
    return urllib.request.urlopen(req, timeout=timeout)

def fetch_latest():
    with _get(API) as r:
        data = json.loads(r.read().decode("utf-8"))
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    return data.get("tag_name", ""), assets, data.get("body", "")

def download_verified(assets, dest):
    if EXE_NAME not in assets or EXE_NAME + ".sha256" not in assets:
        raise RuntimeError("Release is missing the exe or its .sha256 file.")
    with _get(assets[EXE_NAME + ".sha256"]) as r:
        want = r.read().decode("utf-8", "ignore").split()[0].strip().lower()
    h = hashlib.sha256()
    with _get(assets[EXE_NAME], timeout=60) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            f.write(chunk)
    if h.hexdigest().lower() != want:
        os.remove(dest)
        raise RuntimeError("Checksum mismatch, update discarded.")

def install_and_restart(root, new_path):
    cur = sys.executable
    bat = os.path.join(os.path.dirname(cur), "update.bat")
    with open(bat, "w") as f:
        f.write(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            ":retry\r\n"
            f'move /y "{new_path}" "{cur}" >nul 2>&1\r\n'
            "if errorlevel 1 (timeout /t 1 /nobreak >nul & goto retry)\r\n"
            f'start "" "{cur}"\r\n'
            'del "%~f0"\r\n')
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen(["cmd", "/c", bat], env=env, close_fds=True,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    root.destroy()
    os._exit(0)

def check_async(root, log):
    """Runs in the background; asks the user on the main thread if a newer version exists."""
    q = queue.Queue()

    def work():
        try:
            q.put(("ok",) + fetch_latest())
        except Exception as e:
            q.put(("err", str(e)))
    threading.Thread(target=work, daemon=True).start()

    def poll():
        try:
            res = q.get_nowait()
        except queue.Empty:
            root.after(300, poll)
            return
        if res[0] == "err":
            log(f"Update check skipped: {res[1]}")
            return
        _, tag, assets, notes = res
        try:
            newer = parse(tag) > parse(version.VERSION)
        except Exception:
            newer = False
        if not newer:
            log(f"You're up to date (v{version.VERSION}).")
            return
        if not getattr(sys, "frozen", False):
            log(f"Version {tag} is available (running from source, not updating).")
            return
        if not messagebox.askyesno("Update available",
                f"Version {tag} is available (you have v{version.VERSION}).\n\n"
                f"{notes[:500]}\n\nUpdate now?"):
            return
        try:
            dest = os.path.join(os.path.dirname(sys.executable), "ChessHelper_update.exe")
            log("Downloading update...")
            download_verified(assets, dest)
            install_and_restart(root, dest)
        except Exception as e:
            log(f"Update failed: {e}")
            messagebox.showerror("Update failed", str(e))
    poll()