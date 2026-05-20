import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import Base, engine
from routers.auth_router import router as auth_router
from routers.admin_router import router as admin_router
from routers.student_router import router as student_router

# Create all tables on startup
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_admin()
    yield


def _seed_admin():
    """Create default admin account if no admin exists."""
    from database import SessionLocal
    from models import User, UserRole
    from auth import hash_password
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.role == UserRole.admin).first()
        if not existing:
            admin = User(
                username=os.getenv("ADMIN_USERNAME", "admin"),
                full_name="System Administrator",
                role=UserRole.admin,
                password_hash=hash_password(os.getenv("ADMIN_PASSWORD", "Admin@1234")),
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print("✓ Default admin created — username: admin  password: Admin@1234")
    finally:
        db.close()


app = FastAPI(
    title="Babcock CBT Exam Platform",
    description="Secure Computer-Based Testing for Babcock University High School",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the frontend (served from the same origin or a dev server) to call the API
origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(student_router, prefix="/api/student", tags=["Student"])

# Serve the frontend static files when running in production
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Babcock CBT Platform"}
