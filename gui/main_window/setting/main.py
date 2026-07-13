from pathlib import Path
import tkinter as tk
from tkinter import Frame, StringVar
from tkinter import ttk, messagebox

OUTPUT_PATH = Path(__file__).parent
ASSETS_PATH = OUTPUT_PATH / Path("./assets")


def relative_to_assets(path: str) -> Path:
    return ASSETS_PATH / Path(path)


def setting(parent, controller=None):
    return Setting(parent, controller=controller)


class Setting(Frame):
    def __init__(self, parent, controller=None, *args, **kwargs):
        Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.controller = controller
        self.configure(bg="#FFFFFF")
        self.logo_page = None

        self._build_layout()

    def _build_layout(self):
        container = ttk.Frame(self, style="Main.TFrame")
        container.pack(fill="both", expand=True, padx=6, pady=6)

        title_bar = ttk.Frame(container, style="Main.TFrame")
        title_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        # logo_path = relative_to_assets("logo_setting.png")
        # if logo_path.exists():
        #     try:
        #         self.logo_page = tk.PhotoImage(file=str(logo_path)).subsample(8, 8)
        #         logo_label = tk.Label(title_bar, image=self.logo_page, bg="#FFF4EC", bd=0)
        #         logo_label.pack(side="left", padx=(0, 8))
        #     except Exception:
        #         self.logo_page = None

        # ttk.Label(title_bar, text="参数设置", style="Title.TLabel").pack(side="left")

        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)

        cam_card = ttk.LabelFrame(container, text="相机参数", style="Panel.TLabelframe", padding=12)
        cam_card.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))

        alg_card = ttk.LabelFrame(container, text="算法参数", style="Panel.TLabelframe", padding=12)
        alg_card.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))

        save_card = ttk.LabelFrame(container, text="系统设置", style="Panel.TLabelframe", padding=12)
        save_card.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.setting_vars = {
            "曝光时间(us)": StringVar(value="50000"),
            "二值阈值": StringVar(value="60"),
            "PPM": StringVar(value="5.0"),
            "定位X(mm)": StringVar(value="10"),
            "定位Y(mm)": StringVar(value="10"),
            "定位W(mm)": StringVar(value="30"),
            "定位H(mm)": StringVar(value="30"),
            "布料类型": StringVar(value="矩形布料"),
        }

        cam_fields = ["曝光时间(us)"]
        alg_fields = ["二值阈值", "PPM", "定位X(mm)", "定位Y(mm)", "定位W(mm)", "定位H(mm)"]

        for i, key in enumerate(cam_fields):
            ttk.Label(cam_card, text=key + ":", style="Key.TLabel").grid(row=i, column=0, sticky="w", pady=5, padx=(0, 8))
            ttk.Entry(cam_card, textvariable=self.setting_vars[key]).grid(row=i, column=1, sticky="ew", pady=5)
        cam_card.columnconfigure(1, weight=1)

        for i, key in enumerate(alg_fields):
            ttk.Label(alg_card, text=key + ":", style="Key.TLabel").grid(row=i, column=0, sticky="w", pady=5, padx=(0, 8))
            ttk.Entry(alg_card, textvariable=self.setting_vars[key]).grid(row=i, column=1, sticky="ew", pady=5)

        row_idx = len(alg_fields)
        ttk.Label(alg_card, text="布料类型:", style="Key.TLabel").grid(row=row_idx, column=0, sticky="w", pady=5, padx=(0, 8))
        fabric_combo = ttk.Combobox(
            alg_card,
            textvariable=self.setting_vars["布料类型"],
            values=["矩形布料", "弧形布料(预留)"],
            state="readonly",
        )
        fabric_combo.grid(row=row_idx, column=1, sticky="ew", pady=5)
        alg_card.columnconfigure(1, weight=1)

        ttk.Button(save_card, text="应用参数", command=self._on_apply).pack(side="left", padx=(0, 8))
        ttk.Button(save_card, text="加载配置", command=self._on_load_config).pack(side="left", padx=(0, 8))
        ttk.Button(save_card, text="保存配置", style="Primary.TButton", command=self._on_save_config).pack(side="left", padx=(0, 8))
        ttk.Button(save_card, text="恢复默认", command=self._on_reset).pack(side="left")

        self._load_from_controller()

    def _collect_settings(self):
        return {
            "exposure_us": float(self.setting_vars["曝光时间(us)"].get()),
            "bin_thresh": float(self.setting_vars["二值阈值"].get()),
            "ppm": float(self.setting_vars["PPM"].get()),
            "anchor_xmm": float(self.setting_vars["定位X(mm)"].get()),
            "anchor_ymm": float(self.setting_vars["定位Y(mm)"].get()),
            "anchor_wmm": float(self.setting_vars["定位W(mm)"].get()),
            "anchor_hmm": float(self.setting_vars["定位H(mm)"].get()),
            "fabric_type": self.setting_vars["布料类型"].get(),
        }

    def _fill_vars(self, settings):
        self.setting_vars["曝光时间(us)"].set(str(settings.get("exposure_us", 50000)))
        self.setting_vars["二值阈值"].set(str(settings.get("bin_thresh", 60)))
        self.setting_vars["PPM"].set(str(settings.get("ppm", 5.0)))
        self.setting_vars["定位X(mm)"].set(str(settings.get("anchor_xmm", 10)))
        self.setting_vars["定位Y(mm)"].set(str(settings.get("anchor_ymm", 10)))
        self.setting_vars["定位W(mm)"].set(str(settings.get("anchor_wmm", 30)))
        self.setting_vars["定位H(mm)"].set(str(settings.get("anchor_hmm", 30)))
        self.setting_vars["布料类型"].set(str(settings.get("fabric_type", "矩形布料")))

    def _load_from_controller(self):
        if self.controller is None:
            return
        self._fill_vars(self.controller.get_runtime_settings())

    def _on_apply(self):
        if self.controller is None:
            return
        try:
            self.controller.apply_runtime_settings(self._collect_settings())
            messagebox.showinfo("参数设置", "参数已应用")
        except Exception as exc:
            messagebox.showerror("参数设置", f"参数应用失败: {exc}")

    def _on_load_config(self):
        if self.controller is None:
            return
        settings = self.controller.reload_runtime_settings()
        self._fill_vars(settings)
        messagebox.showinfo("参数设置", "配置已加载")

    def _on_save_config(self):
        if self.controller is None:
            return
        try:
            self.controller.apply_runtime_settings(self._collect_settings())
            self.controller.save_runtime_settings()
            messagebox.showinfo("参数设置", "配置已保存")
        except Exception as exc:
            messagebox.showerror("参数设置", f"配置保存失败: {exc}")

    def _on_reset(self):
        defaults = {
            "exposure_us": 50000,
            "bin_thresh": 60,
            "ppm": 5.0,
            "anchor_xmm": 10,
            "anchor_ymm": 10,
            "anchor_wmm": 30,
            "anchor_hmm": 30,
            "fabric_type": "矩形布料",
        }
        self._fill_vars(defaults)
        if self.controller is not None:
            self.controller.apply_runtime_settings(defaults)
        messagebox.showinfo("参数设置", "已恢复默认参数")
