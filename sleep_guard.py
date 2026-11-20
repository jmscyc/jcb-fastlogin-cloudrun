import sys
import platform

class SleepGuard:
    """
    Windows 系統防休眠鎖：
    在預約倒數與搶登期間，防止電腦因閒置而進入睡眠 (Sleep/Hibernate) 或關閉螢幕。
    在 Linux / macOS 上自動安全跳過。
    """
    def __init__(self):
        self.is_active = False
        self.is_windows = platform.system() == "Windows"

    def acquire(self):
        if not self.is_windows:
            return
        try:
            import ctypes
            # ES_CONTINUOUS = 0x80000000
            # ES_SYSTEM_REQUIRED = 0x00000001
            # ES_DISPLAY_REQUIRED = 0x00000002
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            self.is_active = True
        except Exception as e:
            print(f"[SleepGuard] 無法啟用防休眠鎖: {e}")

    def release(self):
        if not self.is_windows or not self.is_active:
            return
        try:
            import ctypes
            # ES_CONTINUOUS = 0x80000000 恢復正常電源管理
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            self.is_active = False
        except Exception as e:
            print(f"[SleepGuard] 無法釋放防休眠鎖: {e}")

sleep_guard = SleepGuard()
