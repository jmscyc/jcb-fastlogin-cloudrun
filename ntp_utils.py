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
            data = b'\x1b' + 47 * b'\0'
            t1 = time.time()
            client.sendto(data, (server, 123))
            resp, _ = client.recvfrom(1024)
            t4 = time.time()
            client.close()
            
            if resp and len(resp) >= 48:
                unpacked = struct.unpack('!12I', resp[0:48])
                t3 = unpacked[10] + float(unpacked[11]) / (2**32) - NTP_DELTA
                offset = t3 - ((t1 + t4) / 2)
                return offset
        except Exception:
            continue
    return 0.0

def get_sprint_interval(now_timestamp: float) -> Tuple[int, str]:
    """
    以台北時間 (UTC+8) 為基準，精準計算距離 09:00:00 (即 UTC 01:00:00) 搶登時刻的間隔。
    同時無論在本地手動測試或在 GitHub Actions 雲端伺服器 (UTC 預設環境) 皆能完美對齊時區！
    """
    # 轉換為 UTC+8 (台北標準時間)
    taipei_time = time.gmtime(now_timestamp + 8 * 3600)
    
    # 計算今天台北時間 09:00:00 對應的秒數
    # 台北 09:00:00 = 9 * 3600 = 32400 秒
    seconds_since_midnight_taipei = taipei_time.tm_hour * 3600 + taipei_time.tm_min * 60 + taipei_time.tm_sec
    target_seconds = 9 * 3600 # 09:00:00
    
    diff = target_seconds - seconds_since_midnight_taipei
    
    # 若在 08:55:00 ~ 09:05:00 的開搶視窗範圍外，視為一般搶登/手動測試模式
    if diff > 1800 or diff < -300:
        return 500, "常規模式 (500ms)"
    
    # 在 09:00:00 ~ 09:00:30 (開搶後前 30 秒)
    if -30 <= diff <= 0:
        return 120, "⚡ 極限毫秒衝刺中 (120ms)"
    # 倒數 5 秒內 (08:59:55 ~ 08:59:59)
    elif 0 < diff <= 5:
        return 150, "🔥 倒數 5 秒極速衝刺預備 (150ms)"
    # 倒數 30 秒內 (08:59:30 ~ 08:59:55)
    elif 5 < diff <= 30:
        return 400, "🚀 倒數 30 秒提速巡邏 (400ms)"
    # 倒數 30 秒以上 (08:55:00 ~ 08:59:30)
    else:
        return 2000, f"⏳ 離 09:00 開搶尚有 {int(diff)} 秒，低頻節能巡航 (2000ms)"
