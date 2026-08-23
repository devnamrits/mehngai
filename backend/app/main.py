from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router
from app.core.config import get_settings
from app.core.db import init_db
from app.services.pulse import pulse_bus


def _durable_sink(event) -> None:
    from app.core.db import session_scope
    from app.domain.models import PulseEvent

    with session_scope() as session:
        session.add(
            PulseEvent(
                ts=event.ts,
                level=event.level,
                kind=event.kind,
                message=event.message,
            )
        )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Mehngai API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    pulse_bus.bind_durable_sink(_durable_sink)
    app.include_router(router)

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    return app


app = create_app()
