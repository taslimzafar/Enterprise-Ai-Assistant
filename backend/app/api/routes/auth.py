from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_db, get_current_active_user
from app.core.security import get_password_hash, verify_password, create_access_token
from app.db.models.user import User
from app.db.models.organization import Organization
from app.db.models.membership import Membership, RoleEnum
from app.schemas.user import UserCreate, User as UserSchema
from app.schemas.token import Token

from app.core.rate_limit import rate_limiter
from app.core.config import settings
from app.core.audit_logger import log_security_event

router = APIRouter()

@router.post("/register", response_model=UserSchema)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Rate limit registration attempts
    await rate_limiter.check(f"auth:register:{user_in.email}", limit=settings.RATE_LIMIT_AUTH_PER_MINUTE)

    # Check if user exists
    result = await db.execute(select(User).filter(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system",
        )
    
    # Create user
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(user)
    await db.flush() # flush to get the user.id
    
    # Create default organization
    org_name = f"{user.email.split('@')[0]}'s Organization"
    org_slug = f"{user.email.split('@')[0]}-{user.id[:8]}"
    org = Organization(name=org_name, slug=org_slug)
    db.add(org)
    await db.flush()
    
    # Create membership
    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=RoleEnum.OWNER
    )
    db.add(membership)
    
    await db.commit()
    await db.refresh(user)

    log_security_event(
        "USER_REGISTERED",
        {"user_id": user.id, "email": user.email, "org_id": org.id},
        user_id=user.id,
        organization_id=org.id,
        severity="INFO",
    )
    return user

@router.post("/login", response_model=Token)
async def login(
    db: AsyncSession = Depends(get_db), 
    form_data: OAuth2PasswordRequestForm = Depends()
):
    # Rate limit login attempts per username
    await rate_limiter.check(f"auth:login:{form_data.username}", limit=settings.RATE_LIMIT_AUTH_PER_MINUTE)

    # Retrieve user
    result = await db.execute(select(User).filter(User.email == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        log_security_event(
            "LOGIN_FAILED",
            {"username": form_data.username},
            severity="WARNING",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not user.is_active:
        log_security_event(
            "LOGIN_INACTIVE_USER",
            {"user_id": user.id, "username": form_data.username},
            user_id=user.id,
            severity="WARNING",
        )
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token = create_access_token(subject=user.id)
    log_security_event(
        "LOGIN_SUCCESS",
        {"user_id": user.id},
        user_id=user.id,
        severity="INFO",
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user
