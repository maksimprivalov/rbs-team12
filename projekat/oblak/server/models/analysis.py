from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    function_id: Mapped[int] = mapped_column(
        ForeignKey("functions.id"), nullable=False, unique=True, index=True
    )

    # Bandit rezultati
    bandit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bandit_report: Mapped[str | None] = mapped_column(Text, nullable=True)

    # pylint rezultati
    pylint_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pylint_report: Mapped[str | None] = mapped_column(Text, nullable=True)

    # LLM rezultati
    llm_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    llm_report: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Finalni verdict
    final_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    function: Mapped["Function"] = relationship()  # noqa: F821
