"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2026-06-04 00:00:00
"""
from alembic import op
import sqlalchemy as sa
import os
import sys

# ensure project root is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database.models import Base

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
