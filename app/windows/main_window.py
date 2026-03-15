import os
import re
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QFrame, QGroupBox, QMessageBox,
    QCheckBox, QProgressBar, QListWidget, QInputDialog
)
from PySide6.QtCore import Qt, Slot, QSettings, QTimer

from app.constants import (
    AUDIO_FORMATS, CODEC_SAMPLE_FORMATS, CHANNEL_OPTIONS, detect_mux_container,
    VIDEO_CODEC_NAMES, VIDEO_CODEC_TOOLTIPS, AUDIO_CODEC_NAMES, AUDIO_CODEC_TOOLTIPS
)
from app.threads import (
    FetchThread, DownloadThread, CaptionDownloadThread, ConversionThread, MuxThread
)
from app.dialogs import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader")
        self.setGeometry(100, 100, 750, 500)

        self.settings = QSettings("YouTubeDownloader", "YouTubeDownloader")
        self.streams_objects = []
        self.video_streams = []
        self.audio_streams = []
        self.captions_data = []
        self.video_url = ""
        self.video_title = ""
        self.pending_audio_conversion = False
        self.last_downloaded_file = ""
        self.temp_video_path = ""
        self.temp_audio_path = ""

        menu_bar = self.menuBar()
        settings_menu = menu_bar.addMenu("Settings")
        settings_action = settings_menu.addAction("Preferences...")
        settings_action.triggered.connect(self.open_settings)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        url_frame = QFrame()
        url_layout = QHBoxLayout(url_frame)
        url_label = QLabel("YouTube URL:")
        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("Paste a YouTube URL here...")
        self.fetch_timer = QTimer()
        self.fetch_timer.setSingleShot(True)
        self.fetch_timer.setInterval(1000)
        self.fetch_timer.timeout.connect(self.fetch_video_info)
        self.url_entry.textChanged.connect(self.on_url_text_changed)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_entry)
        main_layout.addWidget(url_frame)

        self.use_oauth = QCheckBox("Use OAuth (required for some age-restricted videos)")
        main_layout.addWidget(self.use_oauth)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        main_layout.addWidget(self.error_label)

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.title_label.setWordWrap(True)
        main_layout.addWidget(self.title_label)

        options_group = QGroupBox("Download Options")
        options_layout = QVBoxLayout(options_group)

        self.audio_only_checkbox = QCheckBox("Audio Only")
        self.audio_only_checkbox.toggled.connect(self.toggle_audio_only)
        options_layout.addWidget(self.audio_only_checkbox)

        combos_layout = QHBoxLayout()

        self.res_label = QLabel("Resolution:")
        self.resolution_combo = QComboBox()
        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)
        res_layout = QVBoxLayout()
        res_layout.addWidget(self.res_label)
        res_layout.addWidget(self.resolution_combo)
        combos_layout.addLayout(res_layout)

        self.fmt_label = QLabel("Video Format:")
        self.video_format_combo = QComboBox()
        self.video_format_combo.currentIndexChanged.connect(self.update_format_tooltip)
        fmt_layout = QVBoxLayout()
        fmt_layout.addWidget(self.fmt_label)
        fmt_layout.addWidget(self.video_format_combo)
        combos_layout.addLayout(fmt_layout)

        audio_q_layout = QVBoxLayout()
        audio_q_layout.addWidget(QLabel("Audio Quality:"))
        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.currentIndexChanged.connect(self.update_audio_tooltip)
        audio_q_layout.addWidget(self.audio_quality_combo)
        combos_layout.addLayout(audio_q_layout)

        options_layout.addLayout(combos_layout)

        main_layout.addWidget(options_group)

        self.download_button = QPushButton("Download")
        self.download_button.setEnabled(False)
        self.download_button.setMinimumHeight(40)
        self.download_button.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.download_button.clicked.connect(self.start_download_workflow)
        main_layout.addWidget(self.download_button)

        transcripts_group = QGroupBox("Transcripts")
        transcripts_layout = QHBoxLayout(transcripts_group)
        self.transcripts_list = QListWidget()
        self.transcripts_list.setMaximumHeight(80)
        transcripts_layout.addWidget(self.transcripts_list)
        self.transcript_download_button = QPushButton("Download\nTranscript")
        self.transcript_download_button.setEnabled(False)
        self.transcript_download_button.setFixedWidth(90)
        self.transcript_download_button.clicked.connect(self.download_transcript)
        transcripts_layout.addWidget(self.transcript_download_button)
        main_layout.addWidget(transcripts_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Paste a YouTube URL above to get started.")
        main_layout.addWidget(self.status_label)

        self.transcripts_list.itemSelectionChanged.connect(
            lambda: self.transcript_download_button.setEnabled(
                bool(self.transcripts_list.selectedItems())
            )
        )

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def get_download_directory(self):
        download_dir = self.settings.value("download_directory", "")
        if not download_dir:
            QMessageBox.warning(
                self,
                "Download Folder Not Set",
                "You must select a download folder before downloading.\n\n"
                "Please go to Settings > Preferences and choose a download location."
            )
            return None
        return download_dir

    def on_url_text_changed(self, text):
        self.fetch_timer.stop()
        if text.strip():
            self.fetch_timer.start()

    def fetch_video_info(self):
        url = self.url_entry.text().strip()
        if not url:
            self.error_label.setText("Please enter a YouTube video URL.")
            return

        self.video_url = url
        self.status_label.setText("Fetching data...")
        self.error_label.clear()
        self.title_label.clear()
        self.resolution_combo.clear()
        self.video_format_combo.clear()
        self.audio_quality_combo.clear()
        self.transcripts_list.clear()
        self.download_button.setEnabled(False)
        self.url_entry.setEnabled(False)

        self.fetch_thread = FetchThread(url, use_oauth=self.use_oauth.isChecked())
        self.fetch_thread.finished.connect(self.update_info)
        self.fetch_thread.error.connect(self.show_error)
        self.fetch_thread.client_switched.connect(self.show_client_switch)
        self.fetch_thread.start()

    @Slot(str, str)
    def show_client_switch(self, original_client, new_client):
        self.status_label.setText(
            f"Client switched from {original_client} to {new_client} to fetch video data."
        )

    @Slot(list, list, list, str)
    def update_info(self, streams_info, captions_info, streams_objects, status):
        self.streams_objects = streams_objects
        self.captions_data = captions_info or []
        self.url_entry.setEnabled(True)

        if streams_objects:
            title = streams_objects[0].title
            self.video_title = title
            self.title_label.setText(title)
            self.setWindowTitle(f"YouTube Downloader - {title}")

        self.video_streams = [
            s for s in streams_objects
            if s.includes_video_track and s.is_adaptive
        ]
        self.audio_streams = [
            s for s in streams_objects
            if s.type == "audio" and not s.is_progressive
        ]

        self.populate_resolution_combo()
        self.populate_audio_quality_combo()

        self.transcripts_list.clear()
        for cap in self.captions_data:
            self.transcripts_list.addItem(f"{cap['name']} ({cap['code']})")

        self.download_button.setEnabled(True)
        self.status_label.setText(status)
        self.error_label.clear()

    def populate_resolution_combo(self):
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.clear()

        resolutions = {}
        for s in self.video_streams:
            res = s.resolution
            if res and res not in resolutions:
                fps = getattr(s, 'fps', 30)
                res_num = int(res.replace("p", "")) if res.replace("p", "").isdigit() else 0
                resolutions[res] = (res_num, fps)

        sorted_res = sorted(resolutions.keys(), key=lambda r: resolutions[r], reverse=True)
        for res in sorted_res:
            self.resolution_combo.addItem(res)

        self.resolution_combo.blockSignals(False)
        if sorted_res:
            self.on_resolution_changed()

    def on_resolution_changed(self):
        self.video_format_combo.clear()
        resolution = self.resolution_combo.currentText()
        if not resolution:
            return

        matching = [s for s in self.video_streams if s.resolution == resolution]
        matching.sort(key=lambda s: s.filesize_mb if s.filesize_mb else 0)

        for s in matching:
            raw_codec = s.video_codec.split(".")[0] if s.video_codec else ""
            codec_display = VIDEO_CODEC_NAMES.get(raw_codec, raw_codec or s.subtype)
            fps = getattr(s, 'fps', '')
            fps_str = f" {fps}fps" if fps and fps != 30 else ""
            bitrate = s.bitrate
            if bitrate and bitrate >= 1_000_000:
                br_str = f" {bitrate / 1_000_000:.1f} Mbps"
            elif bitrate:
                br_str = f" {bitrate // 1000} kbps"
            else:
                br_str = ""
            size = f"{s.filesize_mb:.1f} MB" if s.filesize_mb else "? MB"
            label = f"{s.subtype.upper()} ({codec_display}){fps_str}{br_str} - {size}"
            idx = self.video_format_combo.count()
            self.video_format_combo.addItem(label, userData=s.itag)
            tooltip = VIDEO_CODEC_TOOLTIPS.get(codec_display, "")
            if tooltip:
                self.video_format_combo.setItemData(idx, tooltip, Qt.ToolTipRole)

        self.update_format_tooltip(self.video_format_combo.currentIndex())

    def update_format_tooltip(self, index):
        if index >= 0:
            tooltip = self.video_format_combo.itemData(index, Qt.ToolTipRole)
            self.video_format_combo.setToolTip(tooltip or "")
        else:
            self.video_format_combo.setToolTip("")

    def update_audio_tooltip(self, index):
        if index >= 0:
            tooltip = self.audio_quality_combo.itemData(index, Qt.ToolTipRole)
            self.audio_quality_combo.setToolTip(tooltip or "")
        else:
            self.audio_quality_combo.setToolTip("")

    def populate_audio_quality_combo(self):
        self.audio_quality_combo.clear()

        sorted_audio = sorted(
            self.audio_streams,
            key=lambda s: int(s.abr.replace("kbps", "")) if s.abr else 0,
            reverse=True
        )

        for s in sorted_audio:
            raw_codec = s.audio_codec.split(".")[0] if s.audio_codec else ""
            codec_display = AUDIO_CODEC_NAMES.get(raw_codec, raw_codec or s.subtype)
            bitrate = s.abr or "?"
            size = f"{s.filesize_mb:.1f} MB" if s.filesize_mb else "? MB"
            label = f"{bitrate} - {s.subtype.upper()} ({codec_display}) - {size}"
            idx = self.audio_quality_combo.count()
            self.audio_quality_combo.addItem(label, userData=s.itag)
            tooltip = AUDIO_CODEC_TOOLTIPS.get(codec_display, "")
            if tooltip:
                self.audio_quality_combo.setItemData(idx, tooltip, Qt.ToolTipRole)

        self.update_audio_tooltip(self.audio_quality_combo.currentIndex())

    def toggle_audio_only(self, checked):
        self.res_label.setVisible(not checked)
        self.resolution_combo.setVisible(not checked)
        self.fmt_label.setVisible(not checked)
        self.video_format_combo.setVisible(not checked)

    def sanitize_filename(self, title):
        return re.sub(r'[\\/*?:"<>|]', "", title)

    def find_stream_by_itag(self, itag):
        return next((s for s in self.streams_objects if s.itag == itag), None)

    def get_best_audio_for_video(self, video_stream):
        v_subtype = video_stream.subtype.lower()

        preferred = []
        fallback = []
        for a in self.audio_streams:
            a_sub = a.subtype.lower()
            if v_subtype == "mp4" and a_sub == "mp4":
                preferred.append(a)
            elif v_subtype == "webm" and a_sub == "webm":
                preferred.append(a)
            else:
                fallback.append(a)

        candidates = preferred if preferred else fallback
        if not candidates:
            candidates = self.audio_streams

        candidates.sort(
            key=lambda s: int(s.abr.replace("kbps", "")) if s.abr else 0,
            reverse=True
        )
        return candidates[0] if candidates else None

    def start_download_workflow(self):
        download_dir = self.get_download_directory()
        if not download_dir:
            return

        self.error_label.clear()
        self.download_button.setEnabled(False)

        if self.audio_only_checkbox.isChecked():
            self.download_audio_only(download_dir)
        else:
            self.download_video_with_audio(download_dir)

    def download_audio_only(self, download_dir):
        itag = self.audio_quality_combo.currentData()
        if itag is None:
            self.error_label.setText("No audio stream selected.")
            self.download_button.setEnabled(True)
            return

        stream = self.find_stream_by_itag(itag)
        if not stream:
            self.error_label.setText("Could not find selected audio stream.")
            self.download_button.setEnabled(True)
            return

        base_title = self.sanitize_filename(self.video_title or "audio")
        bitrate = stream.abr or "unknown"
        filename = f"{base_title}_Audio_{bitrate}.{stream.subtype}"
        if len(filename) > 200:
            ext = f".{stream.subtype}"
            filename = f"{filename[:200 - len(ext)]}{ext}"

        self.pending_audio_conversion = self.should_convert_audio()
        self.status_label.setText(f"Downloading audio: {filename}")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Downloading: %p%")
        self.progress_bar.setVisible(True)

        self.download_thread = DownloadThread(
            stream=stream, output_path=download_dir, filename=filename
        )
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.completed.connect(self.audio_download_completed)
        self.download_thread.error.connect(self.download_error)
        self.download_thread.start()

    @Slot(str)
    def audio_download_completed(self, file_path):
        if self.pending_audio_conversion:
            self.pending_audio_conversion = False
            self.start_audio_conversion(file_path)
            return

        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Download completed: {file_path}")
        self.download_button.setEnabled(True)
        QMessageBox.information(self, "Download Complete", f"File saved to:\n{file_path}")

    def download_video_with_audio(self, download_dir):
        video_itag = self.video_format_combo.currentData()
        if video_itag is None:
            self.error_label.setText("No video stream selected.")
            self.download_button.setEnabled(True)
            return

        video_stream = self.find_stream_by_itag(video_itag)
        if not video_stream:
            self.error_label.setText("Could not find selected video stream.")
            self.download_button.setEnabled(True)
            return

        audio_stream = self.get_best_audio_for_video(video_stream)
        if not audio_stream:
            self.error_label.setText("No compatible audio stream found.")
            self.download_button.setEnabled(True)
            return

        base_title = self.sanitize_filename(self.video_title or "video")
        res = video_stream.resolution or "unknown"

        video_filename = f"{base_title}_video_temp.{video_stream.subtype}"
        audio_filename = f"{base_title}_audio_temp.{audio_stream.subtype}"

        self.temp_video_path = os.path.join(download_dir, video_filename)
        self.temp_audio_path = os.path.join(download_dir, audio_filename)

        container_fmt, container_ext = detect_mux_container(
            video_stream.video_codec, audio_stream.audio_codec
        )

        final_filename = f"{base_title}_{res}{container_ext}"
        if len(final_filename) > 200:
            final_filename = f"{final_filename[:200 - len(container_ext)]}{container_ext}"
        self.final_output_path = os.path.join(download_dir, final_filename)
        self.mux_container_format = container_fmt

        self.pending_audio_stream = audio_stream
        self.status_label.setText(f"Downloading video: {res}...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Downloading video: %p%")
        self.progress_bar.setVisible(True)

        self.download_thread = DownloadThread(
            stream=video_stream,
            output_path=download_dir,
            filename=video_filename
        )
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.completed.connect(self.video_download_completed)
        self.download_thread.error.connect(self.download_error)
        self.download_thread.start()

    @Slot(str)
    def video_download_completed(self, video_path):
        self.temp_video_path = video_path
        audio_stream = self.pending_audio_stream
        download_dir = os.path.dirname(video_path)
        audio_filename = os.path.basename(self.temp_audio_path)

        self.status_label.setText("Downloading audio...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Downloading audio: %p%")

        self.download_thread = DownloadThread(
            stream=audio_stream,
            output_path=download_dir,
            filename=audio_filename
        )
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.completed.connect(self.audio_for_mux_completed)
        self.download_thread.error.connect(self.download_error)
        self.download_thread.start()

    @Slot(str)
    def audio_for_mux_completed(self, audio_path):
        self.temp_audio_path = audio_path
        self.status_label.setText("Muxing video and audio...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Muxing: %p%")

        self.mux_thread = MuxThread(
            video_path=self.temp_video_path,
            audio_path=self.temp_audio_path,
            output_path=self.final_output_path,
            container_format=self.mux_container_format
        )
        self.mux_thread.progress.connect(self.update_progress)
        self.mux_thread.completed.connect(self.mux_completed)
        self.mux_thread.error.connect(self.mux_error)
        self.mux_thread.start()

    @Slot(str)
    def mux_completed(self, output_path):
        self.cleanup_temp_files()
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Download completed: {output_path}")
        self.download_button.setEnabled(True)
        QMessageBox.information(self, "Download Complete", f"File saved to:\n{output_path}")

    @Slot(str)
    def mux_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.error_label.setText(f"Muxing Error: {error_message}")
        self.status_label.setText("Muxing failed. Temporary files were kept.")
        self.download_button.setEnabled(True)
        QMessageBox.critical(self, "Muxing Error",
                             f"Failed to combine video and audio:\n{error_message}\n\n"
                             f"Temporary files kept at:\n{self.temp_video_path}\n{self.temp_audio_path}")

    def cleanup_temp_files(self):
        for path in [self.temp_video_path, self.temp_audio_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def should_convert_audio(self):
        mode = self.settings.value("conversion_mode", "No Conversion")
        return mode != "No Conversion"

    def start_audio_conversion(self, input_path):
        fmt_name = self.settings.value("conversion_format", "MP3")
        fmt_config = AUDIO_FORMATS.get(fmt_name, AUDIO_FORMATS["MP3"])

        bitrate_str = self.settings.value("conversion_bitrate", "192")
        bitrate = int(bitrate_str) * 1000

        sample_rate = int(self.settings.value("conversion_sample_rate", "44100"))

        channel_name = self.settings.value("conversion_channels", "Stereo")
        channels = CHANNEL_OPTIONS.get(channel_name, 2)

        base, _ = os.path.splitext(input_path)
        output_path = f"{base}.{fmt_config['extension']}"

        codec = fmt_config["codec"]
        sample_format = CODEC_SAMPLE_FORMATS.get(codec, "fltp")

        self.last_downloaded_file = input_path
        self.status_label.setText(f"Converting to {fmt_name}...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Converting: %p%")
        self.progress_bar.setVisible(True)

        self.conversion_thread = ConversionThread(
            input_path=input_path,
            output_path=output_path,
            codec=codec,
            container=fmt_config["container"],
            sample_format=sample_format,
            bitrate=bitrate if fmt_config["lossy"] else None,
            sample_rate=sample_rate,
            channels=channels
        )
        self.conversion_thread.progress.connect(self.update_progress)
        self.conversion_thread.completed.connect(self.conversion_completed)
        self.conversion_thread.error.connect(self.conversion_error)
        self.conversion_thread.start()

    @Slot(str)
    def conversion_completed(self, converted_path):
        mode = self.settings.value("conversion_mode", "No Conversion")
        original = self.last_downloaded_file

        if mode == "Convert and Delete Original" and os.path.exists(original):
            os.remove(original)

        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Conversion completed: {converted_path}")
        self.download_button.setEnabled(True)

        if mode == "Convert and Delete Original":
            QMessageBox.information(
                self, "Download & Conversion Complete",
                f"Converted file saved to:\n{converted_path}\n\nOriginal file was deleted."
            )
        else:
            QMessageBox.information(
                self, "Download & Conversion Complete",
                f"Converted file saved to:\n{converted_path}\n\nOriginal file kept at:\n{original}"
            )

    @Slot(str)
    def conversion_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.error_label.setText(f"Conversion Error: {error_message}")
        self.status_label.setText("Conversion failed. Original file was kept.")
        self.download_button.setEnabled(True)
        QMessageBox.critical(self, "Conversion Error",
                             f"Audio conversion failed:\n{error_message}\n\nThe original downloaded file was kept.")

    def download_transcript(self):
        download_dir = self.get_download_directory()
        if not download_dir:
            return

        selected = self.transcripts_list.selectedItems()
        if not selected:
            return

        idx = self.transcripts_list.row(selected[0])
        cap = self.captions_data[idx]
        cap_code = cap["code"]

        fmt, ok = QInputDialog.getItem(
            self, "Choose Transcript Format", "Select format:",
            ["srt", "txt"], 0, False
        )
        if not ok:
            return

        base_title = self.sanitize_filename(self.video_title or "YouTube")
        auto = cap_code.startswith("a.")
        lang = cap_code.split(".", 1)[-1] if auto else cap_code
        descriptor = "AutoTranscript" if auto else "Transcript"
        proposed = f"{base_title}_{descriptor}_{lang}.{fmt}"
        if len(proposed) > 200:
            ext = f".{fmt}"
            proposed = f"{proposed[:200 - len(ext)]}{ext}"

        confirmed, ok2 = QInputDialog.getText(
            self, "Confirm Filename",
            f"Filename will be:\n{proposed}\nDo you want to proceed?",
            text=proposed
        )
        if not ok2:
            return
        final = confirmed or proposed
        if not final.lower().endswith(f".{fmt}"):
            final += f".{fmt}"

        out_path = os.path.join(download_dir, final)
        self.status_label.setText(f"Downloading transcript: {final}")
        self.error_label.clear()
        self.transcript_download_button.setEnabled(False)

        self.caption_thread = CaptionDownloadThread(
            url=self.video_url,
            caption_code=cap_code,
            out_filename=out_path,
            fmt=fmt,
            use_oauth=self.use_oauth.isChecked()
        )
        self.caption_thread.completed.connect(self.transcript_download_completed)
        self.caption_thread.error.connect(self.transcript_download_error)
        self.caption_thread.start()

    @Slot(str)
    def transcript_download_completed(self, file_path):
        self.status_label.setText(f"Transcript saved: {file_path}")
        self.transcript_download_button.setEnabled(True)
        QMessageBox.information(self, "Transcript Downloaded", f"File saved to:\n{file_path}")

    @Slot(str)
    def transcript_download_error(self, error_message):
        self.error_label.setText(f"Error: {error_message}")
        self.status_label.setText("Transcript download failed.")
        self.transcript_download_button.setEnabled(True)

    @Slot(int)
    def update_progress(self, value):
        self.progress_bar.setValue(value)

    @Slot(str)
    def download_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.pending_audio_conversion = False
        self.error_label.setText(f"Error: {error_message}")
        self.status_label.setText("Download failed.")
        self.download_button.setEnabled(True)
        QMessageBox.critical(self, "Download Error", error_message)

    def show_error(self, error):
        self.error_label.setText(f"Error: {error}")
        self.status_label.setText("Failed to fetch data.")
        self.url_entry.setEnabled(True)
