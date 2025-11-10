import math
import time
from io import BytesIO
from typing import Optional, Tuple

import numpy as np
import streamlit as st
import wave

# Optional browser recorder dependency
try:
	from streamlit_audiorec import st_audiorec  # type: ignore
	AUDIOREC_AVAILABLE = True
except Exception:
	AUDIOREC_AVAILABLE = False

# Optional realtime mic via WebRTC (recommended on Python 3.10 x64)
WEBRTC_AVAILABLE = False
try:
	from streamlit_webrtc import (  # type: ignore
		AudioProcessorBase,
		RTCConfiguration,
		WebRtcMode,
		webrtc_streamer,
	)
	import av  # type: ignore
	WEBRTC_AVAILABLE = True
except Exception:
	WEBRTC_AVAILABLE = False


st.set_page_config(page_title="Trợ lý âm đọc - Streamlit", page_icon="🗣️", layout="centered")

# App title and description
st.title("🗣️ Trợ lý nhận biết âm lượng khi đọc bài")
st.caption(
	"Ứng dụng giúp học sinh luyện đọc: nếu đọc to đủ thì được khen, nếu đọc nhỏ thì được khuyến khích. "
	"Kết nối trực tiếp với mic của máy tính."
)


def compute_rms_and_dbfs(audio: np.ndarray) -> Tuple[float, float]:
	"""
	Compute RMS (0.0..1.0) and dBFS given a mono float32/float64/ int16 waveform.
	Assumes audio is mono; if stereo, caller should downmix first.
	"""
	if audio.ndim > 1:
		audio = audio.mean(axis=1)

	# Convert to float32 in range [-1, 1] if needed
	if np.issubdtype(audio.dtype, np.integer):
		# int16 expected from WebRTC frame
		audio = audio.astype(np.float32) / 32768.0
	else:
		audio = audio.astype(np.float32)

	# Guard for empty or silent buffers
	if audio.size == 0:
		return 0.0, -math.inf

	rms = float(np.sqrt(np.mean(np.square(audio))))
	# dBFS relative to 1.0 full scale
	dbfs = 20.0 * math.log10(max(rms, 1e-12))
	return rms, dbfs


def wav_bytes_to_mono_array(wav_bytes: bytes) -> Tuple[np.ndarray, int]:
	"""
	Read PCM WAV bytes and return mono float32 waveform in [-1, 1] and sample_rate.
	"""
	with wave.open(BytesIO(wav_bytes), "rb") as wf:
		num_channels = wf.getnchannels()
		sample_width = wf.getsampwidth()
		sample_rate = wf.getframerate()
		num_frames = wf.getnframes()
		raw = wf.readframes(num_frames)

		# Only handle 16-bit PCM and 32-bit float for simplicity
		if sample_width == 2:
			data = np.frombuffer(raw, dtype=np.int16)
			if num_channels > 1:
				data = data.reshape(-1, num_channels).mean(axis=1).astype(np.int16)
			arr = (data.astype(np.float32) / 32768.0).astype(np.float32)
		elif sample_width == 4:
			# Could be 32-bit PCM or float; assume float32 little-endian
			data = np.frombuffer(raw, dtype=np.float32)
			if num_channels > 1:
				data = data.reshape(-1, num_channels).mean(axis=1).astype(np.float32)
			# Clip to [-1,1] just in case
			arr = np.clip(data, -1.0, 1.0).astype(np.float32)
		else:
			# Fallback: treat as bytes -> int16
			data = np.frombuffer(raw, dtype=np.int16)
			if num_channels > 1:
				data = data.reshape(-1, num_channels).mean(axis=1).astype(np.int16)
			arr = (data.astype(np.float32) / 32768.0).astype(np.float32)

	return arr, sample_rate


# Default messages
DEFAULT_PRAISE = "Tuyệt vời! Con đọc rõ ràng và to đủ, tiếp tục phát huy nhé! 🎉"
DEFAULT_ENCOURAGE = "Hãy tự tin hơn và đọc to hơn một chút nhé! Con làm được! 💪"


with st.sidebar:
	st.header("⚙️ Cài đặt")
	student_name = st.text_input("Tên học sinh", value="Học sinh")
	target_dbfs = st.slider(
		"Mức âm lượng mục tiêu (dBFS, càng gần 0 càng to)",
		min_value=-60,
		max_value=-5,
		value=-25,
		step=1,
		help="Đề xuất: -25 dBFS (đọc vừa đủ to)."
	)
	grace_seconds = st.slider(
		"Thời gian duy trì để được khen (giây)",
		min_value=0.5,
		max_value=3.0,
		value=1.0,
		step=0.5,
		help="Cần duy trì mức âm lượng mục tiêu trong khoảng thời gian này."
	)
	msg_praise = st.text_area("Thông điệp khen", value=DEFAULT_PRAISE, height=80)
	msg_encourage = st.text_area("Thông điệp khuyến khích", value=DEFAULT_ENCOURAGE, height=80)
	st.markdown("---")
	if WEBRTC_AVAILABLE:
		st.caption("Mic realtime (WebRTC). Nếu trình duyệt hỏi quyền micro, hãy bấm Cho phép.")
	else:
		st.caption("Ghi âm hoặc tải WAV. Để dùng mic realtime, cài `streamlit-webrtc` và `av` (khuyên dùng Python 3.10 x64).")

st.subheader("🎤 Nguồn âm thanh")
wav_audio_data = None
webrtc_ctx = None

if WEBRTC_AVAILABLE:
	class LoudnessProcessor(AudioProcessorBase):  # type: ignore[misc]
		def __init__(self) -> None:
			self.smoothed_rms: float = 0.0
			self.alpha: float = 0.3
		def recv_audio(self, frame: av.AudioFrame):  # type: ignore[override]
			samples = frame.to_ndarray()
			if samples.ndim == 2:
				samples = samples.mean(axis=0)
			rms, dbfs = compute_rms_and_dbfs(samples)
			self.smoothed_rms = self.alpha * rms + (1.0 - self.alpha) * self.smoothed_rms
			st.session_state["current_rms"] = self.smoothed_rms
			st.session_state["current_dbfs"] = dbfs
			return frame

	rtc_config = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
	webrtc_ctx = webrtc_streamer(
		key="audio-level-trainer",
		mode=WebRtcMode.SENDONLY,  # type: ignore[arg-type]
		audio_receiver_size=256,
		video_frame_callback=None,
		audio_processor_factory=LoudnessProcessor,
		media_stream_constraints={"audio": True, "video": False},
		rtc_configuration=rtc_config,
	)
	st.caption("Bấm nút Start/Stop ngay trong khung trên để bật/tắt micro realtime.")
else:
	# Cung cấp nút Start/Stop đơn giản cho chế độ không-WebRTC
	start_capture = st.toggle("Start", value=True)
	if AUDIOREC_AVAILABLE:
		if start_capture:
			st.caption("Giữ nút ghi âm để đọc, thả để dừng và phân tích.")
			wav_audio_data = st_audiorec()  # type: ignore[assignment]
		else:
			st.info("Nhấn Start để bật ghi âm.")
	else:
		if start_capture:
			st.caption("Tải lên tệp WAV để phân tích nếu chưa có ghi âm trực tiếp.")
			uploaded = st.file_uploader("Tải lên tệp WAV (mono/stereo, 16-bit PCM)", type=["wav"])
			wav_audio_data = uploaded.read() if uploaded is not None else None
		else:
			st.info("Nhấn Start để bật nhập tệp WAV.")

st.subheader("📈 Mức âm lượng hiện tại")
level_placeholder = st.empty()
meter_placeholder = st.empty()
feedback_placeholder = st.empty()


def rms_to_percent(rms: float) -> float:
	"""
	Map RMS (0..1) to a 0..100 scale for a simple progress meter, with soft knee.
	"""
	# Soft knee via square root to feel responsive at low levels
	return float(min(100.0, max(0.0, (math.sqrt(max(rms, 0.0)) * 100.0))))


# State init
st.session_state.setdefault("current_rms", 0.0)
st.session_state.setdefault("current_dbfs", -math.inf)
st.session_state.setdefault("above_since", None)  # type: ignore[var-annotated]


def render_feedback():
	current_rms: float = st.session_state.get("current_rms", 0.0)
	current_dbfs: float = st.session_state.get("current_dbfs", -math.inf)

	# Visual meter with color
	def render_meter(dbfs_value: float, target_dbfs_value: float):
		# Map dbfs_value to a 0..100 meter based on reasonable range [-60..0] dBFS
		clamped = max(-60.0, min(0.0, dbfs_value))
		percent = int(((clamped + 60.0) / 60.0) * 100.0)
		# Color logic
		if dbfs_value >= target_dbfs_value:
			color = "#22c55e"  # green
			label = "Đủ to"
		elif dbfs_value >= (target_dbfs_value - 10.0):
			color = "#eab308"  # yellow
			label = "Gần đạt"
		else:
			color = "#ef4444"  # red
			label = "Nhỏ"

		html = f'''
<div style="width:100%;max-width:640px;border:1px solid #e5e7eb;border-radius:8px;padding:8px;background:#f9fafb">
  <div style="display:flex;justify-content:space-between;font-size:12px;color:#6b7280;margin-bottom:6px;">
    <span>-60 dBFS</span>
    <span>Mục tiêu: {target_dbfs_value:.0f} dBFS</span>
    <span>0 dBFS</span>
  </div>
  <div style="position:relative;height:20px;background:#e5e7eb;border-radius:6px;overflow:hidden;">
    <div style="position:absolute;left:0;top:0;height:100%;width:{percent}%;background:{color};transition:width 120ms ease;"></div>
    <div style="position:absolute;left:{int(((target_dbfs_value + 60.0)/60.0)*100)}%;top:0;height:100%;width:2px;background:#111827;opacity:0.4"></div>
  </div>
  <div style="margin-top:6px;display:flex;justify-content:space-between;align-items:center;font-size:13px;color:#374151">
    <span>Âm lượng hiện tại: {dbfs_value:.1f} dBFS</span>
    <strong style="color:{color}">{label}</strong>
  </div>
</div>
'''
		meter_placeholder.markdown(html, unsafe_allow_html=True)

	render_meter(current_dbfs, target_dbfs)

	# Target check with simple timing window
	now_ts = float(time.time())  # seconds
	target_ok = current_dbfs >= target_dbfs
	above_since: Optional[float] = st.session_state.get("above_since", None)

	if target_ok:
		if above_since is None:
			above_since = now_ts
			st.session_state["above_since"] = above_since
	else:
		above_since = None
		st.session_state["above_since"] = None

	# Compose message
	header = f"{student_name}, "
	if target_ok and above_since is not None and (now_ts - above_since) >= float(grace_seconds):
		feedback_placeholder.success(header + msg_praise)
	else:
		feedback_placeholder.info(header + msg_encourage)

	# Numeric readout
	level_placeholder.write(
		f"RMS: {current_rms:.3f}  |  dBFS: {current_dbfs:.1f}  |  Mục tiêu: ≥ {target_dbfs} dBFS"
	)


st.subheader("🧭 Phản hồi")
info = st.info(
	("Mic realtime đang chạy. Nói vào micro và xem thanh mức âm lượng." if WEBRTC_AVAILABLE
	 else "Nhấn và giữ nút ghi âm hoặc tải WAV để phân tích.")
	+ " "
	"Khi đạt và duy trì mức mục tiêu, bạn sẽ nhận được lời khen."
)

# When a new recording is available, analyze it
if wav_audio_data is not None:
	try:
		arr, sr = wav_bytes_to_mono_array(wav_audio_data)
		rms, dbfs = compute_rms_and_dbfs(arr)
		st.session_state["current_rms"] = rms
		st.session_state["current_dbfs"] = dbfs
	except Exception as e:
		st.error(f"Lỗi xử lý âm thanh: {type(e).__name__}: {e}")

render_feedback()

# Keep UI responsive for realtime mic
if webrtc_ctx and webrtc_ctx.state.playing:
	st.experimental_rerun()


