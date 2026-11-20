import socket
import struct
import time
from typing import Tuple

NTP_SERVERS = [
    "time.stdtime.gov.tw",
    "clock.stdtime.gov.tw",
    "pool.ntp.org",
    "time.google.com"
]

def get_ntp_offset(timeout: float = 2.0) -> float:
    """
    透過 UDP 協定向標準 NTP 伺服器對時，計算本地時鐘與標準時間之毫秒偏差 (Offset)。
    正值代表本地時間比 NTP 慢，負值代表本地時間比 NTP 快。
    """
    NTP_DELTA = 2208988800 # 1900 到 1970 的秒數
    for server in NTP_SERVERS:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(timeout)
            # NTP 請求封包 (48 bytes, 第一 byte 0x1b 代表 client mode)
            data = b'\x1b' + 47 * b'\0'
            t1 = time.time()
            client.sendto(data, (server, 123))
            resp, _ = client.recvfrom(1024)
            t4 = time.time()
            client.close()
            
            if resp and len(resp) >= 48:
                unpacked = struct.unpack('!12I', resp[0:48])
                # t3 是伺服器傳送時間 (Transmit Timestamp)
                t3 = unpacked[10] + float(unpacked[11]) / (2**32) - NTP_DELTA
                # 計算時間位移
                offset = t3 - ((t1 + t4) / 2)
                return offset
        except Exception:
            continue
    return 0.0

def get_sprint_interval(now_timestamp: float, target_hour: int = 9, target_minute: int = 0) -> Tuple[int, str]:
    """
    計算距離下一個整點 (預設 09:00:00) 的剩餘秒數，並決定探測衝刺間隔 (ms)。
    三段式變速策略：
    - 剩餘 > 30 秒: 輕鬆巡邏 (2000ms)，避免造成負擔或被限流
    - 剩餘 5~30 秒: 提速加溫 (500ms)
    - 剩餘 < 5 秒: 極限毫秒衝刺 (150ms)
    """
    lt = time.localtime(now_timestamp)
    target_today = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, target_hour, target_minute, 0, 0, 0, -1))
    diff = target_today - now_timestamp
    
    if diff < -15:
        return 500, "常規搶登期 (500ms)"
    elif diff <= 0: # 09:00:00 ~ 09:00:15
        return 120, "⚡ 極限毫秒衝刺中 (120ms)"
    elif diff <= 5: # 08:59:55 ~ 08:59:59
        return 150, "🔥 倒數 5 秒極速衝刺預備 (150ms)"
    elif diff <= 30: # 08:59:30 ~ 08:59:55
        return 400, "🚀 倒數 30 秒提速巡邏 (400ms)"
    else:
        return 2000, f"⏳ 離整點尚有 {int(diff)} 秒，低頻節能巡航 (2000ms)"
