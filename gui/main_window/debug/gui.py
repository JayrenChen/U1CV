from pathlib import Path
from datetime import datetime
import base64

import cv2
import numpy as np
import tkinter as tk
from tkinter import Frame, Canvas, Text
from tkinter import ttk

PARAMS_PATH = Path(__file__).parents[2] / "camera_params_all.npz"
REF_OBJ_PATH = Path(__file__).parents[2] / "ref_obj_mm.npz"
RESULTS_DIR = Path(__file__).parents[3] / "results"


def debug_page(parent, controller=None):
    return DebugPage(parent, controller=controller)


class DebugPage(Frame):
    def __init__(self, parent, controller=None, *args, **kwargs):
        Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.controller = controller
        self.configure(bg="#FFF4EC")

        self.ui_font_family = getattr(self.controller, "ui_font_family", "TkDefaultFont")
        self._panel_tk_images = {}

        self.last_raw_frame = None
        self.last_undistorted = None

        self._build_layout()

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
            "矫正图像",
            "角点检测",
            "俯视图",
            "定位区域",
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
                text="图像显示区",
                fill="#94A3B8",
                font=(self.ui_font_family, 14, "bold"),
            )

            footer = ttk.Label(card, text="等待操作...", style="Value.TLabel")
            footer.grid(row=1, column=0, sticky="w", pady=(8, 2))
            self.image_canvases.append((canvas, footer))

        self.image_panel_map = {
            "矫正图像": self.image_canvases[0],
            "角点检测": self.image_canvases[1],
            "俯视图": self.image_canvases[2],
            "定位区域": self.image_canvases[3],
        }

    def _build_right_panel(self, parent):
        parent.columnconfigure(0, weight=1)

        tips_card = ttk.LabelFrame(parent, text="调试操作", style="Panel.TLabelframe", padding=10)
        tips_card.grid(row=0, column=0, sticky="ew", pady=(6, 8))
        tips_card.columnconfigure(0, weight=1)

        ttk.Label(
            tips_card,
            text="先点击图像获取，再点击校准坐标系",
            style="Value.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        ttk.Button(tips_card, text="图像获取", style="Primary.TButton", command=self._on_capture_image).grid(
            row=1, column=0, sticky="ew", pady=6
        )
        ttk.Button(tips_card, text="校准坐标系", style="Primary.TButton", command=self._on_calibrate_coords).grid(
            row=2, column=0, sticky="ew", pady=6
        )
        ttk.Button(tips_card, text="显示定位区域", style="Primary.TButton", command=self._on_show_reference_region).grid(
            row=3, column=0, sticky="ew", pady=6
        )
        ttk.Button(tips_card, text="清空显示", command=self._on_clear).grid(row=4, column=0, sticky="ew", pady=6)

        log_card = ttk.LabelFrame(parent, text="事件日志", style="Panel.TLabelframe", padding=10)
        log_card.grid(row=3, column=0, sticky="nsew", pady=(8, 6))
        parent.rowconfigure(3, weight=1)

        self.log_text = Text(log_card, height=10, wrap="word", bg="#FFFFFF", fg="#111827", relief="flat")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", "调试页面已初始化。\n")
        self.log_text.configure(state="disabled")

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    @staticmethod
    def _load_params_dict():
        params = {}
        if not PARAMS_PATH.exists():
            return params
        data = np.load(str(PARAMS_PATH), allow_pickle=False)
        for key in data.files:
            params[key] = data[key]
        return params

    @staticmethod
    def _save_image(path, img):
        if img is None:
            return False
        arr = img
        if len(arr.shape) == 3 and arr.shape[2] == 1:
            arr = arr[:, :, 0]
        return bool(cv2.imwrite(str(path), arr))

    def _get_runtime_settings(self):
        if self.controller is None:
            return {}
        try:
            return self.controller.get_runtime_settings()
        except Exception:
            return {}

    @staticmethod
    def _order_box_points(pts):
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
        s = pts.sum(axis=1)
        d = np.diff(pts, axis=1).reshape(-1)
        tl = pts[np.argmin(s)]
        br = pts[np.argmax(s)]
        tr = pts[np.argmin(d)]
        bl = pts[np.argmax(d)]
        return np.array([tl, tr, br, bl], dtype=np.float32)

    def _load_reference_box(self):
        if REF_OBJ_PATH.exists():
            try:
                data = np.load(str(REF_OBJ_PATH), allow_pickle=False)
                if "box_mm" in data.files:
                    pts = np.asarray(data["box_mm"], dtype=np.float32).reshape(-1, 2)
                    if pts.shape[0] >= 4:
                        return self._order_box_points(pts[:4]) * 1.02
            except Exception:
                pass
        return np.array([[0, 0], [40, 0], [40, 40], [0, 40]], dtype=np.float32)

    @staticmethod
    def _draw_ori(img, ori, ppm):
        img_ = img.copy()
        p0 = np.array([ori[0], ori[1]], dtype=np.float32)
        theta = np.deg2rad(ori[2])
        ux = np.array([np.cos(theta), np.sin(theta)], dtype=np.float32)
        uy = np.array([-np.sin(theta), np.cos(theta)], dtype=np.float32)
        axis_len_px = 12.0 * float(ppm)
        p1 = p0 + ux * axis_len_px
        p2 = p0 + uy * axis_len_px

        cv2.arrowedLine(img_, tuple(np.round(p0).astype(int)), tuple(np.round(p1).astype(int)), (255, 0, 0), 3, tipLength=0.15)
        cv2.arrowedLine(img_, tuple(np.round(p0).astype(int)), tuple(np.round(p2).astype(int)), (0, 255, 0), 3, tipLength=0.15)
        cv2.circle(img_, tuple(np.round(p0).astype(int)), 4, (0, 0, 255), -1)
        return img_

    @staticmethod
    def _draw_ref_box(img, box_px):
        img_ = img.copy()
        box_px_i = np.round(np.asarray(box_px, dtype=np.float32).reshape(-1, 2)).astype(np.int32)
        cv2.fillPoly(img_, [box_px_i], (0, 255, 0))
        return cv2.addWeighted(img_, 0.4, img, 0.6, 0)

    @staticmethod
    def _detect_ori(img, ppm, anchor_xmm, anchor_ymm, anchor_wmm, anchor_hmm):
        x = int(anchor_xmm * ppm)
        y = int(anchor_ymm * ppm)
        w = max(int(anchor_wmm * ppm), 5)
        h = max(int(anchor_hmm * ppm), 5)

        x2 = min(x + w, img.shape[1])
        y2 = min(y + h, img.shape[0])
        if x >= x2 or y >= y2:
            return [0.0, 0.0, 0.0], img.copy()

        crop = img[y:y2, x:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop.copy()
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, bw = cv2.threshold(blur, 30, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return [0.0, 0.0, 0.0], crop

        cnt = max(contours, key=cv2.contourArea)
        rect = cv2.minAreaRect(cnt)
        box = DebugPage._order_box_points(cv2.boxPoints(rect))
        tl, tr = box[0], box[1]
        angle_deg = float(np.degrees(np.arctan2(tr[1] - tl[1], tr[0] - tl[0])))
        if angle_deg >= 90.0:
            angle_deg -= 180.0
        if angle_deg < -90.0:
            angle_deg += 180.0

        return [float(tl[0] + x), float(tl[1] + y), angle_deg], crop

    @staticmethod
    def _project_with_h(img, settings, params):
        ppm = float(settings.get("ppm", 5.0))
        x_min_mm = float(settings.get("topview_x_min_mm", -30.0))
        x_max_mm = float(settings.get("topview_x_max_mm", 200.0))
        y_min_mm = float(settings.get("topview_y_min_mm", -60.0))
        y_max_mm = float(settings.get("topview_y_max_mm", 280.0))

        if x_max_mm <= x_min_mm or y_max_mm <= y_min_mm:
            raise RuntimeError("俯视范围参数非法")

        H_img2world = params.get("H_img2world")
        if H_img2world is None:
            return img, ppm

        T = np.array([[1, 0, -x_min_mm], [0, 1, -y_min_mm], [0, 0, 1]], dtype=np.float32)
        S = np.array([[ppm, 0, 0], [0, ppm, 0], [0, 0, 1]], dtype=np.float32)
        M_top = S @ T @ H_img2world
        out_w = int(np.ceil((x_max_mm - x_min_mm) * ppm))
        out_h = int(np.ceil((y_max_mm - y_min_mm) * ppm))
        return cv2.warpPerspective(img, M_top, (out_w, out_h)), ppm

    def _on_capture_image(self):
        if self.controller is None:
            self._append_log("控制器不可用")
            return

        try:
            frame = self.controller.capture_single_image()
            params = self._load_params_dict()
            mtx = params.get("mtx")
            dist = params.get("dist")
            if mtx is None or dist is None:
                raise RuntimeError("缺少相机标定参数 mtx/dist，无法矫正")

            h, w = frame.shape[:2]
            new_mtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
            undistorted = cv2.undistort(frame, mtx, dist, None, new_mtx)

            self.last_raw_frame = frame
            self.last_undistorted = undistorted

            self._update_panel_image("矫正图像", undistorted, "图像获取成功")
            self._append_log("图像获取成功，已完成畸变矫正并显示在第一个图像区域")
        except Exception as exc:
            self._append_log(f"图像获取失败: {exc}")

    def _on_calibrate_coords(self):
        if self.last_undistorted is None:
            self._append_log("请先执行图像获取")
            return

        try:
            settings = self._get_runtime_settings()
            img_undistort = self.last_undistorted.copy()
            img_gray = cv2.cvtColor(img_undistort, cv2.COLOR_BGR2GRAY)
            img_corners = img_undistort.copy()

            pattern_cols = max(int(settings.get("calib_pattern_cols", 11)), 3)
            pattern_rows = max(int(settings.get("calib_pattern_rows", 8)), 3)
            pattern_size = (pattern_cols, pattern_rows)
            square_size_mm = float(settings.get("calib_square_size_mm", 15.0))
            objp2d = square_size_mm * np.mgrid[0 : pattern_size[0], 0 : pattern_size[1]].T.reshape(-1, 2)
            objp2d = objp2d.astype(np.float32)

            criteria = (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                30,
                0.001,
            )
            ret, corners = cv2.findChessboardCorners(img_gray, pattern_size, None)
            if not ret:
                raise RuntimeError("棋盘角点检测失败，请更换图像或调整光照")

            corners2 = cv2.cornerSubPix(img_gray, corners, (11, 11), (-1, -1), criteria)
            corners2 = np.asarray(corners2, dtype=np.float32).reshape(-1, 2)
            cv2.drawChessboardCorners(img_corners, pattern_size, corners2.reshape(-1, 1, 2), ret)

            H_world2img, _ = cv2.findHomography(objp2d, corners2, cv2.RANSAC, 2.0)
            if H_world2img is None:
                raise RuntimeError("单应矩阵计算失败")
            H_img2world = np.linalg.inv(H_world2img)

            ppm = float(settings.get("ppm", 5.0))
            x_min_mm = float(settings.get("topview_x_min_mm", -30.0))
            x_max_mm = float(settings.get("topview_x_max_mm", 200.0))
            y_min_mm = float(settings.get("topview_y_min_mm", -60.0))
            y_max_mm = float(settings.get("topview_y_max_mm", 280.0))
            if x_max_mm <= x_min_mm:
                raise RuntimeError("俯视X范围非法：x_max_mm 必须大于 x_min_mm")
            if y_max_mm <= y_min_mm:
                raise RuntimeError("俯视Y范围非法：y_max_mm 必须大于 y_min_mm")

            T = np.array([[1, 0, -x_min_mm], [0, 1, -y_min_mm], [0, 0, 1]], dtype=np.float32)
            S = np.array([[ppm, 0, 0], [0, ppm, 0], [0, 0, 1]], dtype=np.float32)
            M_top = S @ T @ H_img2world
            out_w = int(np.ceil((x_max_mm - x_min_mm) * ppm))
            out_h = int(np.ceil((y_max_mm - y_min_mm) * ppm))
            img_top = cv2.warpPerspective(img_undistort, M_top, (out_w, out_h))

            params = self._load_params_dict()
            params["H_world2img"] = H_world2img.astype(np.float32)
            params["H_img2world"] = H_img2world.astype(np.float32)
            params["square_size_mm"] = np.array(square_size_mm, dtype=np.float32)
            np.savez(str(PARAMS_PATH), **params)

            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            calib_dir = RESULTS_DIR / f"calib_{now}"
            calib_dir.mkdir(parents=True, exist_ok=True)
            self._save_image(calib_dir / "undistorted.png", img_undistort)
            self._save_image(calib_dir / "corners.png", img_corners)
            self._save_image(calib_dir / "top_view.png", img_top)
            np.savez(
                str(calib_dir / "calibration_params.npz"),
                H_world2img=H_world2img.astype(np.float32),
                H_img2world=H_img2world.astype(np.float32),
                pattern_size=np.array(pattern_size, dtype=np.int32),
                square_size_mm=np.array(square_size_mm, dtype=np.float32),
                ppm=np.array(ppm, dtype=np.float32),
                x_min_mm=np.array(x_min_mm, dtype=np.float32),
                x_max_mm=np.array(x_max_mm, dtype=np.float32),
                y_min_mm=np.array(y_min_mm, dtype=np.float32),
                y_max_mm=np.array(y_max_mm, dtype=np.float32),
            )

            self._update_panel_image("角点检测", img_corners, "角点检测完成")
            self._update_panel_image("俯视图", img_top, "透视变换完成")
            self._append_log("坐标系校准成功，透视参数已保存并可供主页图像处理复用")
            self._append_log(f"标定追溯文件已保存: {calib_dir.name}")

            if self.controller is not None:
                self.controller.refresh_processing_parameters()
                self._append_log("主页处理引擎参数已刷新")
        except Exception as exc:
            self._append_log(f"坐标系校准失败: {exc}")

    def _on_show_reference_region(self):
        if self.controller is None:
            self._append_log("控制器不可用")
            return

        try:
            frame = self.controller.capture_single_image()
            params = self._load_params_dict()
            mtx = params.get("mtx")
            dist = params.get("dist")
            if mtx is None or dist is None:
                raise RuntimeError("缺少相机标定参数 mtx/dist，无法矫正")

            h, w = frame.shape[:2]
            new_mtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
            undistorted = cv2.undistort(frame, mtx, dist, None, new_mtx)

            settings = self._get_runtime_settings()
            im_proj, ppm = self._project_with_h(undistorted, settings, params)

            anchor_xmm = float(settings.get("anchor_xmm", 10.0))
            anchor_ymm = float(settings.get("anchor_ymm", 10.0))
            anchor_wmm = float(settings.get("anchor_wmm", 30.0))
            anchor_hmm = float(settings.get("anchor_hmm", 30.0))

            ori, im_ori_crop = self._detect_ori(im_proj, ppm, anchor_xmm, anchor_ymm, anchor_wmm, anchor_hmm)
            # box_ref = self._load_reference_box()
            # box_ref_px = box_ref * ppm + np.array([ori[0], ori[1]], dtype=np.float32)
            ori_ = self._draw_ori(im_proj, ori, ppm)

            self._update_panel_image("俯视图", im_proj, "定位区域图")
            self._update_panel_image("定位区域", im_ori_crop, "定位区域图")
            self._append_log("定位区域图已生成并显示在第4图像窗口")
        except Exception as exc:
            self._append_log(f"定位区域显示失败: {exc}")

    def _on_clear(self):
        self.last_raw_frame = None
        self.last_undistorted = None
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
            footer.configure(text="等待操作...")
        self._append_log("调试显示已清空")

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
