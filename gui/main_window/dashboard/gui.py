from pathlib import Path
import json
import tkinter as tk
from tkinter import Frame, Canvas, StringVar, Text
from tkinter import ttk
from datetime import datetime
import base64

import cv2
from gui.image_processing import ProcessingEngine

OUTPUT_PATH = Path(__file__).parent
ASSETS_PATH = OUTPUT_PATH / Path("./assets")
RESULTS_DIR = OUTPUT_PATH.parents[2] / "results"


def relative_to_assets(path: str) -> Path:
    return ASSETS_PATH / Path(path)


def dashboard(parent, controller=None):
    return Dashboard(parent, controller=controller)


class Dashboard(Frame):
    def __init__(self, parent, controller=None, automation_mode=False, *args, **kwargs):
        Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.controller = controller
        self.automation_mode = automation_mode
        self.configure(bg="#FFF4EC")
        self.logo_page = None
        init_settings = self.controller.get_runtime_settings() if self.controller else None
        self.processor = ProcessingEngine(settings=init_settings)
        self.last_frame = None
        self.last_result = None
        self.last_output = None
        self._panel_tk_images = {}
        self.ui_font_family = getattr(self.controller, "ui_font_family", "TkDefaultFont")

        self._build_layout()

    def _build_layout(self):
        container = ttk.Frame(self, style="Main.TFrame")
        container.pack(fill="both", expand=True)

        title_bar = ttk.Frame(container, style="Main.TFrame")
        title_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        # logo_path = relative_to_assets("logo_dashboard.png")
        # if logo_path.exists():
        #     try:
        #         self.logo_page = tk.PhotoImage(file=str(logo_path)).subsample(8, 8)
        #         ttk.Label(title_bar, image=self.logo_page, style="Main.TLabel").pack(side="left", padx=(0, 8))
        #     except Exception:
        #         self.logo_page = None

        # ttk.Label(title_bar, text="主页面板", style="Title.TLabel").pack(side="left")

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
        self._camera_raw_tkimg = None

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
                text="图像显示区",
                fill="#94A3B8",
                font=(self.ui_font_family, 14, "bold"),
            )

            footer = ttk.Label(card, text="等待图像输入...", style="Value.TLabel")
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

        info_card = ttk.LabelFrame(parent, text="检测信息", style="Panel.TLabelframe", padding=10)
        info_card.grid(row=0, column=0, sticky="ew", pady=(6, 8))
        info_card.columnconfigure(1, weight=1)

        self.info_vars = {
            "批次号": StringVar(value="BATCH-0001"),
            "卷号": StringVar(value="ROLL-000"),
            "操作员": StringVar(value="操作员-A"),
        }

        row_idx = 0
        for key, var in self.info_vars.items():
            ttk.Label(info_card, text=key + ":", style="Key.TLabel").grid(row=row_idx, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(info_card, textvariable=var).grid(row=row_idx, column=1, sticky="ew", pady=4)
            row_idx += 1

        result_card = ttk.LabelFrame(parent, text="检测结果", style="Panel.TLabelframe", padding=10)
        result_card.grid(row=1, column=0, sticky="ew", pady=8)
        result_card.columnconfigure(1, weight=1)
        result_card.columnconfigure(3, weight=1)

        self.status_var = StringVar(value="空闲")
        self.offset_x_var = StringVar(value="--")
        self.offset_y_var = StringVar(value="--")
        self.theta_var = StringVar(value="--")
        self.rmse_var = StringVar(value="--")
        self.width_var = StringVar(value="--")
        self.length_var = StringVar(value="--")
        self.area_var = StringVar(value="--")

        ttk.Label(result_card, text="状态:", style="Key.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.status_var, style="Value.TLabel").grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(result_card, text="偏移 X (mm):", style="Key.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.offset_x_var, style="Value.TLabel").grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(result_card, text="偏移 Y (mm):", style="Key.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.offset_y_var, style="Value.TLabel").grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(result_card, text="偏移角度 (deg):", style="Key.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.theta_var, style="Value.TLabel").grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(result_card, text="拟合误差 RMSE:", style="Key.TLabel").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Label(result_card, textvariable=self.rmse_var, style="Value.TLabel").grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(result_card, text="布料宽度 (mm):", style="Key.TLabel").grid(row=1, column=2, sticky="w", padx=(18, 0), pady=4)
        ttk.Label(result_card, textvariable=self.width_var, style="Value.TLabel").grid(row=1, column=3, sticky="w", pady=4)
    
        ttk.Label(result_card, text="布料长度 (mm):", style="Key.TLabel").grid(row=2, column=2, sticky="w", padx=(18, 0), pady=4)
        ttk.Label(result_card, textvariable=self.length_var, style="Value.TLabel").grid(row=2, column=3, sticky="w", pady=4)

        ttk.Label(result_card, text="布料面积 (mm²):", style="Key.TLabel").grid(row=3, column=2, sticky="w", padx=(18, 0), pady=4)
        ttk.Label(result_card, textvariable=self.area_var, style="Value.TLabel").grid(row=3, column=3, sticky="w", pady=4)

        control_card = ttk.LabelFrame(parent, text="操作面板", style="Panel.TLabelframe", padding=10)
        control_card.grid(row=2, column=0, sticky="ew", pady=8)
        control_card.columnconfigure(0, weight=1)
        control_card.columnconfigure(1, weight=1)

        if self.automation_mode:
            ttk.Label(control_card, text="当前页面由 PLC Modbus 指令触发检测", style="Value.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=6)
            ttk.Button(control_card, text="单次采集", state="disabled").grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=6)
            ttk.Button(control_card, text="处理图像", state="disabled").grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=6)
        else:
            ttk.Button(control_card, text="单次采集", style="Primary.TButton", command=self._on_capture).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=6)
            ttk.Button(control_card, text="处理图像", style="Primary.TButton", command=self._on_process).grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=6)
            ttk.Button(control_card, text="清空显示", command=self._on_clear).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=6)
            ttk.Button(control_card, text="保存结果", command=self._on_save_result).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=6)

        log_card = ttk.LabelFrame(parent, text="事件日志", style="Panel.TLabelframe", padding=10)
        log_card.grid(row=3, column=0, sticky="nsew", pady=(8, 6))
        parent.rowconfigure(3, weight=1)

        self.log_text = Text(log_card, height=10, wrap="word", bg="#FFFFFF", fg="#111827", relief="flat")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", "系统已初始化。\n")
        self.log_text.configure(state="disabled")

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _reset_result_fields(self):
        self.status_var.set("空闲")
        self.offset_x_var.set("--")
        self.offset_y_var.set("--")
        self.theta_var.set("--")
        self.rmse_var.set("--")
        self.width_var.set("--")
        self.length_var.set("--")
        self.area_var.set("--")
        self.last_result = None
        self.last_output = None

    def _clear_panels(self):
        for canvas, footer in self.image_panel_map.values():
            canvas.delete("all")
            canvas.create_rectangle(20, 20, 180, 100, outline="#334155", width=2)
            canvas.create_text(
                100,
                60,
                text="图像显示区",
                fill="#94A3B8",
                font=(self.ui_font_family, 14, "bold"),
            )
            footer.configure(text="等待图像输入...")

    def _increment_roll_id(self):
        roll = self.info_vars["卷号"].get().strip()
        if "-" not in roll:
            self.info_vars["卷号"].set("ROLL-000")
            return
        prefix, suffix = roll.rsplit("-", 1)
        try:
            n = int(suffix)
            self.info_vars["卷号"].set(f"{prefix}-{n + 1:03d}")
        except Exception:
            self.info_vars["卷号"].set(f"{prefix}-001")

    def _on_capture(self):
        if self.controller is None:
            self._append_log("控制器不可用")
            return

        try:
            self._clear_panels()
            self._reset_result_fields()
            self.last_frame = None
            self._increment_roll_id()

            frame = self.controller.capture_single_image()
            self.last_frame = frame.copy()
            self.update_camera_raw(cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE))
            self.status_var.set("采集成功")
            self._append_log("单次采集完成")
        except Exception as exc:
            self.status_var.set("采集失败")
            self._append_log(f"采集失败: {exc}")

    def _on_process(self):
        if self.last_frame is None:
            self._append_log("尚无可处理图像，先执行单次采集")
            self.status_var.set("等待采集")
            return

        auto_save_on_process = False
        try:
            if self.controller is not None:
                runtime_settings = self.controller.get_runtime_settings()
                self.processor.apply_settings(runtime_settings)
                auto_save_on_process = bool(runtime_settings.get("auto_save_on_process", False))

            output = self.processor.process(self.last_frame)
            self.last_output = output
            # self._update_panel_image("相机原图", output["ref"], "已校正")
            self._update_panel_image("检测结果", output["final"], "BOX检测结果")
            self._update_panel_image("图像校准", output["projected"], "预处理结果")
            self._update_panel_image("二值图像", output["preprocess"], "阈值分割图")

            if output["found"]:
                result = output["result"]
                self.status_var.set("处理完成")
                self.offset_x_var.set(f"{result['offset_x_mm']:.3f}")
                self.offset_y_var.set(f"{result['offset_y_mm']:.3f}")
                self.theta_var.set(f"{result['theta_deg']:.3f}")
                self.rmse_var.set(f"{result['rmse']:.3f}")
                self.width_var.set(f"{result['width_mm']:.3f}")
                self.length_var.set(f"{result['length_mm']:.3f}")
                self.area_var.set(f"{result['area_mm2']:.3f}")
                self.last_result = result
                self._append_log(
                    f"BOX识别成功: dx={result['offset_x_mm']:.3f}, dy={result['offset_y_mm']:.3f}, theta={result['theta_deg']:.3f}, rmse={result['rmse']:.3f}"
                )
            else:
                self.status_var.set("未检测到BOX")
                self.offset_x_var.set("--")
                self.offset_y_var.set("--")
                self.theta_var.set("--")
                self.rmse_var.set("--")
                self.width_var.set("--")
                self.length_var.set("--")
                self.area_var.set("--")
                self.last_result = None
                self._append_log("处理完成，但未检测到BOX")
        except Exception as exc:
            self.status_var.set("处理失败")
            self.last_output = None
            self.last_result = None
            self._append_log(f"图像处理失败: {exc}")

        if auto_save_on_process:
            self._on_save_result()

    def run_plc_detection(self):
        """Run the same capture/process pipeline as the homepage from the GUI thread."""
        self._append_log("收到 PLC 移料前视觉检测触发")
        self._on_capture()
        self._on_process()
        return self.last_result

    @staticmethod
    def _save_image(path, img):
        if img is None:
            return False
        arr = img
        if len(arr.shape) == 3 and arr.shape[2] == 1:
            arr = arr[:, :, 0]
        return bool(cv2.imwrite(str(path), arr))

    def _on_save_result(self):
        image_map = {}
        if self.last_output is not None:
            image_map.update(
                {
                    "raw.png": self.last_output.get("raw"),
                    "undistorted.png": self.last_output.get("undistorted"),
                    "projected.png": self.last_output.get("projected"),
                    "ori.png": self.last_output.get("ori"),
                    "ref.png": self.last_output.get("ref"),
                    "preprocess.png": self.last_output.get("preprocess"),
                    "final.png": self.last_output.get("final"),
                }
            )
        elif self.last_frame is not None:
            image_map["raw.png"] = self.last_frame

        has_meaningful_result = self.last_result is not None
        has_meaningful_image = any(img is not None for img in image_map.values())
        if not has_meaningful_result and not has_meaningful_image:
            self._append_log("没有可保存的有效内容（无图像、无结果）")
            return

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_dir = RESULTS_DIR / f"img_{now}"
        img_dir.mkdir(parents=True, exist_ok=True)

        saved_count = 0
        for filename, img in image_map.items():
            if self._save_image(img_dir / filename, img):
                saved_count += 1

        process_status = self.status_var.get().strip()
        payload = {
            "time": now,
            "batch_id": self.info_vars["批次号"].get(),
            "roll_id": self.info_vars["卷号"].get(),
            "operator": self.info_vars["操作员"].get(),
            "status": process_status,
            "image_dir": img_dir.name,
            "result": self.last_result,
        }
        out_file = RESULTS_DIR / f"result_{now}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self._append_log(f"结果已保存: {out_file.name}，过程图像 {saved_count}/7 张，目录 {img_dir.name}")

    def _on_clear(self):
        self._reset_result_fields()
        self.last_frame = None
        self._clear_panels()
        self._append_log("主界面已清空")

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

    def update_camera_raw(self, frame):
        self._update_panel_image("相机原图", frame, "已采集")
