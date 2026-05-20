import logging
import re
from pathlib import Path


class SecretRedactionFilter(logging.Filter):
    TOKEN_PATTERN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.TOKEN_PATTERN.sub("bot<redacted>", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    redaction_filter = SecretRedactionFilter()
    stream_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    stream_handler.addFilter(redaction_filter)
    file_handler.addFilter(redaction_filter)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[stream_handler, file_handler],
        force=True,
    )
