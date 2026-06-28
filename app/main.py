from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import ace_runtime, analyze, categories, concepts, files, generate, generators, health, jobs, lyrics, media, model_status, presets, slices, songs, style_versions, training
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.paths import ensure_app_dirs


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)

    app = FastAPI(title="AI Music POC", version="3.4")

    if settings.enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})

    app.include_router(health.router)
    app.include_router(analyze.router)
    app.include_router(generators.router)
    app.include_router(model_status.router)
    app.include_router(ace_runtime.router)
    app.include_router(presets.router)
    app.include_router(lyrics.router)
    app.include_router(generate.router)
    app.include_router(jobs.router)
    app.include_router(songs.router)
    app.include_router(slices.router)
    app.include_router(training.router)
    app.include_router(style_versions.router)
    app.include_router(files.router)
    app.include_router(categories.router)
    app.include_router(concepts.router)
    app.include_router(media.router)

    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


app = create_app()


def run_dev_server() -> None:
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=settings.app_env == "development")
