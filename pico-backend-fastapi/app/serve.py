import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:fastapi_app",
        host=settings.uvicorn_host,
        port=settings.uvicorn_port,
        reload=settings.uvicorn_reload,
        loop="uvloop",
        http="httptools",
        timeout_keep_alive=settings.uvicorn_timeout_keep_alive,
    )
