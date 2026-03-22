from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from app.core.database import get_db
from app.models.base import CAPartner
from app.core.auth_utils import hash_password, verify_password, create_access_token, get_current_ca

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name:             str
    email:            str
    password:         str
    phone:            str | None = None
    ca_number:        str | None = None
    white_label_name: str | None = None


class LoginRequest(BaseModel):
    email:    str
    password: str


class AuthResponse(BaseModel):
    token:   str
    ca_id:   int
    name:    str
    email:   str
    plan:    str
    white_label_name: str | None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    """Register a new CA account."""

    # Check if email already exists
    existing = db.query(CAPartner).filter(CAPartner.email == req.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered. Please login."
        )

    if len(req.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters."
        )

    ca = CAPartner(
        name             = req.name.strip(),
        email            = req.email.lower().strip(),
        password_hash    = hash_password(req.password),
        phone            = req.phone,
        ca_number        = req.ca_number,
        white_label_name = req.white_label_name or req.name.strip(),
        plan             = "starter",
        is_active        = True
    )
    db.add(ca)
    db.commit()
    db.refresh(ca)

    token = create_access_token(ca.id, ca.email)

    print(f"✅ New CA registered: {ca.email} | ID: {ca.id}")

    return AuthResponse(
        token            = token,
        ca_id            = ca.id,
        name             = ca.name,
        email            = ca.email,
        plan             = ca.plan,
        white_label_name = ca.white_label_name
    )


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Login for existing CA."""

    ca = db.query(CAPartner).filter(CAPartner.email == req.email.lower()).first()

    if not ca or not verify_password(req.password, ca.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if not ca.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact support."
        )

    token = create_access_token(ca.id, ca.email)

    print(f"✅ CA logged in: {ca.email} | ID: {ca.id}")

    return AuthResponse(
        token            = token,
        ca_id            = ca.id,
        name             = ca.name,
        email            = ca.email,
        plan             = ca.plan,
        white_label_name = ca.white_label_name
    )


@router.get("/me")
def get_me(ca: CAPartner = Depends(get_current_ca)):
    """Get current CA profile."""
    return {
        "ca_id":            ca.id,
        "name":             ca.name,
        "email":            ca.email,
        "phone":            ca.phone,
        "ca_number":        ca.ca_number,
        "plan":             ca.plan,
        "white_label_name": ca.white_label_name,
        "created_at":       str(ca.created_at)
    }


@router.put("/profile")
def update_profile(
    data: dict,
    ca: CAPartner = Depends(get_current_ca),
    db: Session = Depends(get_db)
):
    """Update CA profile."""
    allowed = ["name", "phone", "ca_number", "white_label_name"]
    for key in allowed:
        if key in data:
            setattr(ca, key, data[key])
    db.commit()
    return {"success": True, "message": "Profile updated."}