"""
autochat_system.py
=================================================================
2 công tắc điều khiển auto-chat (tin nhắn Sempai tự bắt chuyện
mỗi khi im lặng quá lâu):

CÔNG TẮC 1 — Giới hạn streak:
  Sau AUTO_STREAK_LIMIT (mặc định 4, trong khoảng 3-5) tin auto
  LIÊN TIẾP mà không ai trả lời -> Sempai gửi 1 câu nhắc cuối
  cùng ("nhớ liên lạc với chị") rồi IM LUÔN, không tự nhắn nữa
  cho tới khi có người thật chat lại (streak tự reset về 0).

CÔNG TẮC 2 — Sleep mode (buổi tối giờ VN):
  Nếu Funnas chúc Sempai "ngủ ngon" vào buổi tối -> tắt hẳn
  auto-chat 30 phút, tới khi Funnas gọi dậy (nói "gọi dậy",
  "dậy đi", "mới ngủ dậy"...) mới bật lại.
  Bạn bè khác vẫn chat được bình thường (bot vẫn trả lời), NHƯNG
  không có tác dụng bật lại auto-chat — chỉ Funnas mới gọi dậy được.

State ở đây là runtime (RAM), reset khi bot restart — chấp nhận
được vì bot đang bản beta, không cần persistent.
=================================================================
"""
import os
from datetime import datetime, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))

# ---- Cấu hình (có thể chỉnh qua biến môi trường nếu muốn) ----
AUTO_STREAK_LIMIT = int(os.getenv('AUTO_STREAK_LIMIT', 4))       # 3-5 tin, mặc định 4
EVENING_START_HOUR = int(os.getenv('SLEEP_EVENING_START_HOUR', 20))  # 20h tối
EVENING_END_HOUR = int(os.getenv('SLEEP_EVENING_END_HOUR', 5))       # tới 5h sáng

SLEEP_TRIGGER_KEYWORDS = ["ngủ ngon"]
WAKE_TRIGGER_KEYWORDS = ["gọi dậy", "dậy đi", "thức dậy", "ngủ dậy", "mới ngủ dậy", "dậy chưa"]

# ---- Runtime state ----
_state = {
    "auto_streak": 0,      # số tin auto-chat liên tiếp đã gửi (chưa ai trả lời)
    "sleep_mode": False,   # đang ngủ (tắt auto-chat) hay không
}


# =================================================================
# 🕐 Kiểm tra "buổi tối" theo giờ VN
# =================================================================
def is_evening_vn(now=None):
    now = now or datetime.now(VN_TZ)
    hour = now.hour
    if EVENING_START_HOUR <= EVENING_END_HOUR:
        return EVENING_START_HOUR <= hour < EVENING_END_HOUR
    # Khoảng giờ qua đêm, VD 23h30 -> 5h sáng hôm sau
    return hour >= EVENING_START_HOUR or hour < EVENING_END_HOUR


def _contains_any(text, keywords):
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def is_sleep_trigger(user_msg):
    return _contains_any(user_msg, SLEEP_TRIGGER_KEYWORDS)


def is_wake_trigger(user_msg):
    return _contains_any(user_msg, WAKE_TRIGGER_KEYWORDS)


# =================================================================
# 🔧 PUBLIC API — main.py gọi các hàm này
# =================================================================
def reset_streak_on_human_message():
    """Gọi mỗi khi có người THẬT nhắn tin (bất kỳ ai) -> reset streak về 0."""
    _state["auto_streak"] = 0


def enable_sleep_mode():
    _state["sleep_mode"] = True
    print("🌙 [Sleep mode] BẬT — tạm dừng auto-chat 30 phút tới khi Funnas gọi dậy.")


def disable_sleep_mode():
    _state["sleep_mode"] = False
    _state["auto_streak"] = 0
    print("☀️ [Sleep mode] TẮT — auto-chat hoạt động lại bình thường.")


def is_sleep_mode():
    return _state["sleep_mode"]


def can_send_auto_message():
    """
    Có được phép gửi auto-chat lúc này không.
    Trả về (allowed: bool, is_final_warning: bool)

    - allowed=False nếu đang sleep_mode HOẶC đã đạt streak limit
    - is_final_warning=True nếu đây là tin CUỐI CÙNG trước khi
      dừng hẳn (dùng để chèn thêm câu "nhớ liên lạc với chị")
    """
    if _state["sleep_mode"]:
        return False, False

    if _state["auto_streak"] >= AUTO_STREAK_LIMIT:
        return False, False

    is_final = (_state["auto_streak"] == AUTO_STREAK_LIMIT - 1)
    return True, is_final


def record_auto_message_sent():
    """Gọi sau khi auto-chat gửi thành công, tăng streak lên 1."""
    _state["auto_streak"] += 1
