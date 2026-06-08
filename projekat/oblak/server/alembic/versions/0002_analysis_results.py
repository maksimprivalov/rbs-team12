"""add analysis_results table

Revision ID: 0002_analysis_results

"""

from alembic import op
import sqlalchemy as sa

revision = "0002_analysis_results"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("function_id", sa.Integer(), sa.ForeignKey("functions.id"), nullable=False),
        sa.Column("bandit_score", sa.Integer(), nullable=True),
        sa.Column("bandit_report", sa.Text(), nullable=True),
        sa.Column("pylint_score", sa.Float(), nullable=True),
        sa.Column("pylint_report", sa.Text(), nullable=True),
        sa.Column("llm_verdict", sa.String(16), nullable=True),
        sa.Column("llm_report", sa.Text(), nullable=True),
        sa.Column("final_verdict", sa.String(16), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("function_id"),
    )
    op.create_index("ix_analysis_results_id", "analysis_results", ["id"])
    op.create_index("ix_analysis_results_function_id", "analysis_results", ["function_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_results_function_id", table_name="analysis_results")
    op.drop_index("ix_analysis_results_id", table_name="analysis_results")
    op.drop_table("analysis_results")
