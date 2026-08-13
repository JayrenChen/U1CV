from __future__ import annotations

import threading


class ModbusRtuSlave:
    """Minimal Modbus RTU slave supporting protocol function codes 0x03 and 0x06."""

    def __init__(self, port, baudrate=115200, unit_id=1, on_trigger=None, logger=None):
        self.port = str(port or "").strip()
        self.baudrate = int(baudrate)
        self.unit_id = int(unit_id)
        self.on_trigger = on_trigger
        self.logger = logger or (lambda _message: None)
        self._serial = None
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._registers = {0x0001: 0, 0x0011: 0, 0x0012: 0, 0x0013: 0, 0x0014: 0, 0x0021: 0}

    @staticmethod
    def crc16(data):
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc & 0xFFFF

    @classmethod
    def with_crc(cls, payload):
        crc = cls.crc16(payload)
        return bytes(payload) + bytes((crc & 0xFF, crc >> 8))

    @staticmethod
    def _encode_scaled_int16(value):
        signed_value = max(-32768, min(32767, int(round(float(value) * 100))))
        return signed_value & 0xFFFF

    def update_result(self, success, offset_x_mm=0.0, offset_y_mm=0.0, theta_deg=0.0):
        with self._lock:
            self._registers[0x0011] = 0 if success else 1
            self._registers[0x0012] = self._encode_scaled_int16(offset_x_mm) if success else 0
            self._registers[0x0013] = self._encode_scaled_int16(offset_y_mm) if success else 0
            self._registers[0x0014] = self._encode_scaled_int16(theta_deg) if success else 0

    def set_device_status(self, status_code):
        with self._lock:
            self._registers[0x0001] = int(status_code) & 0xFFFF

    def start(self):
        if not self.port:
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._serve, name="modbus-rtu-slave", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop_event.set()
        serial_port = self._serial
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        self._serial = None

    def _serve(self):
        try:
            import serial

            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                write_timeout=0.5,
            )
            self.logger(f"[PLC通信] Modbus从机已启动: {self.port}, {self.baudrate}, 地址 {self.unit_id}")
            buffer = bytearray()
            while not self._stop_event.is_set():
                chunk = self._serial.read(256)
                if chunk:
                    buffer.extend(chunk)
                    self._consume_frames(buffer)
        except Exception as exc:
            if not self._stop_event.is_set():
                self.logger(f"[PLC通信] 串口服务已停止: {exc}")
        finally:
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None

    def _consume_frames(self, buffer):
        while len(buffer) >= 8:
            if buffer[0] != self.unit_id:
                del buffer[0]
                continue
            frame = bytes(buffer[:8])
            expected_crc = self.crc16(frame[:-2])
            actual_crc = frame[-2] | (frame[-1] << 8)
            if expected_crc != actual_crc:
                del buffer[0]
                continue
            del buffer[:8]
            response = self.handle_request(frame)
            self.logger(f"[PLC通信] 接收 {self._hex(frame)} | {self._describe_request(frame)}")
            if response and self._serial is not None:
                self._serial.write(response)
                self._serial.flush()
                self.logger(f"[PLC通信] 回复 {self._hex(response)} | {self._describe_response(frame, response)}")

    @staticmethod
    def _hex(frame):
        return " ".join(f"{byte:02X}" for byte in frame)

    @staticmethod
    def _signed_int16(value):
        return value - 0x10000 if value & 0x8000 else value

    @staticmethod
    def _register_name(address):
        return {
            0x0001: "系统状态",
            0x0011: "移料前检测状态",
            0x0012: "X偏差",
            0x0013: "Y偏差",
            0x0014: "R偏差",
            0x0021: "移料后检测结果",
        }.get(address, f"寄存器0x{address:04X}")

    def _describe_request(self, frame):
        function_code = frame[1]
        address = (frame[2] << 8) | frame[3]
        value = (frame[4] << 8) | frame[5]
        if function_code == 0x03:
            return f"读取 {self._register_name(address)} 起始=0x{address:04X}，数量={value}"
        if function_code == 0x06:
            if address == 0x0010 and value == 1:
                return "写入 0x0010=1，触发移料前视觉检测"
            return f"写入 {self._register_name(address)}=0x{value:04X}"
        return f"功能码 0x{function_code:02X}"

    def _describe_response(self, request, response):
        function_code = request[1]
        address = (request[2] << 8) | request[3]
        if function_code == 0x06:
            return "已确认移料前视觉检测触发" if address == 0x0010 else "写入确认"
        if function_code != 0x03 or response[1] != 0x03 or len(response) < 5:
            return "异常响应" if response[1] & 0x80 else "响应完成"

        response_address = (response[2] << 8) | response[3]
        raw_value = (response[4] << 8) | response[5]
        if response_address in (0x0012, 0x0013):
            return f"{self._register_name(response_address)}={self._signed_int16(raw_value) / 100:.2f} mm"
        if response_address == 0x0014:
            return f"R偏差={self._signed_int16(raw_value) / 100:.2f} deg"
        return f"{self._register_name(response_address)}={raw_value}"

    def handle_request(self, frame):
        if len(frame) != 8 or frame[0] != self.unit_id:
            return b""
        if self.crc16(frame[:-2]) != (frame[-2] | (frame[-1] << 8)):
            return b""

        function_code = frame[1]
        address = (frame[2] << 8) | frame[3]
        value = (frame[4] << 8) | frame[5]
        if function_code == 0x03:
            if value not in (0, 1):
                return self._exception(function_code, 0x03)
            with self._lock:
                register_value = self._registers.get(address, 0)
            return self.with_crc(bytes((
                self.unit_id,
                function_code,
                (address >> 8) & 0xFF,
                address & 0xFF,
                (register_value >> 8) & 0xFF,
                register_value & 0xFF,
            )))

        if function_code == 0x06:
            if address == 0x0010 and value == 1:
                self.update_result(False)
                callback = self.on_trigger
                if callback is not None:
                    try:
                        callback()
                    except Exception as exc:
                        self.logger(f"[PLC通信] 触发检测失败: {exc}")
            return self.with_crc(frame[:6])

        return self._exception(function_code, 0x01)

    def _exception(self, function_code, exception_code):
        return self.with_crc(bytes((self.unit_id, function_code | 0x80, exception_code)))