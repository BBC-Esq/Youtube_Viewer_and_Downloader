from PySide6.QtCore import QThread, Signal


class DownloadThread(QThread):
    completed = Signal(str)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, stream, output_path=None, filename=None, filename_prefix=None,
                 skip_existing=True, timeout=None, max_retries=0,
                 interrupt_checker=None):
        super().__init__()
        self.stream = stream
        self.output_path = output_path
        self.filename = filename
        self.filename_prefix = filename_prefix
        self.skip_existing = skip_existing
        self.timeout = timeout
        self.max_retries = max_retries
        self.interrupt_checker = interrupt_checker

    def _on_progress(self, stream, chunk, bytes_remaining):
        total = stream.filesize
        if total > 0:
            percent = int(((total - bytes_remaining) / total) * 100)
            self.progress.emit(percent)

    def run(self):
        try:
            self.stream._monostate.on_progress = self._on_progress
            downloaded_file = self.stream.download(
                output_path=self.output_path,
                filename=self.filename,
                filename_prefix=self.filename_prefix,
                skip_existing=self.skip_existing,
                timeout=self.timeout,
                max_retries=self.max_retries,
                interrupt_checker=self.interrupt_checker
            )
            if downloaded_file:
                self.progress.emit(100)
                self.completed.emit(downloaded_file)
            else:
                self.error.emit("Download was skipped or failed.")
        except Exception as e:
            self.error.emit(str(e))
