import sys
import os
import time
import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QFileDialog,
    QComboBox,
    QSlider,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QMessageBox,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class VideoProcessorApp(QWidget):
    frame_ready = Signal(np.ndarray, np.ndarray, int, int)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Обработка видеоданных")
        self.resize(1400, 850)

        self.video_path = None
        self.cap = None
        self.total_frames = 0
        self.video_fps = 25.0
        self.duration_ms = 0

        self.is_playing = False
        self.slider_is_pressed = False
        self.last_frame_time = time.perf_counter()
        self.display_fps = 0.0

        self.audio_output = QAudioOutput()
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_video_frame)

        self.init_ui()

        self.frame_ready.connect(self.update_labels_with_frames)
        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)

    def init_ui(self):
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.original_label = QLabel("Исходный кадр")
        self.original_label.setAlignment(Qt.AlignCenter)
        self.original_label.setMinimumSize(600, 320)
        self.original_label.setStyleSheet("""
            QLabel {
                background-color: #202020;
                color: white;
                border: 1px solid #444;
                font-size: 18px;
            }
        """)

        original_box = QGroupBox("Исходное видео")
        original_layout = QVBoxLayout()
        original_layout.addWidget(self.original_label)
        original_box.setLayout(original_layout)

        self.processed_label = QLabel("Обработанный кадр")
        self.processed_label.setAlignment(Qt.AlignCenter)
        self.processed_label.setMinimumSize(600, 320)
        self.processed_label.setStyleSheet("""
            QLabel {
                background-color: #202020;
                color: white;
                border: 1px solid #444;
                font-size: 18px;
            }
        """)

        processed_box = QGroupBox("Обработанное видео")
        processed_layout = QVBoxLayout()
        processed_layout.addWidget(self.processed_label)
        processed_box.setLayout(processed_layout)

        info_box = QGroupBox("Информация о видео")
        info_layout = QVBoxLayout()

        self.file_label = QLabel("Файл: не выбран")
        self.frame_label = QLabel("Текущий кадр: 0")
        self.total_label = QLabel("Всего кадров: 0")
        self.fps_label = QLabel("Частота кадров: 0.00")
        self.mode_info_label = QLabel("Режим обработки: -")
        self.time_label = QLabel("Время: 00:00 / 00:00")

        for lbl in [
            self.file_label,
            self.frame_label,
            self.total_label,
            self.fps_label,
            self.mode_info_label,
            self.time_label,
        ]:
            lbl.setStyleSheet("font-size: 16px; padding: 4px;")

        info_layout.addWidget(self.file_label)
        info_layout.addWidget(self.frame_label)
        info_layout.addWidget(self.total_label)
        info_layout.addWidget(self.fps_label)
        info_layout.addWidget(self.mode_info_label)
        info_layout.addWidget(self.time_label)
        info_layout.addStretch()

        info_box.setLayout(info_layout)

        controls_box = QGroupBox("Управление")
        controls_layout = QVBoxLayout()

        top_controls = QHBoxLayout()

        self.open_button = QPushButton("Выбрать видео")
        self.open_button.clicked.connect(self.open_video_file)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Оттенки серого", "gray")
        self.mode_combo.addItem("Сглаживание (Gaussian Blur)", "blur")
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)

        top_controls.addWidget(self.open_button)
        top_controls.addWidget(self.mode_combo)

        middle_controls = QHBoxLayout()

        self.play_pause_button = QPushButton("▶ Воспроизвести")
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.play_pause_button.setEnabled(False)

        self.stop_button = QPushButton("■ Стоп")
        self.stop_button.clicked.connect(self.stop_video)
        self.stop_button.setEnabled(False)

        middle_controls.addWidget(self.play_pause_button)
        middle_controls.addWidget(self.stop_button)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setEnabled(False)
        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)
        self.slider.sliderMoved.connect(self.on_slider_moved)

        controls_layout.addLayout(top_controls)
        controls_layout.addSpacing(10)
        controls_layout.addLayout(middle_controls)
        controls_layout.addSpacing(14)
        controls_layout.addWidget(self.slider)
        controls_layout.addStretch()

        controls_box.setLayout(controls_layout)

        main_layout.addWidget(original_box, 0, 0)
        main_layout.addWidget(processed_box, 0, 1)
        main_layout.addWidget(info_box, 1, 0)
        main_layout.addWidget(controls_box, 1, 1)

        self.setLayout(main_layout)

    def open_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите видеофайл",
            "",
            "Видео (*.mp4 *.avi *.mov *.mkv *.webm);;Все файлы (*.*)"
        )

        if not file_path:
            return

        self.load_video(file_path)

    def load_video(self, file_path):
        self.stop_video()

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self.video_path = file_path
        self.cap = cv2.VideoCapture(file_path)

        if not self.cap.isOpened():
            QMessageBox.critical(self, "Ошибка", "Не удалось открыть видеофайл.")
            return

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.video_fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        if self.video_fps <= 0:
            self.video_fps = 25.0

        self.duration_ms = int((self.total_frames / self.video_fps) * 1000) if self.total_frames > 0 else 0

        self.slider.setEnabled(True)
        self.slider.setRange(0, max(0, self.duration_ms))

        self.media_player.setSource(QUrl.fromLocalFile(file_path))

        self.play_pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.play_pause_button.setText("▶ Воспроизвести")

        self.file_label.setText(f"Файл: {os.path.basename(file_path)}")
        self.frame_label.setText("Текущий кадр: 0")
        self.total_label.setText(f"Всего кадров: {self.total_frames}")
        self.fps_label.setText(f"Частота кадров: {self.video_fps:.2f}")
        self.mode_info_label.setText(f"Режим обработки: {self.mode_combo.currentText()}")
        self.time_label.setText(f"Время: 00:00 / {self.ms_to_mmss(self.duration_ms)}")

        self.show_frame_by_position(0)

    def stop_video(self):
        self.is_playing = False
        self.timer.stop()
        self.media_player.stop()

        self.play_pause_button.setText("▶ Воспроизвести")

        if self.cap is not None and self.video_path:
            self.show_frame_by_position(0)
            self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(False)

    def toggle_play_pause(self):
        if not self.video_path or self.cap is None:
            return

        if self.is_playing:
            self.pause_video()
        else:
            self.play_video()

    def play_video(self):
        if not self.video_path or self.cap is None:
            return

        self.is_playing = True
        self.play_pause_button.setText("⏸ Пауза")
        self.media_player.play()

        interval = max(1, int(1000 / self.video_fps))
        self.last_frame_time = time.perf_counter()
        self.timer.start(interval)

    def pause_video(self):
        self.is_playing = False
        self.play_pause_button.setText("▶ Воспроизвести")
        self.timer.stop()
        self.media_player.pause()

    def on_mode_changed(self):
        self.mode_info_label.setText(f"Режим обработки: {self.mode_combo.currentText()}")
        if self.video_path:
            current_pos = self.slider.value()
            self.show_frame_by_position(current_pos)

    def on_position_changed(self, position):
        if not self.slider_is_pressed:
            self.slider.blockSignals(True)
            self.slider.setValue(position)
            self.slider.blockSignals(False)

        total = self.media_player.duration() if self.media_player.duration() > 0 else self.duration_ms
        self.time_label.setText(f"Время: {self.ms_to_mmss(position)} / {self.ms_to_mmss(total)}")

    def on_duration_changed(self, duration):
        if duration > 0:
            self.duration_ms = duration
            self.slider.setRange(0, duration)
            self.time_label.setText(f"Время: 00:00 / {self.ms_to_mmss(duration)}")

    def on_playback_state_changed(self, state):
        if self.media_player.position() >= self.duration_ms and self.duration_ms > 0:
            self.pause_video()

    def on_slider_pressed(self):
        self.slider_is_pressed = True

    def on_slider_moved(self, value):
        self.time_label.setText(f"Время: {self.ms_to_mmss(value)} / {self.ms_to_mmss(self.duration_ms)}")
        self.show_frame_by_position(value)

    def on_slider_released(self):
        self.slider_is_pressed = False
        value = self.slider.value()

        self.media_player.setPosition(value)
        self.show_frame_by_position(value)

    def update_video_frame(self):
        if not self.video_path or self.cap is None:
            return

        position_ms = self.media_player.position()

        if position_ms >= self.duration_ms and self.duration_ms > 0:
            self.pause_video()
            return

        self.show_frame_by_position(position_ms)

    def show_frame_by_position(self, position_ms):
        if self.cap is None or self.total_frames <= 0:
            return

        frame_index = int((position_ms / 1000.0) * self.video_fps)

        if frame_index < 0:
            frame_index = 0
        if frame_index >= self.total_frames:
            frame_index = self.total_frames - 1

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = self.cap.read()

        if not ret or frame is None:
            return

        processed = self.preprocess_frame(frame)

        now = time.perf_counter()
        delta = now - self.last_frame_time
        if delta > 0:
            self.display_fps = 1.0 / delta
        self.last_frame_time = now

        self.frame_ready.emit(frame, processed, frame_index + 1, self.total_frames)

    def preprocess_frame(self, frame):
        mode = self.mode_combo.currentData()

        if mode == "gray":
            processed = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
            return processed

        if mode == "blur":
            return cv2.GaussianBlur(frame, (9, 9), 0)

        return frame

    def update_labels_with_frames(self, original_frame, processed_frame, current_frame, total_frames):
        self.set_image_to_label(self.original_label, original_frame)
        self.set_image_to_label(self.processed_label, processed_frame)

        self.frame_label.setText(f"Текущий кадр: {current_frame}")
        self.total_label.setText(f"Всего кадров: {total_frames}")
        self.fps_label.setText(f"Частота кадров: {self.video_fps:.2f}")

    def set_image_to_label(self, label, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w

        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        scaled = pixmap.scaled(
            label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.video_path and self.cap is not None:
            current_pos = self.slider.value()
            self.show_frame_by_position(current_pos)

    @staticmethod
    def ms_to_mmss(ms):
        total_seconds = max(0, ms // 1000)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def closeEvent(self, event):
        try:
            self.timer.stop()
            self.media_player.stop()
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = VideoProcessorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()