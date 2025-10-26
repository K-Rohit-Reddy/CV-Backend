import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .routes.auth import router as auth_router
from .routes.job_seeker import router as job_seeker_router
from importlib.metadata import version, PackageNotFoundError

# Ensure we load environment variables from Backend/.env regardless of CWD
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=str(ENV_PATH))

# Startup diagnostics (masked) to help during local dev
def _pkg_ver(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"

print(
    "[startup] env=Backend/.env:{exists} httpx={httpx} groq={groq} GROQ_API_KEY={grok} TAVILY_API_KEY={tavily}".format(
        exists=str(ENV_PATH.exists()),
        httpx=_pkg_ver("httpx"),
        groq=_pkg_ver("groq"),
        grok=("set" if os.getenv("GROQ_API_KEY") else "missing"),
        tavily=("set" if os.getenv("TAVILY_API_KEY") else "missing"),
    )
)

app = FastAPI(title="Smart Resume Analyzer API")

# Basic CORS (adjust as needed)
origins = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated files (e.g., PDFs) from Backend/Resumes at /files
RESUMES_DIR = Path(__file__).resolve().parent / "Resumes"
if RESUMES_DIR.exists():
    app.mount("/files", StaticFiles(directory=str(RESUMES_DIR)), name="files")

@app.get("/")
async def root():
    return {"status": "ok"}

# include routers
app.include_router(auth_router)
app.include_router(job_seeker_router)
