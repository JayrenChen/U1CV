class CameraInterface:
    """Lightweight camera adapter for HikCamera single-shot capture."""

    def __init__(self, device_index=0, exposure=50000, logger=None, camera_key=None):
        self.device_index = device_index
        self.exposure = exposure
        self.camera_key = str(camera_key or "").strip()
        self._logger = logger or print
        self._camera = None
        self._is_ready = False

    @staticmethod
    def list_devices():
        from hik_camera import HikCamera

        return HikCamera.enumerate_devices()

    def _ensure_ready(self):
        if self._is_ready:
            return

        from hik_camera import HikCamera

        self._camera = HikCamera(device_index=self.device_index, logger=self._logger, camera_key=self.camera_key)
        self._camera.open()
        self._camera.set_exposure(self.exposure)
        self._camera.start_grabbing()
        self._is_ready = True

    def capture_once(self):
        self._ensure_ready()
        frame, frame_info = self._camera.get_one_frame()
        if frame is None:
            raise RuntimeError("Failed to capture image from camera")
        return frame

    def update_exposure(self, exposure):
        self.exposure = float(exposure)
        if self._camera is None:
            return
        try:
            self._camera.set_exposure(self.exposure)
        except Exception:
            pass

    def close(self):
        if self._camera is None:
            return

        try:
            self._camera.close()
        except Exception:
            pass
        finally:
            self._camera = None
            self._is_ready = False
