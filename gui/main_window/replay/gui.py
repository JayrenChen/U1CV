from pathlib import Path
import json
import tkinter as tk
from tkinter import Frame, Canvas, StringVar, Text
from tkinter import ttk
from datetime import datetime
import base64

import cv2

OUTPUT_PATH = Path(__file__).parent
RESULTS_DIR = OUTPUT_PATH.parents[2] / "results"


def replay(parent, controller=None):
    return Replay(parent, controller=controller)


class Replay(Frame):
    def __init__(self, parent, controller=None, *args, **kwargs):
        Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.controller = controller
        self.configure(bg="#FFF4EC")

        self.ui_font_family = getattr(self.controller, "ui_font_family", "TkDefaultFont")
        self._panel_tk_images = {}
        self.result_items = []
        self.current_index = -1

        self.result_select_var = StringVar(value="")
        self.status_var = StringVar(value="--")
        self.time_var = StringVar(value="--")
        self.batch_var = StringVar(value="--")
        self.roll_var = StringVar(value="--")
        self.operator_var = StringVar(value="--")
        self.offset_x_var = StringVar(value="--")
        self.offset_y_var = StringVar(value="--")
        self.theta_var = StringVar(value="--")
        self.rmse_var = StringVar(value="--")
        self.width_var = StringVar(value="--")
        self.length_var = StringVar(value="--")
        self.area_var = StringVar(value="--")

        self._build_layout()
        self.refresh_results(select_latest=True)

    def _build_layout(self):
        container = ttk.Frame(self, style="Main.TFrame")
        container.pack(fill="both", expand=True)

        container.columnconfigure(0, weight=2)
        container.columnconfigure(1, weight=5)
        container.rowconfigure(1, weight=1)

        left = ttk.Frame(container, style="Main.TFrame")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))

        right = ttk.Frame(container, style="Main.TFrame")
        right.grid(row=1, column=1, sticky="nsew")
        container.grid_columnconfigure(1, minsize=100)

        self._build_image_grid(left)
        self._build_right_panel(right)

    def _build_image_grid(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        panel_titles = [
            "相机原图",
            "检测结果",
            "图像校准",
            "二值图像",
        ]

        self.image_canvases = []
        for idx, title in enumerate(panel_titles):
            r = idx // 2
            c = idx % 2

            card = ttk.LabelFrame(parent, text=title, style="Panel.TLabelframe", padding=8)
            card.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            card.columnconfigure(0, weight=1)
            card.rowconfigure(0, weight=1)

            canvas = Canvas(card, bg="#101827", highlightthickness=0)
            canvas.grid(row=0, column=0, sticky="nsew")
            canvas.create_rectangle(20, 20, 180, 100, outline="#334155", width=2)
            canvas.create_text(
                100,
                60,
                text="等待回放",
                fill="#94A3B8",
                font=(self.ui_font_family, 14, "bold"),
            )

            footer = ttk.Label(card, text="等待选择结果...", style="Value.TLabel")
            footer.grid(row=1, column=0, sticky="w", pady=(8, 2))
            self.image_canvases.append((canvas, footer))

        self.image_panel_map = {
            "相机原图": self.image_canvases[0],
            "检测结果": self.image_canvases[1],
            "图像校准": self.image_canvases[2],
            "二值图像": self.image_canvases[3],
        }

    def _build_right_panel(self, parent):
        parent.columnconfigure(0, weight=1)

        pick_card = ttk.LabelFrame(parent, text="结果回放", style="Panel.TLabelframe", padding=10)
        pick_card.grid(row=0, column=0, sticky="ew", pady=(6, 8))
        pick_card.columnconfigure(0, weight=1)
        pick_card.columnconfigure(1, weight=0)
        pick_card.columnconfigure(2, weight=0)
        pick_card.columnconfigure(3, weight=0)

        self.result_combo = ttk.Combobox(pick_card, textvariable=self.result_select_var, state="readonly")
        self.result_combo.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(4, 8))
        self.result_combo.bind("<<ComboboxSelected>>", self._on_select_result)

        ttk.Button(pick_card, text="刷新", command=lambda: self.refresh_results(select_latest=False)).grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        ttk.Button(pick_card, text="上一条", command=self._on_prev).grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(pick_card, text="下一条", command=self._on_next).grid(row=1, column=2, sticky="ew", padx=4, pady=4)

        meta_card = ttk.LabelFrame(parent, text="回放信息", style="Panel.TLabelframe", padding=10)
        meta_card.grid(row=1, column=0, sticky="ew", pady=8)
        meta_card.columnconfigure(1, weight=1)
        ttk.Label(meta_card, text="状态:", style="Key.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(meta_card, textvariable=self.status_var, style="Value.TLabel").grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(meta_card, text="时间:", style="Key.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(meta_card, textvariable=self.time_var, style="Value.TLabel").grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(meta_card, text="批次号:", style="Key.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(meta_card, textvariable=self.batch_var, style="Value.TLabel").grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(meta_card, text="卷号:", style="Key.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(meta_card, textvariable=self.roll_var, style="Value.TLabel").grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(meta_card, text="操作员:", style="Key.TLabel").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Label(meta_card, textvariable=self.operator_var, style="Value.TLabel").grid(row=4, column=1, sticky="w", pady=4)

        result_card = ttk.LabelFrame(parent, text="检测结果", style="Panel.TLabelframe", padding=10)
        result_card.grid(row=2, column=0, sticky="ew", pady=8)
        result_card.columnconfigure(1, weight=1)
        result_card.columnconfigure(3, weight=1)

        ttk.Label(result_card, text="偏移 X (mm):", style="Key.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.offset_x_var, style="Value.TLabel").grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(result_card, text="偏移 Y (mm):", style="Key.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.offset_y_var, style="Value.TLabel").grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(result_card, text="偏移角度 (deg):", style="Key.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.theta_var, style="Value.TLabel").grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(result_card, text="拟合误差 RMSE:", style="Key.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.rmse_var, style="Value.TLabel").grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(result_card, text="布料宽度 (mm):", style="Key.TLabel").grid(row=0, column=2, sticky="w", padx=(18, 0), pady=4)
        ttk.Label(result_card, textvariable=self.width_var, style="Value.TLabel").grid(row=0, column=3, sticky="w", pady=4)
        ttk.Label(result_card, text="布料长度 (mm):", style="Key.TLabel").grid(row=1, column=2, sticky="w", padx=(18, 0), pady=4)
        ttk.Label(result_card, textvariable=self.length_var, style="Value.TLabel").grid(row=1, column=3, sticky="w", pady=4)
        ttk.Label(result_card, text="布料面积 (mm²):", style="Key.TLabel").grid(row=2, column=2, sticky="w", padx=(18, 0), pady=4)
        ttk.Label(result_card, textvariable=self.area_var, style="Value.TLabel").grid(row=2, column=3, sticky="w", pady=4)

        log_card = ttk.LabelFrame(parent, text="回放日志", style="Panel.TLabelframe", padding=10)
        log_card.grid(row=3, column=0, sticky="nsew", pady=(8, 6))
        parent.rowconfigure(3, weight=1)

        self.log_text = Text(log_card, height=10, wrap="word", bg="#FFFFFF", fg="#111827", relief="flat")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", "回放页面已初始化。\n")
        self.log_text.configure(state="disabled")

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_result_value(self, var_obj, value):
        if value is None:
            var_obj.set("--")
            return
        try:
            var_obj.set(f"{float(value):.3f}")
        except Exception:
            var_obj.set(str(value))

    def _clear_panels(self):
        for panel_name, (canvas, footer) in self.image_panel_map.items():
            canvas.delete("all")
            canvas.create_rectangle(20, 20, 180, 100, outline="#334155", width=2)
            canvas.create_text(
                100,
                60,
                text="图像缺失",
                fill="#94A3B8",
                font=(self.ui_font_family, 14, "bold"),
            )
            footer.configure(text=f"{panel_name}: 未找到")

    def _update_panel_image(self, panel_name, img, footer_text):
        canvas, footer = self.image_panel_map[panel_name]
        canvas.update_idletasks()

        canvas_w = max(canvas.winfo_width(), 1)
        canvas_h = max(canvas.winfo_height(), 1)
        target_w = max(canvas_w, 320)
        target_h = max(canvas_h, 240)

        if img is None:
            raise RuntimeError("待显示图像为空")

        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        src_h, src_w = img.shape[:2]
        scale = min(target_w / max(src_w, 1), target_h / max(src_h, 1))
        new_w = max(int(src_w * scale), 1)
        new_h = max(int(src_h * scale), 1)
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        ok, encoded = cv2.imencode(".png", resized)
        if not ok:
            raise RuntimeError("图像编码失败，无法显示")

        b64_data = base64.b64encode(encoded.tobytes())
        self._panel_tk_images[panel_name] = tk.PhotoImage(data=b64_data)

        canvas.delete("all")
        canvas.create_image(canvas_w // 2, canvas_h // 2, image=self._panel_tk_images[panel_name])
        footer.configure(text=f"{footer_text}: {src_w}x{src_h}")

    def refresh_results(self, select_latest=True):
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        result_files = sorted(RESULTS_DIR.glob("result_*.json"), reverse=True)

        self.result_items = []
        for p in result_files:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            ts = str(data.get("time", p.stem.replace("result_", "")))
            roll = str(data.get("roll_id", "--"))
            status = str(data.get("status", "未知状态"))
            label = f"{ts} | {roll} | {status}"
            self.result_items.append({"label": label, "path": p, "data": data})

        values = [item["label"] for item in self.result_items]
        self.result_combo["values"] = values

        if not values:
            self.result_select_var.set("")
            self.current_index = -1
            self._clear_panels()
            self._append_log("未找到可回放结果")
            return

        if select_latest or self.current_index < 0 or self.current_index >= len(values):
            self.current_index = 0

        self.result_select_var.set(values[self.current_index])
        self._load_current_item()

    def _on_select_result(self, _event=None):
        label = self.result_select_var.get()
        for i, item in enumerate(self.result_items):
            if item["label"] == label:
                self.current_index = i
                break
        self._load_current_item()

    def _on_prev(self):
        if not self.result_items:
            return
        self.current_index = (self.current_index - 1) % len(self.result_items)
        self.result_select_var.set(self.result_items[self.current_index]["label"])
        self._load_current_item()

    def _on_next(self):
        if not self.result_items:
            return
        self.current_index = (self.current_index + 1) % len(self.result_items)
        self.result_select_var.set(self.result_items[self.current_index]["label"])
        self._load_current_item()

    def _load_current_item(self):
        if self.current_index < 0 or self.current_index >= len(self.result_items):
            return

        item = self.result_items[self.current_index]
        data = item["data"]

        self.status_var.set(str(data.get("status", "--")))
        self.time_var.set(str(data.get("time", "--")))
        self.batch_var.set(str(data.get("batch_id", "--")))
        self.roll_var.set(str(data.get("roll_id", "--")))
        self.operator_var.set(str(data.get("operator", "--")))

        result = data.get("result") if isinstance(data.get("result"), dict) else None
        if result is None:
            self.offset_x_var.set("--")
            self.offset_y_var.set("--")
            self.theta_var.set("--")
            self.rmse_var.set("--")
            self.width_var.set("--")
            self.length_var.set("--")
            self.area_var.set("--")
        else:
            self._set_result_value(self.offset_x_var, result.get("offset_x_mm"))
            self._set_result_value(self.offset_y_var, result.get("offset_y_mm"))
            self._set_result_value(self.theta_var, result.get("theta_deg"))
            self._set_result_value(self.rmse_var, result.get("rmse"))
            self._set_result_value(self.width_var, result.get("width_mm"))
            self._set_result_value(self.length_var, result.get("length_mm"))
            self._set_result_value(self.area_var, result.get("area_mm2"))

        image_dir = data.get("image_dir")
        if not image_dir:
            ts = str(data.get("time", ""))
            image_dir = f"img_{ts}" if ts else ""

        image_root = RESULTS_DIR / image_dir if image_dir else RESULTS_DIR
        image_paths = {
            "相机原图": image_root / "raw.png",
            "检测结果": image_root / "final.png",
            "图像校准": image_root / "projected.png",
            "二值图像": image_root / "preprocess.png",
        }

        self._clear_panels()
        shown = 0
        for panel_name, p in image_paths.items():
            if not p.exists():
                continue
            img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
            if img is None:
                continue
            try:
                self._update_panel_image(panel_name, img, p.name)
                shown += 1
            except Exception:
                continue

        self._append_log(f"加载结果: {item['path'].name}，图像显示 {shown}/4")
