from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class BadRequestException(AppException):
    def __init__(self, detail: str = "잘못된 요청입니다.") -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)


class UnauthorizedException(AppException):
    def __init__(self, detail: str = "인증이 필요합니다.") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)


class ForbiddenException(AppException):
    def __init__(self, detail: str = "접근 권한이 없습니다.") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class NotFoundException(AppException):
    def __init__(self, detail: str = "리소스를 찾을 수 없습니다.") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ConflictException(AppException):
    def __init__(self, detail: str = "이미 존재하는 리소스입니다.") -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)


class InternalServerErrorException(AppException):
    def __init__(self, detail: str = "서버 내부 오류가 발생했습니다.") -> None:
        super().__init__(status.HTTP_500_INTERNAL_SERVER_ERROR, detail)


class BadGatewayException(AppException):
    def __init__(self, detail: str = "외부 서비스 응답이 올바르지 않습니다.") -> None:
        super().__init__(status.HTTP_502_BAD_GATEWAY, detail)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "요청 형식이 올바르지 않습니다."},
        )
