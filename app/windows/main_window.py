import os
import re
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QFrame, QGroupBox, QMessageBox,
    QCheckBox, QTreeWidget, QTreeWidgetItem, QHeaderView, QInputDialog,
    QProgressBar
)
from PySide6.QtCore import Qt, Slot, QSettings

from app.constants import AUDIO_FORMATS, CODEC_SAMPLE_FORMATS, CHANNEL_OPTIONS
from app.threads import FetchThread, DownloadThread, CaptionDownloadThread, ConversionThread
from app.dialogs import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Video Info")
        self.setGeometry(100, 100, 1200, 900)

        self.settings = QSettings("YouTubeDownloader", "YouTubeDownloader")
        self.streams_objects = []
        self.video_url = ""
        self.video_title = ""
        self.captions_data = []
        self.pending_audio_conversion = False
        self.last_downloaded_file = ""

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
        fetch_button = QPushButton("Fetch Info")
        fetch_button.clicked.connect(self.fetch_video_info)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_entry)
        url_layout.addWidget(fetch_button)
        main_layout.addWidget(url_frame)

        self.use_oauth = QCheckBox("Use OAuth (required for some age-restricted videos)")
        main_layout.addWidget(self.use_oauth)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        main_layout.addWidget(self.error_label)

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(self.title_label)

        streams_group = QGroupBox("Available Streams")
        streams_layout = QVBoxLayout(streams_group)

        self.streams_tree = QTreeWidget()
        self.streams_tree.setHeaderLabels([
            "Stream Type",
            "Resolution",
            "FPS",
            "Format",
            "Filesize",
            "Audio",
            "Video",
            "Adaptive",
            "Progressive",
            "Bitrate",
            "Codecs"
        ])

        header = self.streams_tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        self.streams_tree.setAlternatingRowColors(True)
        self.streams_tree.setSortingEnabled(True)

        streams_layout.addWidget(self.streams_tree)

        self.download_button = QPushButton("Download Selected Stream")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download_selected_stream)
        streams_layout.addWidget(self.download_button)

        captions_group = QGroupBox("Available Captions")
        captions_layout = QVBoxLayout(captions_group)
        self.captions_listbox = QListWidget()
        captions_layout.addWidget(self.captions_listbox)

        info_layout = QVBoxLayout()
        info_layout.addWidget(streams_group, stretch=4)
        info_layout.addWidget(captions_group, stretch=1)
        main_layout.addLayout(info_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Enter a YouTube URL and click Fetch Info to see available streams and captions.")
        main_layout.addWidget(self.status_label)

        self.streams_tree.itemSelectionChanged.connect(self.update_download_button_state)

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

    def fetch_video_info(self):
        url = self.url_entry.text().strip()
        if not url:
            self.error_label.setText("Please enter a YouTube video URL.")
            return

        self.video_url = url
        self.status_label.setText("Fetching data...")
        self.error_label.clear()
        self.title_label.clear()
        self.streams_tree.clear()
        self.captions_listbox.clear()
        self.download_button.setEnabled(False)

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

        if streams_objects:
            title = streams_objects[0].title
            self.video_title = title
            self.title_label.setText(title)
            self.setWindowTitle(f"YouTube Video Info - {title}")

        self.streams_tree.clear()

        video_parent = QTreeWidgetItem(["Video Streams"])
        audio_parent = QTreeWidgetItem(["Audio Streams"])
        transcripts_parent = QTreeWidgetItem(["Transcripts"])
        self.streams_tree.addTopLevelItem(video_parent)
        self.streams_tree.addTopLevelItem(audio_parent)
        self.streams_tree.addTopLevelItem(transcripts_parent)

        for stream in streams_objects:
            parent = video_parent if stream.type == 'video' else audio_parent
            item = QTreeWidgetItem(parent)
            item.setText(0, f"Itag: {stream.itag}")
            item.setText(1, str(getattr(stream, 'resolution', 'N/A')))
            item.setText(2, str(getattr(stream, 'fps', 'N/A')))
            item.setText(3, stream.mime_type)
            item.setText(4, f"{stream.filesize_mb:.2f} MB")
            item.setText(5, "Yes" if stream.includes_audio_track else "No")
            item.setText(6, "Yes" if stream.includes_video_track else "No")
            item.setText(7, "Yes" if stream.is_adaptive else "No")
            item.setText(8, "Yes" if stream.is_progressive else "No")
            bitrate = stream.abr if stream.includes_audio_track else "N/A"
            item.setText(9, bitrate)
            audio_codec, video_codec = stream.parse_codecs()
            codecs = f"Audio: {audio_codec or 'N/A'}, Video: {video_codec or 'N/A'}"
            item.setText(10, codecs)
            tooltip = (
                f"Itag: {stream.itag}\n"
                f"Type: {stream.type}\n"
                f"Resolution: {getattr(stream, 'resolution', 'N/A')}\n"
                f"FPS: {getattr(stream, 'fps', 'N/A')}\n"
                f"Mime Type: {stream.mime_type}\n"
                f"Filesize: {stream.filesize_mb:.2f} MB\n"
                f"Adaptive: {'Yes' if stream.is_adaptive else 'No'}\n"
                f"Progressive: {'Yes' if stream.is_progressive else 'No'}\n"
                f"Audio: {'Yes' if stream.includes_audio_track else 'No'}\n"
                f"Video: {'Yes' if stream.includes_video_track else 'No'}\n"
                f"Bitrate: {bitrate}\n"
                f"Codecs: {codecs}"
            )
            item.setToolTip(0, tooltip)

        for cap in self.captions_data:
            code = cap.get("code", "")
            name = cap.get("name", "")
            cap_item = QTreeWidgetItem(transcripts_parent)
            cap_item.setText(0, f"Caption: {code}")
            cap_item.setText(1, name or "Unknown")
            cap_item.setText(3, "text/plain or srt")
            cap_item.setText(10, f"Name: {name} | Code: {code}")
            cap_item.setToolTip(0, f"Caption track\nName: {name}\nCode: {code}\nTip: Select and click Download to save SRT or TXT.")

        self.streams_tree.expandAll()

        self.captions_listbox.clear()
        if self.captions_data:
            self.captions_listbox.addItems([f"{c['name']} ({c['code']})" for c in self.captions_data])

        self.status_label.setText(status)
        self.error_label.clear()

    def update_download_button_state(self):
        selected_items = self.streams_tree.selectedItems()
        self.download_button.setEnabled(bool(selected_items))

    def get_selected_stream(self):
        selected_items = self.streams_tree.selectedItems()
        if not selected_items:
            raise ValueError("Please select a stream to download.")
        selected_item = selected_items[0]
        itag_text = selected_item.text(0)
        try:
            itag = int(itag_text.split(": ")[1])
        except (IndexError, ValueError):
            raise ValueError("Invalid stream selection.")
        selected_stream = next(
            (stream for stream in self.streams_objects if stream.itag == itag),
            None
        )
        if not selected_stream:
            raise ValueError("Error: Could not find selected stream.")
        return selected_stream

    def construct_filename(self, stream):
        stream_type = "Audio" if stream.type == "audio" else "Video"
        format_subtype = stream.subtype
        bitrate = stream.abr if stream.includes_audio_track and stream.abr else "N/A"
        resolution = stream.resolution if stream.includes_video_track and stream.resolution else "N/A"
        base_title = re.sub(r'[\\/*?:"<>|]', "", stream.title)
        filename_parts = [base_title, stream_type, format_subtype]
        if bitrate != "N/A":
            bitrate_str = bitrate if bitrate.lower().endswith("kbps") else f"{bitrate}kbps"
            filename_parts.append(bitrate_str)
        if resolution != "N/A":
            filename_parts.append(resolution)
        custom_filename = "_".join(filename_parts)
        file_extension = format_subtype
        custom_filename_with_ext = f"{custom_filename}.{file_extension}"
        max_length = 200
        if len(custom_filename_with_ext) > max_length:
            extension = f".{file_extension}"
            custom_filename_with_ext = f"{custom_filename_with_ext[:max_length - len(extension)]}{extension}"
        return custom_filename_with_ext, file_extension

    def get_confirmed_filename(self, proposed_filename, file_extension):
        confirmed_filename, ok = QInputDialog.getText(
            self,
            "Confirm Filename",
            f"Filename will be:\n{proposed_filename}\nDo you want to proceed?",
            text=proposed_filename
        )
        if not ok:
            raise ValueError("Download canceled by the user.")
        if confirmed_filename and not confirmed_filename.lower().endswith(f".{file_extension}"):
            confirmed_filename += f".{file_extension}"
        return confirmed_filename or proposed_filename

    def is_audio_only_stream(self, stream):
        return stream.type == "audio" and not stream.is_progressive

    def should_convert_audio(self):
        mode = self.settings.value("conversion_mode", "No Conversion")
        return mode != "No Conversion"

    def start_download(self, stream, filename):
        download_dir = self.get_download_directory()
        if not download_dir:
            self.download_button.setEnabled(True)
            return
        self.pending_audio_conversion = self.is_audio_only_stream(stream) and self.should_convert_audio()
        self.status_label.setText(f"Downloading: {filename}")
        self.error_label.clear()
        self.download_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Downloading: %p%")
        self.progress_bar.setVisible(True)
        self.download_thread = DownloadThread(
            stream=stream,
            output_path=download_dir,
            filename=filename
        )
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.completed.connect(self.download_completed)
        self.download_thread.error.connect(self.download_error)
        self.download_thread.start()

    def handle_download_error(self, error_message):
        self.error_label.setText(f"Error: {error_message}")
        self.status_label.setText("Download failed.")
        self.download_button.setEnabled(True)
        QMessageBox.critical(self, "Download Error", error_message)

    def get_selected_caption_code(self):
        selected_items = self.streams_tree.selectedItems()
        if not selected_items:
            raise ValueError("Please select a transcript to download.")
        selected_item = selected_items[0]
        t0 = selected_item.text(0)
        if not t0.startswith("Caption: "):
            raise ValueError("Please select a transcript (under the Transcripts category).")
        return t0.split("Caption: ", 1)[1].strip()

    def construct_caption_filename(self, caption_code, fmt):
        base_title = re.sub(r'[\\/*?:"<>|]', "", self.video_title or "YouTube")
        fmt = fmt.lower()
        auto = caption_code.startswith("a.")
        lang = caption_code.split(".", 1)[-1] if auto else caption_code
        descriptor = "AutoTranscript" if auto else "Transcript"
        proposed = f"{base_title}_{descriptor}_{lang}.{fmt}"
        max_length = 200
        if len(proposed) > max_length:
            ext = f".{fmt}"
            proposed = f"{proposed[:max_length - len(ext)]}{ext}"
        return proposed

    def download_selected_stream(self):
        try:
            selected_items = self.streams_tree.selectedItems()
            if not selected_items:
                raise ValueError("Please select a stream or transcript to download.")
            t0 = selected_items[0].text(0)
            if t0.startswith("Itag: "):
                selected_stream = self.get_selected_stream()
                proposed_filename, file_extension = self.construct_filename(selected_stream)
                final_filename = self.get_confirmed_filename(proposed_filename, file_extension)
                self.start_download(selected_stream, final_filename)
                return
            if t0.startswith("Caption: "):
                download_dir = self.get_download_directory()
                if not download_dir:
                    return
                cap_code = self.get_selected_caption_code()
                fmt, ok = QInputDialog.getItem(
                    self,
                    "Choose Transcript Format",
                    "Select format:",
                    ["srt", "txt"],
                    0,
                    False
                )
                if not ok:
                    raise ValueError("Download canceled by the user.")
                proposed = self.construct_caption_filename(cap_code, fmt)
                confirmed, ok2 = QInputDialog.getText(
                    self,
                    "Confirm Filename",
                    f"Filename will be:\n{proposed}\nDo you want to proceed?",
                    text=proposed
                )
                if not ok2:
                    raise ValueError("Download canceled by the user.")
                final = confirmed or proposed
                if not final.lower().endswith(f".{fmt}"):
                    final += f".{fmt}"
                out_path = os.path.join(download_dir, final)
                self.status_label.setText(f"Starting transcript download as: {final}")
                self.error_label.clear()
                self.download_button.setEnabled(False)
                self.caption_thread = CaptionDownloadThread(
                    url=self.video_url,
                    caption_code=cap_code,
                    out_filename=out_path,
                    fmt=fmt,
                    use_oauth=self.use_oauth.isChecked()
                )
                self.caption_thread.completed.connect(self.download_completed)
                self.caption_thread.error.connect(self.download_error)
                self.caption_thread.start()
                return
            raise ValueError("Invalid selection. Pick a Video, Audio, or Caption item.")
        except ValueError as ve:
            self.error_label.setText(f"Error: {str(ve)}")
            self.status_label.setText("Download failed.")
        except Exception as e:
            self.handle_download_error(str(e))

    @Slot(int)
    def update_progress(self, value):
        self.progress_bar.setValue(value)

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
    def download_completed(self, file_path):
        if self.pending_audio_conversion:
            self.pending_audio_conversion = False
            self.start_audio_conversion(file_path)
            return

        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Download completed: {file_path}")
        self.download_button.setEnabled(True)
        QMessageBox.information(self, "Download Complete", f"File saved to:\n{file_path}")

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
