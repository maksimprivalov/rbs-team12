from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class FunctionStatus(str, Enum):
    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    SAFE = "SAFE"
    REJECTED = "REJECTED"
    READY = "READY"


class Function(Base):
    __tablename__ = "functions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=FunctionStatus.PENDING)
    invoke_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship(back_populates="functions")  # noqa: F821
    files: Mapped[list["FunctionFile"]] = relationship(back_populates="function", cascade="all, delete-orphan")


class FunctionFile(Base):
    __tablename__ = "function_files"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    function_id: Mapped[int] = mapped_column(ForeignKey("functions.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)

    function: Mapped["Function"] = relationship(back_populates="files")
