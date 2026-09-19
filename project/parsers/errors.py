"""Parser-specific exceptions carrying safe diagnostics."""


class UnsupportedFormatError(ValueError):
    def __init__(self, reason: str, headers: list[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.headers = headers or []
