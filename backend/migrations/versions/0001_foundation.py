from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("intersections",
        sa.Column("code", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False))
    op.create_table("audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("intersection_code", sa.String(80), sa.ForeignKey("intersections.code"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("origin", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1"))
    op.create_index("ix_audit_events_intersection_code", "audit_events", ["intersection_code"])

def downgrade():
    op.drop_index("ix_audit_events_intersection_code", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("intersections")
