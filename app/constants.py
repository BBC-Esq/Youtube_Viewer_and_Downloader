AUDIO_FORMATS = {
    "MP3": {"codec": "mp3", "extension": "mp3", "container": "mp3", "lossy": True},
    "AAC": {"codec": "aac", "extension": "aac", "container": "adts", "lossy": True},
    "FLAC": {"codec": "flac", "extension": "flac", "container": "flac", "lossy": False},
    "WAV": {"codec": "pcm_s16le", "extension": "wav", "container": "wav", "lossy": False},
    "OGG Vorbis": {"codec": "libvorbis", "extension": "ogg", "container": "ogg", "lossy": True},
}

CODEC_SAMPLE_FORMATS = {
    "mp3": "s16p",
    "aac": "fltp",
    "flac": "s16",
    "pcm_s16le": "s16",
    "libvorbis": "fltp",
}

BITRATE_OPTIONS = ["96", "128", "160", "192", "256", "320"]
SAMPLE_RATE_OPTIONS = ["22050", "44100", "48000"]
CHANNEL_OPTIONS = {"Stereo": 2, "Mono": 1}
