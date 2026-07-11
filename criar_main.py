import pathlib

main_content = '''from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_tables
from app.modules.auth.router import router as auth_router
from app.modules.cadastros.router import router as cadastros_router
from app.modules.embarque.router import router as embarque_router
from app.modules.auditoria.router import router as auditoria_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    if settings.ENVIRONMENT == "development":
        await create_tables()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(cadastros_router, prefix=settings.API_PREFIX)
app.include_router(embarque_router, prefix=settings.API_PREFIX)
app.include_router(auditoria_router, prefix=settings.API_PREFIX)


@app.get("/health", tags=["Sistema"])
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}
'''

pathlib.Path('app/main.py').write_text(main_content, encoding='utf-8')
print('OK -> app/main.py criado')
