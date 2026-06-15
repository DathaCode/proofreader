# PyInstaller .exe Packaging

The real spec is `build.spec` (single-file, windowed). Build with:
```powershell
python -m PyInstaller build.spec --clean --noconfirm   # -> dist/SinhalaProofreader.exe
```
…or double-click `build.bat` (installs deps + builds). Close any running
`SinhalaProofreader.exe` first — it locks the output file.

## Resource path for bundled files (icon, etc.)
```python
import sys, os
def resource_path(*parts):
    """Works in dev AND inside the frozen .exe."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)
# Usage: resource_path("assets", "icon.png")
```

## build.spec essentials
```python
# Bundle the icon(s) so the running app can set its window/taskbar icon.
datas = []
for _icon in ("icon.ico", "icon.png"):
    p = os.path.join("assets", _icon)
    if os.path.exists(p):
        datas += [(p, "assets")]
datas += collect_data_files("customtkinter")          # CTk theme JSON/assets

hiddenimports = ["customtkinter", "requests",
                 "engine.corrections_db", "engine.lan_proxy_engine"]
hiddenimports += collect_submodules("google.generativeai")        # Direct mode
hiddenimports += collect_submodules("google.ai.generativelanguage")

# Windows EXE icons must be .ico (fall back to .png only if no .ico).
icon_file = os.path.join("assets", "icon.ico")
if not os.path.exists(icon_file):
    icon_file = os.path.join("assets", "icon.png")

exe = EXE(..., name="SinhalaProofreader", console=False, icon=icon_file)
```
`EXCLUDES` in the spec drops heavy unused libs (torch, numpy, scipy, …) to keep
the `.exe` small and the build fast.

## App icon workflow
- Source of truth: `assets/icon.png`.
- Generate `assets/icon.ico` (square, multi-size) from it with Pillow:
```python
from PIL import Image
im = Image.open("assets/icon.png").convert("RGBA")
s = max(im.size); c = Image.new("RGBA", (s, s), (0,0,0,0))
c.paste(im, ((s-im.width)//2, (s-im.height)//2), im)
c.save("assets/icon.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
```
- The window icon is set at runtime in `MainWindow._set_app_icon()`:
  `iconphoto(True, PhotoImage(png))` (cross-platform + child Toplevels) and, on
  Windows, `iconbitmap(ico)` for a crisp title-bar/taskbar icon.
- `sqlite3` is stdlib — PyInstaller bundles it automatically; no spec change needed
  for the corrections DB (it's created at runtime under `~/.sinhala_proofreader/`).

## Config / data NOT inside the .exe
- `~/.sinhala_proofreader/config.json` (settings + key, Direct mode)
- `~/.sinhala_proofreader/corrections.db` (SQLite learned-corrections cache)
- These persist across `.exe` updates — the user's key/data are never lost.
