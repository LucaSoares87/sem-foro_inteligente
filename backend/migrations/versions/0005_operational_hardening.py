from alembic import op
import sqlalchemy as sa

revision="0005_operational_hardening"
down_revision="0004_intersection_geography"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("operational_audit_events",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("request_id",sa.String(64),nullable=False),
        sa.Column("actor",sa.String(160),nullable=False),
        sa.Column("roles",sa.String(120),nullable=False),
        sa.Column("method",sa.String(8),nullable=False),
        sa.Column("route",sa.String(200),nullable=False),
        sa.Column("status_code",sa.Integer(),nullable=False),
        sa.Column("outcome",sa.String(40),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_operational_audit_events_request_id","operational_audit_events",["request_id"],unique=True)
    op.create_index("ix_operational_audit_events_created_at","operational_audit_events",["created_at"])

def downgrade():
    op.drop_index("ix_operational_audit_events_created_at",table_name="operational_audit_events")
    op.drop_index("ix_operational_audit_events_request_id",table_name="operational_audit_events")
    op.drop_table("operational_audit_events")
