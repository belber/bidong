class AppError(Exception):
    """业务错误，main.py 统一转成 JSON 响应。"""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)

