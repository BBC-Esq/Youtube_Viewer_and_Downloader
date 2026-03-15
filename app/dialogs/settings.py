import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QPushButton, QComboBox, QFileDialog, QMessageBox
)
from PySide6.QtCore import QSettings

from app.constants import AUDIO_FORMATS, BITRATE_OPTIONS, SAMPLE_RATE_OPTIONS, CHANNEL_OPTIONS


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(550)

        self.settings = QSettings("YouTubeDownloader", "YouTubeDownloader")

        layout = QVBoxLayout(self)

        download_group = QGroupBox("Download Location")
        download_layout = QHBoxLayout(download_group)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("No download folder selected")
        current_path = self.settings.value("download_directory", "")
        if current_path:
            self.path_edit.setText(current_path)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_folder)

        download_layout.addWidget(self.path_edit)
        download_layout.addWidget(browse_button)

        layout.addWidget(download_group)

        conversion_group = QGroupBox("Audio Conversion")
        conversion_layout = QFormLayout(conversion_group)

        self.conversion_mode = QComboBox()
        self.conversion_mode.addItems([
            "No Conversion",
            "Convert and Keep Original",
            "Convert and Delete Original"
        ])
        current_mode = self.settings.value("conversion_mode", "No Conversion")
        index = self.conversion_mode.findText(current_mode)
        if index >= 0:
            self.conversion_mode.setCurrentIndex(index)
        self.conversion_mode.currentTextChanged.connect(self.update_conversion_fields_state)
        conversion_layout.addRow("Conversion Mode:", self.conversion_mode)

        self.output_format = QComboBox()
        self.output_format.addItems(list(AUDIO_FORMATS.keys()))
        current_format = self.settings.value("conversion_format", "MP3")
        index = self.output_format.findText(current_format)
        if index >= 0:
            self.output_format.setCurrentIndex(index)
        self.output_format.currentTextChanged.connect(self.update_bitrate_state)
        conversion_layout.addRow("Output Format:", self.output_format)

        self.bitrate = QComboBox()
        self.bitrate.addItems([f"{b} kbps" for b in BITRATE_OPTIONS])
        current_bitrate = self.settings.value("conversion_bitrate", "192")
        bitrate_index = BITRATE_OPTIONS.index(current_bitrate) if current_bitrate in BITRATE_OPTIONS else 3
        self.bitrate.setCurrentIndex(bitrate_index)
        conversion_layout.addRow("Bitrate:", self.bitrate)

        self.sample_rate = QComboBox()
        self.sample_rate.addItems([f"{r} Hz" for r in SAMPLE_RATE_OPTIONS])
        current_rate = self.settings.value("conversion_sample_rate", "44100")
        rate_index = SAMPLE_RATE_OPTIONS.index(current_rate) if current_rate in SAMPLE_RATE_OPTIONS else 1
        self.sample_rate.setCurrentIndex(rate_index)
        conversion_layout.addRow("Sample Rate:", self.sample_rate)

        self.channels = QComboBox()
        self.channels.addItems(list(CHANNEL_OPTIONS.keys()))
        current_channels = self.settings.value("conversion_channels", "Stereo")
        ch_index = self.channels.findText(current_channels)
        if ch_index >= 0:
            self.channels.setCurrentIndex(ch_index)
        conversion_layout.addRow("Channels:", self.channels)

        layout.addWidget(conversion_group)

        self.update_conversion_fields_state()
        self.update_bitrate_state()

        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.path_edit.setText(folder)

    def update_conversion_fields_state(self):
        enabled = self.conversion_mode.currentText() != "No Conversion"
        self.output_format.setEnabled(enabled)
        self.bitrate.setEnabled(enabled)
        self.sample_rate.setEnabled(enabled)
        self.channels.setEnabled(enabled)
        if enabled:
            self.update_bitrate_state()

    def update_bitrate_state(self):
        if not self.output_format.isEnabled():
            return
        fmt = self.output_format.currentText()
        is_lossy = AUDIO_FORMATS.get(fmt, {}).get("lossy", True)
        self.bitrate.setEnabled(is_lossy)

    def save_settings(self):
        path = self.path_edit.text().strip()
        if path and not os.path.isdir(path):
            QMessageBox.warning(self, "Invalid Path", "The selected folder does not exist.")
            return
        self.settings.setValue("download_directory", path)
        self.settings.setValue("conversion_mode", self.conversion_mode.currentText())
        self.settings.setValue("conversion_format", self.output_format.currentText())
        bitrate_text = self.bitrate.currentText().replace(" kbps", "")
        self.settings.setValue("conversion_bitrate", bitrate_text)
        rate_text = self.sample_rate.currentText().replace(" Hz", "")
        self.settings.setValue("conversion_sample_rate", rate_text)
        self.settings.setValue("conversion_channels", self.channels.currentText())
        self.accept()
