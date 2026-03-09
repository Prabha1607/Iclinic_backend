from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from src.config.hashing import verify_password
from src.config.jwt_handler import create_access_token, create_refresh_token, verify_access_token, verify_refresh_token
from src.core.services.user import make_it_revoked, create_user, get_user, insert_refresh_token, is_revoked
from src.api.rest.dependencies import get_db
from src.schemas.user import UserCreate, UserLogin
from src.config.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register")
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        await create_user(db=db, user_data=user_data)
        logger.info("User registered successfully", extra={"email": user_data.email})
        return {"message": "User registered successfully"}

    except IntegrityError:
        logger.warning("Registration failed - duplicate entry", extra={"email": user_data.email})
        raise HTTPException(status_code=400, detail="Email or phone number already exists")

    except Exception as e:
        logger.error(f"Registration unexpected error : {e}", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Something went wrong")


@router.post("/login")
async def login_user(request: Request, response: Response, user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    try:
        user = await get_user(user_data.identifier, db)

        if not user or not verify_password(user_data.password, user.password):
            logger.warning("Login failed - invalid credentials", extra={"identifier": user_data.identifier})
            raise HTTPException(status_code=401, detail="Invalid credentials")

        payload = {
            "id": user.id,
            "email": user.email,
            "name": user.first_name + " " + user.last_name,
            "role_id": user.role_id,
            "phone_number": user.phone_no
        }

        access_data = await create_access_token(payload=payload)
        refresh_data = await create_refresh_token(payload=payload)

        access_token = access_data[0]
        refresh_token = refresh_data[0]
        refresh_token_id = refresh_data[1]

        await insert_refresh_token(db, refresh_token_id)

        response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax", secure=False, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, samesite="lax", secure=False, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86000)

        logger.info("User logged in", extra={"user_id": user.id})
        return {"message": "Authentication Successfull!!!", "access_token": access_token}

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Login unexpected error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Unexpected error occurred")


@router.get("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        refresh_token = request.cookies.get("refresh_token")

        if not refresh_token:
            raise HTTPException(status_code=400, detail="Refresh Token missing")

        payload = await verify_refresh_token(refresh_token)

        if payload is None:
            raise HTTPException(status_code=400, detail="Invalid or expired refresh token")

        await make_it_revoked(db=db, jti=payload.get("jti"))

        response.delete_cookie("refresh_token")
        response.delete_cookie("access_token")

        logger.info("User logged out", extra={"user_id": payload.get("id")})
        return {"message": "Logout successful"}

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Logout failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Logout failed")


@router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        refresh_token = request.cookies.get("refresh_token")

        if not refresh_token:
            raise HTTPException(status_code=401, detail="Refresh token missing")

        payload = await verify_refresh_token(refresh_token)

        if payload is None:
            raise HTTPException(status_code=403, detail="Invalid refresh token")

        if await is_revoked(jti=payload.get("jti"), db=db):
            logger.warning("Revoked refresh token used", extra={"user_id": payload.get("id")})
            raise HTTPException(status_code=403, detail="Refresh token revoked")

        token_data = {
            "email": payload.get("email"),
            "id": payload.get("id"),
            "name": payload.get("name"),
            "phone_number": payload.get("phone_number"),
            "role_id": payload.get("role_id")
        }

        access_data = await create_access_token(token_data)

        response.set_cookie(key="access_token", value=access_data[0], httponly=True, samesite="lax", secure=False, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

        return {"access_token": access_data[0], "token_type": "bearer"}

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Token refresh failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Token refresh failed")


@router.get("/verify")
async def verify_tokens(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        access_token = request.cookies.get("access_token")
        refresh_token_cookie = request.cookies.get("refresh_token")

        # Access token still valid — return it directly so frontend can hydrate Redux
        if access_token:
            try:
                payload = await verify_access_token(access_token)
                if payload:
                    user = {
                        "id": payload.get("id"),
                        "email": payload.get("email"),
                        "name": payload.get("name"),
                        "role_id": payload.get("role_id"),
                        "phone_number": payload.get("phone_number"),
                    }
                    return {
                        "valid": True,
                        "access_token": access_token,  
                        "user": user,
                    }
            except Exception:
                pass  

        if not refresh_token_cookie:
            raise HTTPException(status_code=401, detail="Not authenticated")

        payload = await verify_refresh_token(refresh_token_cookie)

        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        if await is_revoked(jti=payload.get("jti"), db=db):
            raise HTTPException(status_code=401, detail="Session revoked")

        token_data = {
            "id": payload.get("id"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "phone_number": payload.get("phone_number"),
            "role_id": payload.get("role_id"),
        }

        access_data = await create_access_token(token_data)
        new_access_token = access_data[0]

        logger.info("Silent token refresh on /verify", extra={"user_id": payload.get("id")})

        return JSONResponse(
            content={
                "valid": True,
                "access_token": new_access_token,
                "user": token_data,
            },
            headers={
                "Set-Cookie": (
                    f"access_token={new_access_token}; Path=/; HttpOnly; SameSite=Lax; "
                    f"Max-Age={settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}"
                )
            },
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Token verification failed", extra={"error": str(e)})
        raise HTTPException(status_code=401, detail="Verification failed")
    
