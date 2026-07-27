import logging
import re


class SensitiveDataFilter(logging.Filter):
    base64_pattern = re.compile(r"([A-Za-z0-9+/]{80,}={0,2})")
    cpf_pattern = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = self.base64_pattern.sub("[BASE64_REDACTED]", message)
        message = self.cpf_pattern.sub("[CPF_REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger().addFilter(SensitiveDataFilter())
