from sqlalchemy import Column, Integer, String, DateTime, func
from src.data.clients.postgres_client import Base

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    role_name = Column(String(100), nullable=False, unique=True)
    created_at = Column(
    DateTime(timezone=True),
    server_default=func.now(),
    nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    