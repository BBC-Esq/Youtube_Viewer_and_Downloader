from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QPixmap, QImage

import urllib.request


class ThumbnailThread(QThread):
    finished = Signal(QPixmap)
    error = Signal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
            image = QImage()
            if image.loadFromData(data):
                self.finished.emit(QPixmap.fromImage(image))
            else:
                self.error.emit("Failed to decode thumbnail image.")
        except Exception as e:
            self.error.emit(str(e))
