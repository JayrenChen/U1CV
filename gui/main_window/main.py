from pathlib import Path
import json
import os
import platform
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from tkinter import Toplevel, Frame, Canvas, Button
from tkinter import ttk

from gui.main_window.dashboard.gui import Dashboard
from gui.main_window.setting.main import Setting
from gui.camera_interface import CameraInterface

OUTPUT_PATH = Path(__file__).parent
ASSETS_PATH = OUTPUT_PATH / Path("./assets")
SETTINGS_PATH = OUTPUT_PATH.parents[1] / "runtime_settings.json"
LOGO_ICON_PATH = ASSETS_PATH / "icon_aitu.png"
LOGO_PATH = ASSETS_PATH / "logo_aitu.png"
ICON_HOME_PATH = ASSETS_PATH / "logo_home.png"
ICON_SETTING_PATH = ASSETS_PATH / "logo_setting.png"
PROJECT_ROOT = OUTPUT_PATH.parents[1]
LOCAL_FONT_CANDIDATES = {
    "msyh.ttf": [
        OUTPUT_PATH / "assets" / "font" / "msyh.ttf",
        OUTPUT_PATH / "assets" / "fonts" / "msyh.ttf",
        PROJECT_ROOT / "main_window" / "assets" / "font" / "msyh.ttf",
        PROJECT_ROOT / "assets" / "fonts" / "msyh.ttf",
        PROJECT_ROOT / "msyh.ttf",
    ],
    "arial.ttf": [
        OUTPUT_PATH / "assets" / "font" / "arial.ttf",
        OUTPUT_PATH / "assets" / "fonts" / "arial.ttf",
        PROJECT_ROOT / "main_window" / "assets" / "font" / "arial.ttf",
        PROJECT_ROOT / "assets" / "fonts" / "arial.ttf",
        PROJECT_ROOT / "arial.ttf",
    ],
}

def relative_to_assets(path: str) -> Path:
    return ASSETS_PATH / Path(path)

def mainWindow(root=None):
    return MainWindow(root)


class MainWindow(Toplevel):
    def __init__(self, root=None, *args, **kwargs):
        if root is None:
            from tkinter import Tk

            root = Tk()
            root.withdraw()

        Toplevel.__init__(self, root, *args, **kwargs)

        self.title("杰克艾图 - 工业布料检测系统")
        self.geometry("1400x860")
        self.minsize(1200, 760)
        self.iconphoto(False, tk.PhotoImage(file=str(LOGO_ICON_PATH)))
        self.configure(bg="#FFF4EC")

        self.current_window = None
        self.camera = None
        self.settings_path = SETTINGS_PATH
        self.default_settings = {
            "exposure_us": 50000.0,
            "bin_thresh": 60.0,
            "ppm": 5.0,
            "anchor_xmm": 10.0,
            "anchor_ymm": 10.0,
            "anchor_wmm": 30.0,
            "anchor_hmm": 30.0,
            "fabric_type": "矩形布料",
            "fabric_color_mode": "黑白布料",
            "hsv_lower": [0, 0, 0],
            "hsv_upper": [360, 100, 100],
        }
        self.runtime_settings = self._load_runtime_settings()
        self.logo_full = None
        self.logo_home = None
        self.logo_setting = None
        self._register_local_ui_fonts()
        self.ui_font_family = self._resolve_ui_font_family()
        self._print_font_diagnostics()

        self.palette = {
            "bg_main": "#FFFFFF",
            "bg_panel": "#FFFFFF",
            "bg_sidebar": "#FCD1AE",
            "bg_logo": "#FFFBF7",
            "bg_sidebar_active": "#EC9A56",
            "fg_title": "#7A3E0A",
            "fg_subtitle": "#A16207",
            "fg_key": "#9A4B0A",
            "fg_value": "#5C2A06",
            "primary": "#EA7A27",
            "primary_active": "#D96512",
            "warn": "#E05252",
            "warn_active": "#C24141",
            "indicator": "#FFFFFF",
            "canvas_dark": "#2A1E14",
            "canvas_line": "#8A684E",
            "canvas_hint": "#E0CBB8",
        }

        # 浅蓝备选配色（在此处取消注释并覆盖 self.palette 即可）
        # self.palette = {
        #     "bg_main": "#FFFFFF",
        #     "bg_panel": "#FFFFFF",
        #     "bg_sidebar": "#A5D0F8",
        #     "bg_logo": "#EEF5FC",
        #     "bg_sidebar_active": "#5A9DDA",
        #     "fg_title": "#0F4E8A",
        #     "fg_subtitle": "#2563A8",
        #     "fg_key": "#1D4F82",
        #     "fg_value": "#123C64",
        #     "primary": "#3B82F6",
        #     "primary_active": "#2563EB",
        #     "warn": "#E05252",
        #     "warn_active": "#C24141",
        #     "indicator": "#FFFFFF",
        #     "canvas_dark": "#182635",
        #     "canvas_line": "#476684",
        #     "canvas_hint": "#B8CCE2",
        # }

        self._build_style()
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    def _resolve_ui_font_family(self):
        available = list(tkfont.families(self))
        available_map = {name.lower(): name for name in available}
        forced = os.environ.get("AITUEYES_FORCE_FONT", "").strip()
        windowing_system = "unknown"
        try:
            windowing_system = self.tk.call("tk", "windowingsystem")
        except Exception:
            pass
        x11_core_mode = (windowing_system == "x11" and len(available) <= 80)

        if forced:
            actual = self._probe_tk_font_family(forced)
            if actual:
                print(f"[AituEyes] forced font requested={forced}, actual={actual}")
                return actual
            print(f"[AituEyes] forced font requested={forced}, but Tk probe failed; fallback to auto.")

        candidates = [
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "微软雅黑",
            "msyh",
            "Noto Sans CJK SC",
            "Noto Sans CJK",
            "WenQuanYi Micro Hei",
            "Source Han Sans SC",
            "Song Ti",
            "FangSong Ti",
            "Gothic",
            "Mincho",
            "Arial Unicode MS",
            "Arial",
            "PingFang SC",
            "DejaVu Sans",
        ]

        # In X11 core-font mode (common in remote sessions), prefer the families
        # that are actually exposed by Tk to avoid falling back unpredictably.
        if x11_core_mode:
            candidates = [
                "gothic",
                "song ti",
                "fangsong ti",
                "mincho",
            ] + candidates

        for family in candidates:
            real_name = available_map.get(family.lower())
            if real_name is not None:
                return real_name

        # Alias fallback: some distributions expose family names with slightly different variants.
        alias_tokens = ["yahei", "wenquanyi", "noto sans cjk", "source han", "song", "fangsong"]
        for token in alias_tokens:
            for key, real_name in available_map.items():
                if token in key:
                    return real_name

        # Final chance: ask Tk to resolve candidate names even if not in tkfont.families.
        for family in candidates:
            actual = self._probe_tk_font_family(family)
            if not actual:
                continue
            actual_l = actual.lower()
            if any(token in actual_l for token in ["yahei", "微软雅黑", "wenquanyi", "noto", "source han", "song", "fangsong"]):
                return actual
        return "TkDefaultFont"

    def _probe_tk_font_family(self, family_name):
        probe_name = "AituEyesProbeFont"
        try:
            self.tk.call("font", "delete", probe_name)
        except Exception:
            pass

        try:
            self.tk.call("font", "create", probe_name, "-family", family_name, "-size", 12)
            actual = self.tk.call("font", "actual", probe_name, "-family")
            self.tk.call("font", "delete", probe_name)
            if isinstance(actual, str) and actual.strip():
                return actual.strip()
        except Exception:
            return None
        return None

    def _register_local_ui_fonts(self):
        # Linux fonts are loaded from project-local fontconfig dirs configured before Tk startup.
        # Keep a best-effort local cache refresh here; do not copy files into ~/.local/share/fonts.
        if platform.system().lower() != "linux":
            return

        try:
            refreshed = set()
            for candidates in LOCAL_FONT_CANDIDATES.values():
                for candidate in candidates:
                    if candidate.exists():
                        d = str(candidate.parent)
                        if d in refreshed:
                            continue
                        refreshed.add(d)
                        subprocess.run(["fc-cache", "-f", d], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        break
        except Exception:
            pass

    def _print_font_diagnostics(self):
        available = list(tkfont.families(self))
        print(available)
        available_l = [f.lower() for f in available]
        key_hits = [f for f in available if any(k in f.lower() for k in ["yahei", "wenquanyi", "noto", "source han", "song", "fangsong", "gothic", "mincho"]) ]

        is_nomachine = any(os.environ.get(k) for k in ["NXSESSIONID", "NX_CLIENT", "NOMACHINE"]) or ("nx" in os.environ.get("XDG_SESSION_TYPE", "").lower())
        windowing_system = "unknown"
        try:
            windowing_system = self.tk.call("tk", "windowingsystem")
        except Exception:
            pass

        print(f"[AituEyes] UI font family: {self.ui_font_family}")
        print(f"[AituEyes] Tk windowing={windowing_system}, DISPLAY={os.environ.get('DISPLAY', '')}, NoMachine={is_nomachine}")
        print(f"[AituEyes] Tk families={len(available)}, CJK-like hits={key_hits[:12]}")

        # If NoMachine is active and YaHei is not visible to Tk, point out likely root cause.
        if is_nomachine and not any("yahei" in f for f in available_l):
            print("[AituEyes] Note: running under NoMachine and Tk cannot see YaHei in families. This usually means Tk is using the X server font set and not all fontconfig families are exposed.")

        if windowing_system == "x11" and len(available) <= 80:
            print("[AituEyes] Note: X11 core-font mode detected (small Tk family set). Tk may not expose all fc-list fonts; using visible CJK fallback families first.")

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        font = self.ui_font_family

        style.configure("Main.TFrame", background=self.palette["bg_main"])
        style.configure("Panel.TLabelframe", background=self.palette["bg_panel"], borderwidth=1, relief="solid")
        style.configure("Panel.TLabelframe.Label", background=self.palette["bg_panel"], foreground=self.palette["fg_key"], font=(font, 14, "bold"))
        style.configure("Title.TLabel", background=self.palette["bg_main"], foreground=self.palette["fg_title"], font=(font, 24, "bold"))
        style.configure("Subtitle.TLabel", background=self.palette["bg_main"], foreground=self.palette["fg_subtitle"], font=(font, 18, "bold"))

        style.configure("Key.TLabel", background=self.palette["bg_panel"], foreground=self.palette["fg_key"], font=(font, 10, "bold"))
        style.configure("Value.TLabel", background=self.palette["bg_panel"], foreground=self.palette["fg_value"], font=(font, 10))

        style.configure("Primary.TButton", font=(font, 12, "bold"), padding=10)
        style.map("Primary.TButton", background=[("active", self.palette["primary_active"]), ("!disabled", self.palette["primary"])], foreground=[("!disabled", "white")])

        style.configure("Warn.TButton", font=(font, 12, "bold"), padding=10)
        style.map("Warn.TButton", background=[("active", self.palette["warn_active"]), ("!disabled", self.palette["warn"])], foreground=[("!disabled", "white")])

    def _build_layout(self):
        root = ttk.Frame(self, style="Main.TFrame", padding=(10, 10, 10, 10))
        root.pack(fill="both", expand=True)

        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        sidebar = Frame(root, bg=self.palette["bg_sidebar"], width=200)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        content = ttk.Frame(root, style="Main.TFrame")
        content.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        content.rowconfigure(1, weight=1)
        content.columnconfigure(0, weight=1)

        header = ttk.Frame(content, style="Main.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(header, text="杰克艾图 - 工业布料检测系统", style="Title.TLabel").pack(anchor="w")

        self.content_area = ttk.Frame(content, style="Main.TFrame")
        self.content_area.grid(row=1, column=0, sticky="nsew")

        # sidebar content
        Canvas(sidebar, bg=self.palette["bg_logo"], highlightthickness=0, height=100, width=200).place(x=0, y=0)

        if LOGO_PATH.exists():
            try:
                self.logo_full = tk.PhotoImage(file=str(LOGO_PATH))
                self.logo_home = tk.PhotoImage(file=str(ICON_HOME_PATH))
                self.logo_home = self.logo_home.subsample(8, 8)
                self.logo_setting = tk.PhotoImage(file=str(ICON_SETTING_PATH))
                self.logo_setting = self.logo_setting.subsample(8, 8)
                logo_label = tk.Label(sidebar, image=self.logo_full, bg=self.palette["bg_logo"], bd=0, highlightthickness=0)
                logo_label.place(x=18, y=18)
            except Exception:
                self.logo_full = None
                self.logo_home = None
                self.logo_setting = None

        self.sidebar_indicator = Frame(sidebar, background=self.palette["indicator"])
        self.sidebar_indicator.place(x=0, y=130, height=46, width=6)

        self.dashboard_btn = Button(
            sidebar,
            text="  主页",
            image=self.logo_home,
            compound="left",
            fg="white",
            bg=self.palette["bg_sidebar"],
            bd=0,
            relief="flat",
            font=(self.ui_font_family, 14, "bold"),
            activebackground=self.palette["bg_sidebar_active"],
            activeforeground="white",
            command=lambda: self.handle_btn_press("dash", 130),
        )
        self.dashboard_btn.place(x=20, y=130, width=150, height=46)

        self.setting_btn = Button(
            sidebar,
            text="  设置",
            image=self.logo_setting,
            compound="left",
            fg="white",
            bg=self.palette["bg_sidebar"],
            bd=0,
            relief="flat",
            font=(self.ui_font_family, 14, "bold"),
            activebackground=self.palette["bg_sidebar_active"],
            activeforeground="white",
            command=lambda: self.handle_btn_press("set", 182),
        )
        self.setting_btn.place(x=20, y=182, width=150, height=46)

        self.windows = {
            "dash": Dashboard(self.content_area, controller=self),
            "set": Setting(self.content_area, controller=self),
        }

        self.navigate("dash")

    def handle_btn_press(self, target, indicator_y):
        self.sidebar_indicator.place(x=0, y=indicator_y, height=46, width=6)
        self.navigate(target)

    def navigate(self, target):
        if self.current_window is not None:
            self.current_window.pack_forget()

        self.current_window = self.windows[target]
        self.current_window.pack(fill="both", expand=True)

    def capture_single_image(self):
        exposure = float(self.runtime_settings.get("exposure_us", 50000.0))
        if self.camera is None:
            self.camera = CameraInterface(device_index=0, exposure=exposure)
        else:
            self.camera.update_exposure(exposure)
        return self.camera.capture_once()

    def _load_runtime_settings(self):
        settings = dict(self.default_settings)
        if not self.settings_path.exists():
            return settings
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception:
            pass
        return settings

    def get_runtime_settings(self):
        return dict(self.runtime_settings)

    def apply_runtime_settings(self, new_settings):
        def _clamp_int(value, low, high):
            return max(low, min(high, int(value)))

        merged = dict(self.runtime_settings)
        merged.update(new_settings)
        for k in ["exposure_us", "bin_thresh", "ppm", "anchor_xmm", "anchor_ymm", "anchor_wmm", "anchor_hmm"]:
            merged[k] = float(merged[k])
        merged["fabric_type"] = str(merged.get("fabric_type", "矩形布料"))
        merged["fabric_color_mode"] = str(merged.get("fabric_color_mode", "黑白布料"))

        hsv_lower = merged.get("hsv_lower", [0, 0, 0])
        hsv_upper = merged.get("hsv_upper", [360, 100, 100])
        try:
            hsv_lower = list(hsv_lower)
            hsv_upper = list(hsv_upper)
        except Exception:
            hsv_lower = [0, 0, 0]
            hsv_upper = [360, 100, 100]

        if len(hsv_lower) != 3:
            hsv_lower = [0, 0, 0]
        if len(hsv_upper) != 3:
            hsv_upper = [360, 100, 100]

        merged["hsv_lower"] = [
            _clamp_int(hsv_lower[0], 0, 360),
            _clamp_int(hsv_lower[1], 0, 100),
            _clamp_int(hsv_lower[2], 0, 100),
        ]
        merged["hsv_upper"] = [
            _clamp_int(hsv_upper[0], 0, 360),
            _clamp_int(hsv_upper[1], 0, 100),
            _clamp_int(hsv_upper[2], 0, 100),
        ]
        self.runtime_settings = merged
        if self.camera is not None:
            self.camera.update_exposure(self.runtime_settings["exposure_us"])

    def save_runtime_settings(self):
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.runtime_settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def reload_runtime_settings(self):
        self.runtime_settings = self._load_runtime_settings()
        if self.camera is not None:
            self.camera.update_exposure(self.runtime_settings["exposure_us"])
        return self.get_runtime_settings()

    def _on_window_close(self):
        if self.camera is not None:
            self.camera.close()
            self.camera = None
        master = self.master
        try:
            self.quit()
        except Exception:
            pass
        self.destroy()
        if master is not None:
            try:
                master.quit()
            except Exception:
                pass
            master.destroy()
