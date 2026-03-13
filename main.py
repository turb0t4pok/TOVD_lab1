import cv2
import os
import time
import tempfile
import subprocess
import tkinter as tk
from tkinter import filedialog
import pygame

WINDOW_NAME = "Original | Processed"

FFMPEG_EXE = "ffmpeg"


def choose_mode():
    print("\nВыберите режим обработки кадра:")
    print("1 - оттенки серого")
    print("2 - сглаживание (Gaussian Blur)")

    while True:
        choice = input("Введите номер режима (1/2): ").strip()
        if choice == "1":
            return "gray"
        elif choice == "2":
            return "blur"
        else:
            print("Неверный ввод. Введите 1 или 2.")


def choose_video_file():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    file_path = filedialog.askopenfilename(
        title="Выберите видеофайл",
        filetypes=[
            ("Video files", "*.mp4 *.avi *.mov *.mkv *.webm"),
            ("All files", "*.*")
        ]
    )

    root.destroy()
    return file_path


def preprocess_frame(frame, mode):
    if mode == "gray":
        processed = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)

    if mode == "blur":
        return cv2.GaussianBlur(frame, (9, 9), 0)

    return frame


def is_window_closed(window_name):
    try:
        return cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def ask_restart():
    print("\nЧто сделать дальше?")
    print("1 - выбрать другой режим/видео")
    print("0 - выйти из программы")

    while True:
        choice = input("Введите 1 или 0: ").strip()
        if choice == "1":
            return True
        if choice == "0":
            return False
        print("Неверный ввод. Введите 1 или 0.")


def extract_audio_to_wav(video_path):
    temp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(temp_dir, "temp_audio.wav")

    cmd = [
        FFMPEG_EXE,
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        audio_path
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.exists(audio_path):
        return None

    return audio_path


def stop_audio():
    try:
        pygame.mixer.music.stop()
    except:
        pass


def run_video(mode, video_path):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("Ошибка: не удалось открыть видеофайл.")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 25.0

    print(f"\nВыбранный файл: {video_path}")
    print(f"Режим обработки: {mode}")
    print(f"Общее количество кадров: {total_frames}")
    print(f"Частота кадров (FPS): {fps:.2f}")
    print("Нажми Q, Esc или закрой окно крестиком.\n")

    frame_duration = 1.0 / fps

    audio_path = extract_audio_to_wav(video_path)
    audio_enabled = False

    if audio_path:
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            audio_enabled = True
            print("Аудио успешно запущено.")
        except Exception as e:
            print(f"Не удалось воспроизвести аудио: {e}")
    else:
        print("Аудиодорожка не найдена или не удалось извлечь звук.")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    frame_number = 0
    start_time = time.perf_counter()

    while True:
        if is_window_closed(WINDOW_NAME):
            print("Окно закрыто пользователем.")
            break

        ret, frame = cap.read()
        if not ret:
            print("Конец видео или ошибка чтения кадра.")
            break

        frame_number += 1
        processed = preprocess_frame(frame, mode)
        combined = cv2.hconcat([frame, processed])

        cv2.putText(
            combined,
            f"Frame: {frame_number}/{total_frames} | FPS: {fps:.2f} | Mode: {mode}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        print(f"Текущий кадр: {frame_number}, Всего кадров: {total_frames}, FPS: {fps:.2f}")

        cv2.imshow(WINDOW_NAME, combined)

        expected_time = frame_number * frame_duration
        elapsed = time.perf_counter() - start_time
        remaining = expected_time - elapsed
        delay_ms = max(1, int(remaining * 1000))

        key = cv2.waitKey(delay_ms) & 0xFF

        if key == 27 or key == ord('q') or key == ord('Q'):
            print("Выход из просмотра по команде пользователя.")
            break

        if is_window_closed(WINDOW_NAME):
            print("Окно закрыто пользователем.")
            break

    cap.release()
    cv2.destroyAllWindows()
    stop_audio()

    if audio_enabled:
        try:
            pygame.mixer.quit()
        except:
            pass


def main():
    while True:
        mode = choose_mode()
        video_path = choose_video_file()

        if not video_path:
            print("Файл не выбран.")
            if ask_restart():
                continue
            print("Программа завершена.")
            break

        if not os.path.exists(video_path):
            print("Ошибка: файл не найден.")
            if ask_restart():
                continue
            print("Программа завершена.")
            break

        run_video(mode, video_path)

        if ask_restart():
            continue
        print("Программа завершена.")
        break


if __name__ == "__main__":
    main()