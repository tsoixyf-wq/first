"""Initial schema — resumes, job_descriptions, match_results.

Revision ID: 0001
Revises: None
Create Date: 2024-06-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- resumes ---
    op.create_table(
        "resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("parsed_data", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_text", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("parse_error", sa.String(500), nullable=True),
        sa.Column("parse_duration_ms", sa.Integer, nullable=True),
        sa.Column("embedding_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # --- job_descriptions ---
    op.create_table(
        "job_descriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("parsed_data", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_text", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("embedding_id", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # --- match_results ---
    op.create_table(
        "match_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("rule_score", sa.Float, nullable=True),
        sa.Column("tfidf_score", sa.Float, nullable=True),
        sa.Column("semantic_score", sa.Float, nullable=True),
        sa.Column("llm_score", sa.Float, nullable=True),
        sa.Column("overall_score", sa.Float, nullable=False),
        sa.Column("dimension_scores", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("matched_skills", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("missing_skills", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("llm_reasoning", sa.Text, nullable=True),
        sa.Column("suggestions", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_hard_pass", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("hard_pass_reasons", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("match_duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # --- indexes ---
    op.create_index("ix_match_results_resume_id", "match_results", ["resume_id"])
    op.create_index("ix_match_results_job_id", "match_results", ["job_id"])
    op.create_index("ix_match_results_overall_score", "match_results", ["overall_score"])
    op.create_index("ix_resumes_parse_status", "resumes", ["parse_status"])
    op.create_index("ix_job_descriptions_is_active", "job_descriptions", ["is_active"])


def downgrade() -> None:
    op.drop_table("match_results")
    op.drop_table("job_descriptions")
    op.drop_table("resumes")
