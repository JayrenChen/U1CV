from __future__ import annotations

import os
import platform


def _import_serial():
    import serial
    from serial.tools import list_ports

    return serial, list_ports


class LightSourceController:
    DEFAULT_BAUDRATE = 19200
    ONLINE_REGISTER = 0x01B1
    CHANNEL_BRIGHTNESS_REGISTERS = {
        1: 0x0001,
    }
    CHANNEL_STATE_REGISTERS = {
        1: 0x0041,
    }

    def __init__(self, port=None, baudrate=DEFAULT_BAUDRATE, address=1, logger=None):
        self.port = port or ""
        self.baudrate = int(baudrate)
        self.address = int(address)
        self._serial = None
        self._logger = logger or self._noop_logger

    def set_logger(self, logger):
        self._logger = logger or self._noop_logger

    @staticmethod
    def _noop_logger(_message):
        """Default logger: discards messages instead of printing to stdout.
        Light source control logs should only be shown in the GUI."""
        pass

    @staticmethod
    def list_serial_ports():
        try:
            _, list_ports = _import_serial()
        except Exception:
            return []

        ports = []
        for port_info in list_ports.comports():
            port_name = getattr(port_info, "device", None) or getattr(port_info, "name", None) or str(port_info)
            if port_name and port_name not in ports:
                ports.append(port_name)
        return ports

    @staticmethod
    def _crc16(data):
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF

    @staticmethod
    def _hex(data):
        return " ".join(f"{byte:02X}" for byte in data)

    def _log(self, message):
        try:
            self._logger(message)
        except Exception:
            pass

    def _format_open_error(self, exc):
        message = str(exc)
        is_linux = platform.system().lower() == "linux"
        is_permission_error = (
            getattr(exc, "errno", None) == 13
            or "Permission denied" in message
            or "Errno 13" in message
        )

        if is_linux and is_permission_error:
            hints = [
                f"串口权限不足: {self.port}",
                "请将当前用户加入 dialout 组并重新登录:",
                f"  sudo usermod -aG dialout $USER",
                "然后执行以下命令确认设备权限:",
                f"  ls -l {self.port}",
                "必要时临时授权(重启后失效):",
                f"  sudo chmod 666 {self.port}",
            ]
            return "\n".join(hints)

        if is_linux and os.path.exists(self.port) and not os.access(self.port, os.R_OK | os.W_OK):
            return f"串口存在但当前用户无读写权限: {self.port}"

        return message

    def close(self):
        if self._serial is None:
            return

        try:
            self._serial.close()
        except Exception:
            pass
        finally:
            self._serial = None

    def open(self, port=None, baudrate=None):
        if port is not None:
            self.port = str(port).strip()
        if baudrate is not None:
            self.baudrate = int(baudrate)

        if not self.port:
            raise ValueError("未选择光源串口")

        if self._serial is not None:
            same_port = getattr(self._serial, "port", None) == self.port
            same_baud = getattr(self._serial, "baudrate", None) == self.baudrate
            if same_port and same_baud:
                return self._serial
            self.close()

        serial, _ = _import_serial()
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.25,
                write_timeout=0.5,
            )
        except Exception as exc:
            raise RuntimeError(self._format_open_error(exc)) from exc
        self._log(f"[光源控制] 串口已打开: {self.port}, baudrate={self.baudrate}")
        return self._serial

    def _ensure_open(self):
        if self._serial is None:
            self.open()
        return self._serial

    def _read_response(self):
        response = bytearray()
        serial_port = self._ensure_open()

        while True:
            chunk = serial_port.read(256)
            if not chunk:
                break
            response.extend(chunk)
            if len(chunk) < 256:
                continue

        return bytes(response)

    def _send_frame(self, frame):
        serial_port = self._ensure_open()
        if hasattr(serial_port, "reset_input_buffer"):
            try:
                serial_port.reset_input_buffer()
            except Exception:
                pass
        serial_port.write(frame)
        serial_port.flush()
        self._log(f"[光源控制] TX: {self._hex(frame)}")
        response = self._read_response()
        if response:
            self._log(f"[光源控制] RX: {self._hex(response)}")
            self._log(self._parse_response(response))
        else:
            self._log("[光源控制] RX: 无返回数据")
        return response

    def _build_read_frame(self, register, count=1):
        payload = bytes([
            self.address,
            0x03,
            (register >> 8) & 0xFF,
            register & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        ])
        crc = self._crc16(payload)
        return payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    def _build_write_frame(self, register, value):
        payload = bytes([
            self.address,
            0x06,
            (register >> 8) & 0xFF,
            register & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
            0x00,
        ])
        crc = self._crc16(payload)
        return payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    def _parse_response(self, frame):
        if len(frame) < 4:
            return f"[光源控制] 响应过短: {self._hex(frame)}"

        crc_expected = self._crc16(frame[:-2])
        crc_actual = frame[-2] | (frame[-1] << 8)
        crc_ok = crc_expected == crc_actual
        func = frame[1]

        if func == 0x06:
            if len(frame) >= 6:
                register = (frame[2] << 8) | frame[3]
                if len(frame) >= 8 and frame[6] == 0x00:
                    value = (frame[4] << 8) | frame[5]
                    return (
                        f"[光源控制] 写寄存器应答: register=0x{register:04X}, value=0x{value:04X}, "
                        f"crc={'OK' if crc_ok else 'ERR'}"
                    )
                return f"[光源控制] 写寄存器确认: register=0x{register:04X}, crc={'OK' if crc_ok else 'ERR'}"
            return f"[光源控制] 写寄存器响应异常: {self._hex(frame)}"

        if func == 0x03:
            if len(frame) < 5:
                return f"[光源控制] 读寄存器响应异常: {self._hex(frame)}"
            data_len = frame[2]
            data_start = 3
            data_end = data_start + data_len
            data = frame[data_start:data_end]
            register = None
            value = None
            if len(data) >= 4:
                register = (data[0] << 8) | data[1]
                value = (data[2] << 8) | data[3]
            elif len(data) >= 2:
                value = (data[0] << 8) | data[1]
            extra_flag = ""
            if len(frame) == data_end + 3 and frame[data_end] == 0x00:
                extra_flag = ", extra=00"
            if register is not None and value is not None:
                return (
                    f"[光源控制] 读寄存器应答: register=0x{register:04X}, value=0x{value:04X}, "
                    f"data_len={data_len}{extra_flag}, crc={'OK' if crc_ok else 'ERR'}"
                )
            if value is not None:
                return f"[光源控制] 读寄存器应答: value=0x{value:04X}, data_len={data_len}{extra_flag}, crc={'OK' if crc_ok else 'ERR'}"
            return f"[光源控制] 读寄存器应答: data={self._hex(data)}, data_len={data_len}{extra_flag}, crc={'OK' if crc_ok else 'ERR'}"

        return f"[光源控制] 未知响应: {self._hex(frame)}, crc={'OK' if crc_ok else 'ERR'}"

    def read_register(self, register, count=1):
        frame = self._build_read_frame(register, count=count)
        response = self._send_frame(frame)
        return response

    def write_register(self, register, value):
        frame = self._build_write_frame(register, value)
        response = self._send_frame(frame)
        return response

    def set_channel_brightness(self, channel, brightness):
        channel = int(channel)
        if channel not in self.CHANNEL_BRIGHTNESS_REGISTERS:
            raise ValueError(f"不支持的光源通道: {channel}")
        brightness = max(0, min(255, int(brightness)))
        register = self.CHANNEL_BRIGHTNESS_REGISTERS[channel]
        self._log(f"[光源控制] 设置通道{channel}亮度={brightness}")
        return self.write_register(register, brightness)

    def set_channel_state(self, channel, enabled):
        channel = int(channel)
        if channel not in self.CHANNEL_STATE_REGISTERS:
            raise ValueError(f"不支持的光源通道: {channel}")
        register = self.CHANNEL_STATE_REGISTERS[channel]
        value = 1 if bool(enabled) else 0
        self._log(f"[光源控制] 设置通道{channel}开关={'开' if value else '关'}")
        return self.write_register(register, value)

    def check_online(self):
        self._log("[光源控制] 读取控制器在线状态")
        response = self.read_register(self.ONLINE_REGISTER, count=1)
        if not response:
            self._log("[光源控制] 在线状态: 未收到响应")
            return False

        if len(response) >= 9 and response[1] == 0x03:
            data_len = response[2]
            data = response[3:3 + data_len]
            if len(data) >= 4:
                value = (data[2] << 8) | data[3]
                online = value == 1
                self._log(f"[光源控制] 在线状态: {'在线' if online else '离线'}, value=0x{value:04X}")
                return online

        self._log(f"[光源控制] 在线状态解析失败: {self._hex(response)}")
        return False

    def apply_settings(self, port=None, baudrate=None, intensity=50, enabled=False, check_online=True):
        try:
            if port is not None:
                self.port = str(port).strip()
            if baudrate is not None:
                self.baudrate = int(baudrate)

            self.open()
            self.set_channel_brightness(1, intensity)
            self.set_channel_state(1, enabled)
            if check_online:
                self.check_online()
            return True
        except Exception as exc:
            self._log(f"[光源控制] 同步失败: {exc}")
            return False
