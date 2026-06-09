from sqlmodel import SQLModel, create_engine, Session
from adwatch.config import settings
import adwatch.models  # noqa: F401 — registers all SQLModel table metadata

# Railway injects DATABASE_URL as postgres://... but SQLAlchemy needs postgresql://
_url = settings.database_url
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}

engine = create_engine(_url, echo=False, connect_args=_connect_args)


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
