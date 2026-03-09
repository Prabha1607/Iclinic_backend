from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from src.config.jwt_handler import verify_access_token

class AuthorizationMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        public_paths = [
            "/",
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
            "/api/v1/auth/verify",
            "/api/v1/voice/voice-response",
            "/api/v1/users/get_roles",
            "/api/v1/voice/call-status",
            "/api/v1/users/patients/create",  
            "/favicon.ico",
            "/docs",
            "/openapi.json"
        ]

        if request.url.path in public_paths or request.method == "OPTIONS":
            return await call_next(request)

        try:
            credential = request.headers.get("Authorization")

            if credential is None:
                raise HTTPException(detail="Bearer authorization required", status_code=400)

            scheme, _, token = credential.partition(" ")

            if scheme.lower() != "bearer":
                raise HTTPException(status_code=403, detail="Invalid or expired token.")

            access_payload = await verify_access_token(token)

            if access_payload is None:
                raise HTTPException(status_code=403, detail="Invalid or expired token.")

            return await call_next(request)

        except Exception as e:
            return JSONResponse(status_code=401, content={"detail": str(e)})