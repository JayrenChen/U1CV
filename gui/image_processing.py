from pathlib import Path
from typing import Optional

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
PARAMS_PATH = BASE_DIR / "camera_params_all.npz"
REF_OBJ_PATH = BASE_DIR / "ref_obj_mm.npz"


class ProcessingEngine:
    """Image processing pipeline adapted from Demo05 for GUI use."""

    def __init__(self, params_path: Optional[Path] = None, ref_obj_path: Optional[Path] = None, settings: Optional[dict] = None):
        self.params_path = Path(params_path) if params_path is not None else PARAMS_PATH
        self.ref_obj_path = Path(ref_obj_path) if ref_obj_path is not None else REF_OBJ_PATH

        self._params = None
        self._ref_obj = None
        self._load_params()
        self._load_ref_obj()

        self.bin_thresh = 60.0
        self.ppm = 5.0
        self.anchor_xmm = 10.0
        self.anchor_ymm = 10.0
        self.anchor_wmm = 30.0
        self.anchor_hmm = 30.0
        self.fabric_type = "矩形布料"
        self.fabric_color_mode = "黑白布料"
        self.hsv_lower = np.array([0, 0, 0], dtype=np.float32)
        self.hsv_upper = np.array([360, 100, 100], dtype=np.float32)

        self.x_min_mm = -30.0
        self.x_max_mm = 200.0
        self.y_min_mm = -60.0
        self.y_max_mm = 280.0

        self.ori = [0.0, 0.0, 0.0]
        self.box_ref = self._load_reference_box()

        self.T = None
        self.S = None
        self.M_top = None
        self.out_w = 0
        self.out_h = 0

        self._recompute_projection()
        if settings:
            self.apply_settings(settings)

    def _load_params(self):
        if not self.params_path.exists():
            self._params = None
            return
        try:
            self._params = np.load(str(self.params_path))
        except Exception:
            self._params = None

    def _load_ref_obj(self):
        if not self.ref_obj_path.exists():
            self._ref_obj = None
            return
        try:
            self._ref_obj = np.load(str(self.ref_obj_path))
        except Exception:
            self._ref_obj = None

    def _load_reference_box(self):
        if self._ref_obj is not None and "box_mm" in self._ref_obj.files:
            pts = np.asarray(self._ref_obj["box_mm"], dtype=np.float32).reshape(-1, 2)
            if pts.shape[0] >= 4:
                return self._order_box_points(pts[:4])*1.02
        return np.array([[0, 0], [40, 0], [40, 40], [0, 40]], dtype=np.float32)

    def apply_settings(self, settings: dict):
        def _clamp_int(value, low, high):
            return max(low, min(high, int(value)))

        self.bin_thresh = float(settings.get("bin_thresh", self.bin_thresh))
        self.ppm = float(settings.get("ppm", self.ppm))
        self.anchor_xmm = float(settings.get("anchor_xmm", self.anchor_xmm))
        self.anchor_ymm = float(settings.get("anchor_ymm", self.anchor_ymm))
        self.anchor_wmm = float(settings.get("anchor_wmm", self.anchor_wmm))
        self.anchor_hmm = float(settings.get("anchor_hmm", self.anchor_hmm))
        self.fabric_type = str(settings.get("fabric_type", self.fabric_type))

        self.fabric_color_mode = str(settings.get("fabric_color_mode", self.fabric_color_mode))
        hsv_lower = settings.get("hsv_lower", self.hsv_lower.tolist())
        hsv_upper = settings.get("hsv_upper", self.hsv_upper.tolist())
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

        self.hsv_lower = np.array(
            [
                _clamp_int(hsv_lower[0], 0, 360),
                _clamp_int(hsv_lower[1], 0, 100),
                _clamp_int(hsv_lower[2], 0, 100),
            ],
            dtype=np.float32,
        )
        self.hsv_upper = np.array(
            [
                _clamp_int(hsv_upper[0], 0, 360),
                _clamp_int(hsv_upper[1], 0, 100),
                _clamp_int(hsv_upper[2], 0, 100),
            ],
            dtype=np.float32,
        )
        self._recompute_projection()

    def _recompute_projection(self):
        self.T = np.array([[1, 0, -self.x_min_mm], [0, 1, -self.y_min_mm], [0, 0, 1]], dtype=np.float32)
        self.S = np.array([[self.ppm, 0, 0], [0, self.ppm, 0], [0, 0, 1]], dtype=np.float32)

        self.out_w = int(np.ceil((self.x_max_mm - self.x_min_mm) * self.ppm))
        self.out_h = int(np.ceil((self.y_max_mm - self.y_min_mm) * self.ppm))

        self.M_top = None
        if self._params is not None and "H_img2world" in self._params.files:
            self.M_top = self.S @ self.T @ self._params["H_img2world"]

    def _undistort(self, img: np.ndarray) -> np.ndarray:
        if self._params is None:
            return img
        keys = set(self._params.files)
        if "mtx" not in keys or "dist" not in keys:
            return img

        mtx = self._params["mtx"]
        dist = self._params["dist"]
        h, w = img.shape[:2]
        new_mtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
        return cv2.undistort(img, mtx, dist, None, new_mtx)

    def _project(self, img: np.ndarray) -> np.ndarray:
        if self.M_top is None:
            return img
        return cv2.warpPerspective(img, self.M_top, (self.out_w, self.out_h), flags=cv2.INTER_LINEAR)

    def draw_ori(self, img):
        img_ = img.copy()
        p0 = np.array([self.ori[0], self.ori[1]], dtype=np.float32)
        theta = np.deg2rad(self.ori[2])
        ux = np.array([np.cos(theta), np.sin(theta)], dtype=np.float32)
        uy = np.array([-np.sin(theta), np.cos(theta)], dtype=np.float32)
        axis_len_px = 12.0 * self.ppm
        p1 = p0 + ux * axis_len_px
        p2 = p0 + uy * axis_len_px

        cv2.arrowedLine(img_, tuple(np.round(p0).astype(int)), tuple(np.round(p1).astype(int)), (255, 0, 0), 3, tipLength=0.15)
        cv2.arrowedLine(img_, tuple(np.round(p0).astype(int)), tuple(np.round(p2).astype(int)), (0, 255, 0), 3, tipLength=0.15)
        cv2.circle(img_, tuple(np.round(p0).astype(int)), 4, (0, 0, 255), -1)
        return img_

    def draw_ref_box(self, img, box_px):
        img_ = img.copy()
        box_px_i = np.round(np.asarray(box_px, dtype=np.float32).reshape(-1, 2)).astype(np.int32)
        cv2.fillPoly(img_, [box_px_i], (0, 255, 0))
        return cv2.addWeighted(img_, 0.3, img, 0.7, 0)
    
    def draw_detected_object(self, img, points, color=(0, 0, 255), thickness=4):
        img_ = img.copy()
        if points is None:
            return img_
        cv2.polylines(img_, [points], isClosed=True, color=color, thickness=thickness)
        return img_
    
    def _detect_ori(self, img: np.ndarray):
        x = int(self.anchor_xmm * self.ppm)
        y = int(self.anchor_ymm * self.ppm)
        w = max(int(self.anchor_wmm * self.ppm), 5)
        h = max(int(self.anchor_hmm * self.ppm), 5)

        x2 = min(x + w, img.shape[1])
        y2 = min(y + h, img.shape[0])
        if x >= x2 or y >= y2:
            return [0.0, 0.0, 0.0]

        crop = img[y:y2, x:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop.copy()
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, bw = cv2.threshold(blur, 30, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return [0.0, 0.0, 0.0]

        cnt = max(contours, key=cv2.contourArea)
        rect = cv2.minAreaRect(cnt)
        box = self._order_box_points(cv2.boxPoints(rect))
        tl, tr = box[0], box[1]
        angle_deg = float(np.degrees(np.arctan2(tr[1] - tl[1], tr[0] - tl[0])))
        if angle_deg >= 90.0:
            angle_deg -= 180.0
        if angle_deg < -90.0:
            angle_deg += 180.0

        return [float(tl[0] + x), float(tl[1] + y), angle_deg], crop

    def _preprocess(self, img):
        if self.fabric_color_mode == "彩色布料":
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            _hsv_lower = self.hsv_lower.copy()
            _hsv_upper = self.hsv_upper.copy()
            _hsv_lower[0] = int(_hsv_lower[0] / 2.0)
            _hsv_lower[1] = int(_hsv_lower[1] / 100.0 * 255.0)
            _hsv_lower[2] = int(_hsv_lower[2] / 100.0 * 255.0)
            _hsv_upper[0] = int(_hsv_upper[0] / 2.0)
            _hsv_upper[1] = int(_hsv_upper[1] / 100.0 * 255.0)
            _hsv_upper[2] = int(_hsv_upper[2] / 100.0 * 255.0)
            print(f"HSV Lower: {_hsv_lower}, HSV Upper: {_hsv_upper}")
            img_bin = cv2.inRange(hsv, _hsv_lower, _hsv_upper)
        else:
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img_blur = cv2.GaussianBlur(img_gray, (5, 5), 0)
            _, img_bin = cv2.threshold(img_blur, self.bin_thresh, 255, cv2.THRESH_BINARY_INV)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(img_bin, connectivity=8)
        if num_labels <= 1:
            return img_bin

        max_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        img_bin_pick = np.zeros_like(img_bin)
        img_bin_pick[labels == max_label] = 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 50))
        return cv2.morphologyEx(img_bin_pick, cv2.MORPH_CLOSE, kernel)

    def _detect_box(self, img_bin):
        contours_ret = cv2.findContours(img_bin, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours_ret[0] if len(contours_ret) == 2 else contours_ret[1]
        if not contours:
            return None

        cnt = max(contours, key=cv2.contourArea)
        if cv2.contourArea(cnt) < 10:
            return None

        rect = cv2.minAreaRect(cnt)
        box = cv2.boxPoints(rect).astype(np.float32)
        box = self._order_box_points(box)
        return np.round(box).astype(np.int32)

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

    def _estimate_transfer(self, ref_pts, det_pts):
        ref = self._order_box_points(ref_pts).astype(np.float64)
        det = self._order_box_points(det_pts).astype(np.float64)

        c_ref = ref.mean(axis=0)
        c_det = det.mean(axis=0)
        X = ref - c_ref
        Y = det - c_det

        H = X.T @ Y
        U, _, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:
            Vt[-1, :] *= -1
            R = Vt.T @ U.T

        t = c_det - (R @ c_ref)
        pred = (R @ ref.T).T + t
        err = pred - det
        rmse = float(np.sqrt(np.mean(np.sum(err * err, axis=1))))

        theta_deg = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))
        theta_deg = ((theta_deg + 90.0) % 180.0) - 90.0
        return float(t[0]), float(t[1]), theta_deg, rmse

    def process(self, frame: np.ndarray) -> dict:
        # 1. 图像变换（去畸变+透视变换）
        im_undist = self._undistort(frame)
        im_proj = self._project(im_undist)
        # 2. 寻找坐标系原点+绘制参考区域（TODO：寻找原点不鲁棒）
        self.ori, im_ori_crop = self._detect_ori(im_proj)
        box_ref_px = self.box_ref * self.ppm + np.array([self.ori[0], self.ori[1]], dtype=np.float32)
        im_ref = self.draw_ref_box(self.draw_ori(im_proj), box_ref_px)
        # 3. 图像预处理(灰度+滤波+二值化+最大联通+闭运算)
        im_pre = self._preprocess(im_proj)
        # 4. 检测矩形目标
        box_detected = self._detect_box(im_pre)
        im_final = self.draw_detected_object(im_ref, box_detected)
        # 5. 估计平移+旋转
        found = box_detected is not None
        result = {
            "offset_x_mm": None,
            "offset_y_mm": None,
            "theta_deg": None,
            "rmse": None,
            "width_mm": None,
            "length_mm": None,
            "area_mm2": None,
            "left_top": None,
            "angle_deg": None,
        }

        if found:
            dx, dy, theta, rmse = self._estimate_transfer(box_ref_px, box_detected)
            rect = cv2.minAreaRect(box_detected.astype(np.float32))
            w_px, h_px = rect[1]
            width_mm = float(min(w_px, h_px) / max(self.ppm, 1e-6))
            length_mm = float(max(w_px, h_px) / max(self.ppm, 1e-6))
            area_mm2 = float(cv2.contourArea(box_detected.astype(np.float32)) / max(self.ppm * self.ppm, 1e-6))

            result.update(
                {
                    "offset_x_mm": float(dx / max(self.ppm, 1e-6)),
                    "offset_y_mm": float(dy / max(self.ppm, 1e-6)),
                    "theta_deg": float(theta),
                    "rmse": float(rmse / max(self.ppm, 1e-6)),
                    "width_mm": width_mm,
                    "length_mm": length_mm,
                    "area_mm2": area_mm2,
                    "left_top": tuple(map(float, box_detected[0])),
                    "angle_deg": float(theta),
                }
            )

        return {
            "raw": frame,
            "undistorted": im_undist,
            "projected": im_proj,
            "binary": cv2.cvtColor(im_pre, cv2.COLOR_GRAY2BGR),
            "ori": im_ori_crop,
            "ref": im_ref,
            "preprocess": im_pre,
            "final": im_final,
            "found": found,
            "result": result,
            "origin": self.ori,
        }
