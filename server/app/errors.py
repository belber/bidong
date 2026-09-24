class AppError(Exception):
    """业务错误，main.py 统一转成 JSON 响应。"""

    def __init__(self, status_code: int, message: str, error_type: str | None = None):
        self.status_code = status_code
        self.message = message
        self.error_type = error_type
        super().__init__(message)

