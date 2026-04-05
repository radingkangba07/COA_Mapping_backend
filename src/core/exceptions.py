class AppError(Exception):
    status_code: int = 500

    def __init__(self, detail: str = "Internal server error"):
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = 404

    def __init__(self, detail: str = "Not found"):
        super().__init__(detail)


class ForbiddenError(AppError):
    status_code = 403

    def __init__(self, detail: str = "Forbidden"):
        super().__init__(detail)


class ConflictError(AppError):
    status_code = 409

    def __init__(self, detail: str = "Conflict"):
        super().__init__(detail)


class ValidationError(AppError):
    status_code = 422

    def __init__(self, detail: str = "Validation error"):
        super().__init__(detail)


class ServiceUnavailableError(AppError):
    status_code = 503

    def __init__(self, detail: str = "Service unavailable"):
        super().__init__(detail)
