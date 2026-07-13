
import os
import platform
import subprocess
from pathlib import Path
from tkinter import Tk
from gui.main_window.main import MainWindow


def _configure_local_fontconfig():
    if platform.system().lower() != "linux":
        return

    project_root = Path(__file__).resolve().parents[1]
    font_dirs = [
        project_root / "gui" / "main_window" / "assets" / "font",
        project_root / "gui" / "main_window" / "assets" / "fonts",
        project_root / "gui" / "assets" / "font",
        project_root / "gui" / "assets" / "fonts",
        project_root / "assets" / "font",
        project_root / "assets" / "fonts",
    ]
    font_dirs = [d for d in font_dirs if d.exists()]
    if not font_dirs:
        return

    conf_dir = project_root / ".fontconfig"
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_file = conf_dir / "aitueyes-fonts.conf"

    dir_xml = "\n".join(f"  <dir>{d.as_posix()}</dir>" for d in font_dirs)
    conf_xml = (
        "<?xml version=\"1.0\"?>\n"
        "<!DOCTYPE fontconfig SYSTEM \"fonts.dtd\">\n"
        "<fontconfig>\n"
        "  <include ignore_missing=\"yes\">/etc/fonts/fonts.conf</include>\n"
        f"{dir_xml}\n"
        "</fontconfig>\n"
    )
    conf_file.write_text(conf_xml, encoding="utf-8")

    os.environ["FONTCONFIG_FILE"] = str(conf_file)
    os.environ.setdefault("FONTCONFIG_PATH", "/etc/fonts")

    for font_dir in font_dirs:
        try:
            subprocess.run(["fc-cache", "-f", str(font_dir)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def run_app():
    _configure_local_fontconfig()
    root = Tk()
    root.withdraw()
    MainWindow(root)
    root.mainloop()

if __name__ == "__main__":
    run_app()
