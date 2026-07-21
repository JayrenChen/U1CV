import cv2
import numpy as np
from ctypes import *
from MVS_SDK.CamOperation_class import CameraOperation
from MVS_SDK.MvCameraControl_class import *
from MVS_SDK.CameraParams_header import *

class HikCamera:
    """
    对海康工业相机的轻量封装。

    这个类只保留当前笔记本需要的能力：
    1. 初始化 SDK、枚举并打开指定相机
    2. 设置像素格式与曝光时间
    3. 启动取流并获取单张图像
    4. 在结束时正确释放相机和 SDK 资源
    """

    PIXEL_MONO8 = 17301505
    PIXEL_BAYER_RG8 = 17301513
    PIXEL_BAYER_GB8 = 17301514
    PIXEL_RGB8_PACKED = 35127316

    def __init__(self, device_index=0, pixel_format=PIXEL_BAYER_RG8, logger=None):
        # 指定要连接的相机序号，默认连接枚举到的第一台。
        self.device_index = device_index
        # 默认使用 BayerRG8，后续由 OpenCV 完成去马赛克。
        self.pixel_format = pixel_format
        self._logger = logger or print

        self.camera = None
        self.device_list = MV_CC_DEVICE_INFO_LIST()
        self.payload_size = 0
        self.width = 0
        self.height = 0
        self.is_open = False
        self.is_grabbing = False
        self.sdk_initialized = False

    def _check_ret(self, ret, action):
        """将 SDK 返回值统一转换为 Python 异常，便于定位问题。"""
        if ret != 0:
            raise RuntimeError(f"[HK-CAMERA] {action}失败，错误码: {ret}")

    def _log(self, message):
        try:
            self._logger(message)
        except Exception:
            print(message)

    def _get_int_value(self, name):
        """读取整型参数节点，例如图像宽高、PayloadSize。"""
        st_param = MVCC_INTVALUE()
        ret = self.camera.MV_CC_GetIntValue(name, st_param)
        self._check_ret(ret, f"获取{name}")
        return st_param.nCurValue

    def _convert_frame_to_rgb(self, data_buf, frame_info):
        """
        将 SDK 返回的原始缓冲区转换为 RGB 图像。

        返回值始终为 RGB 三通道图，方便后续统一显示或保存。
        """
        actual_width = frame_info.nWidth
        actual_height = frame_info.nHeight
        pixel_type = frame_info.enPixelType
        frame_len = frame_info.nFrameLen

        # 只读取当前帧实际使用的字节数，避免误读未写入的数据。
        frame = np.frombuffer(data_buf, dtype=np.uint8, count=frame_len)

        if pixel_type == self.PIXEL_MONO8:
            expected_size = actual_width * actual_height
            if frame.size < expected_size:
                raise RuntimeError(
                    f"[HK-CAMERA] Mono8数据不足: 期望 {expected_size}, 实际 {frame.size}"
                )
            mono_frame = frame[:expected_size].reshape((actual_height, actual_width))
            return cv2.cvtColor(mono_frame, cv2.COLOR_GRAY2RGB)

        if pixel_type == self.PIXEL_BAYER_RG8:
            expected_size = actual_width * actual_height
            if frame.size < expected_size:
                raise RuntimeError(
                    f"[HK-CAMERA] BayerRG8数据不足: 期望 {expected_size}, 实际 {frame.size}"
                )
            raw_frame = frame[:expected_size].reshape((actual_height, actual_width))
            return cv2.cvtColor(raw_frame, cv2.COLOR_BayerRG2RGB)

        if pixel_type == self.PIXEL_BAYER_GB8:
            expected_size = actual_width * actual_height
            if frame.size < expected_size:
                raise RuntimeError(
                    f"[HK-CAMERA] BayerGB8数据不足: 期望 {expected_size}, 实际 {frame.size}"
                )
            raw_frame = frame[:expected_size].reshape((actual_height, actual_width))
            return cv2.cvtColor(raw_frame, cv2.COLOR_BayerGB2RGB)

        if pixel_type == self.PIXEL_RGB8_PACKED:
            expected_size = actual_width * actual_height * 3
            if frame.size < expected_size:
                raise RuntimeError(
                    f"[HK-CAMERA] RGB8数据不足: 期望 {expected_size}, 实际 {frame.size}"
                )
            rgb_frame = frame[:expected_size].reshape((actual_height, actual_width, 3))
            return rgb_frame

        raise RuntimeError(f"[HK-CAMERA] 不支持的像素格式: {pixel_type}")

    def open(self):
        """初始化 SDK、枚举设备并打开相机。"""
        if self.is_open:
            return self

        ret = MvCamera.MV_CC_Initialize()
        self._check_ret(ret, "初始化SDK")
        self.sdk_initialized = True

        n_layer_type = MV_GIGE_DEVICE | MV_USB_DEVICE | MV_GENTL_CAMERALINK_DEVICE
        ret = MvCamera.MV_CC_EnumDevices(n_layer_type, self.device_list)
        self._check_ret(ret, "枚举设备")

        self._log(f"[HK-CAMERA] 找到 {self.device_list.nDeviceNum} 台设备")
        if self.device_list.nDeviceNum == 0:
            raise RuntimeError("[HK-CAMERA] 未找到设备")
        if self.device_index >= self.device_list.nDeviceNum:
            raise IndexError(
                f"[HK-CAMERA] 设备序号越界: {self.device_index}，当前仅找到 {self.device_list.nDeviceNum} 台设备"
            )

        st_device = cast(
            self.device_list.pDeviceInfo[self.device_index],
            POINTER(MV_CC_DEVICE_INFO)
        ).contents

        self.camera = MvCamera()
        ret = self.camera.MV_CC_CreateHandle(st_device)
        self._check_ret(ret, "创建设备句柄")

        ret = self.camera.MV_CC_OpenDevice()
        self._check_ret(ret, "打开设备")
        self.is_open = True

        # 打开后先读取基础参数，便于后续分配取图缓冲区。
        self.payload_size = self._get_int_value("PayloadSize")
        self.width = self._get_int_value("Width")
        self.height = self._get_int_value("Height")
        self._log(f"[HK-CAMERA] 分辨率: {self.width}x{self.height}")

        self.set_pixel_format(self.pixel_format)
        return self

    def set_pixel_format(self, pixel_format):
        """设置相机输出像素格式，并打印回读结果做确认。"""
        if not self.is_open:
            raise RuntimeError("[HK-CAMERA] 请先打开相机，再设置像素格式")

        ret = self.camera.MV_CC_SetEnumValue("PixelFormat", pixel_format)
        self._check_ret(ret, "设置像素格式")
        self.pixel_format = pixel_format

        st_enum = MVCC_ENUMVALUE()
        ret = self.camera.MV_CC_GetEnumValue("PixelFormat", st_enum)
        if ret == 0:
            self._log(f"[HK-CAMERA] 当前 PixelFormat: {st_enum.nCurValue}")

    def set_exposure(self, exposure_time_us):
        """
        设置曝光时间，单位为微秒。

        这里先关闭自动曝光，避免手动曝光值被相机自动策略覆盖。
        """
        if not self.is_open:
            raise RuntimeError("[HK-CAMERA] 请先打开相机，再设置曝光时间")

        ret = self.camera.MV_CC_SetEnumValue("ExposureAuto", 0)
        self._check_ret(ret, "关闭自动曝光")

        ret = self.camera.MV_CC_SetFloatValue("ExposureTime", float(exposure_time_us))
        self._check_ret(ret, "设置曝光时间")

    def start_grabbing(self):
        """启动取流，使后续可以通过 get_one_frame 获取图像。"""
        if not self.is_open:
            raise RuntimeError("[HK-CAMERA] 请先打开相机，再开始抓图")
        if self.is_grabbing:
            return

        ret = self.camera.MV_CC_StartGrabbing()
        self._check_ret(ret, "开始抓图")
        self.is_grabbing = True

    def stop_grabbing(self):
        """停止取流，但保留设备句柄，便于继续设置参数或重新开始抓图。"""
        if self.is_open and self.is_grabbing:
            ret = self.camera.MV_CC_StopGrabbing()
            self._check_ret(ret, "停止抓图")
            self.is_grabbing = False

    def get_one_frame(self, timeout_ms=1000):
        """
        获取单张图像。

        返回值:
        - frame_rgb: OpenCV 格式的 RGB 图像
        - frame_info: SDK 返回的原始帧信息结构体
        """
        if not self.is_open:
            raise RuntimeError("[HK-CAMERA] 请先打开相机，再获取图像")
        if not self.is_grabbing:
            raise RuntimeError("[HK-CAMERA] 请先开始抓图，再获取图像")

        data_buf = (c_ubyte * self.payload_size)()
        frame_info = MV_FRAME_OUT_INFO_EX()
        ret = self.camera.MV_CC_GetOneFrameTimeout(
            byref(data_buf),
            self.payload_size,
            frame_info,
            timeout_ms
        )
        self._check_ret(ret, "[HK-CAMERA] 获取单张图像")

        frame_rgb = self._convert_frame_to_rgb(data_buf, frame_info)
        return frame_rgb, frame_info

    def close(self):
        """
        按正确顺序释放资源：先停流，再关设备，最后销毁句柄并反初始化 SDK。

        这个方法允许重复调用，方便在 finally 中无条件清理。
        """
        if self.camera is not None and self.is_grabbing:
            try:
                self.stop_grabbing()
            except RuntimeError:
                pass

        if self.camera is not None and self.is_open:
            ret = self.camera.MV_CC_CloseDevice()
            self._check_ret(ret, "[HK-CAMERA] 关闭设备")
            self.is_open = False

        if self.camera is not None:
            self.camera.MV_CC_DestroyHandle()
            self.camera = None

        if self.sdk_initialized:
            MvCamera.MV_CC_Finalize()
            self.sdk_initialized = False
