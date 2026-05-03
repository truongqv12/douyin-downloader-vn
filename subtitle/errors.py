class SubtitleError(Exception):
    """Base error for subtitle processing."""


class SubtitleParseError(SubtitleError):
    """Raised when an SRT/ASS file cannot be parsed safely."""


class TranslationError(SubtitleError):
    """Raised when a translation backend returns invalid data."""


class FFmpegError(SubtitleError):
    """Raised when FFmpeg/FFprobe fails."""


class DependencyUnavailableError(SubtitleError):
    """Raised when an optional dependency is not installed."""
