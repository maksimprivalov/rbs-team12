"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("api_key", sa.String(64), nullable=False, unique=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "functions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, default="PENDING"),
        sa.Column("invoke_url", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "function_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("function_id", sa.Integer(), sa.ForeignKey("functions.id"), nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("function_files")
    op.drop_table("functions")
    op.drop_table("users")
