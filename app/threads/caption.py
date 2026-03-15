from PySide6.QtCore import QThread, Signal

from pytubefix import YouTube


class CaptionDownloadThread(QThread):
    completed = Signal(str)
    error = Signal(str)

    def __init__(self, url, caption_code, out_filename, fmt="srt", use_oauth=False):
        super().__init__()
        self.url = url
        self.caption_code = caption_code
        self.out_filename = out_filename
        self.fmt = fmt.lower()
        self.use_oauth = use_oauth

    def run(self):
        try:
            yt = YouTube(self.url, use_oauth=self.use_oauth)
            if self.caption_code not in [c.code for c in yt.captions]:
                raise ValueError(f"Caption track '{self.caption_code}' not found for this video.")
            caption = yt.captions[self.caption_code]
            if self.fmt == "srt":
                content = caption.generate_srt_captions()
                with open(self.out_filename, "w", encoding="utf-8") as f:
                    f.write(content)
            elif self.fmt == "txt":
                caption.save_captions(self.out_filename)
            else:
                raise ValueError("Unsupported caption format (choose SRT or TXT).")
            self.completed.emit(self.out_filename)
        except Exception as e:
            self.error.emit(str(e))
