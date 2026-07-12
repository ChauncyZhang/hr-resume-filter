from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from server.app.identity.models import AuditLog, Base, UserSession


class IdentityStore:
    SessionModel = UserSession
    AuditModel = AuditLog

    def __init__(self, database_url: str) -> None:
        sync_url = database_url.replace("postgresql+asyncpg", "postgresql+psycopg").replace("sqlite+aiosqlite", "sqlite")
        self.engine = create_engine(sync_url)
        self.sync_session: sessionmaker[Session] = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
