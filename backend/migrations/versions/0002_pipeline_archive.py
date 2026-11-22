from alembic import op
import sqlalchemy as sa

revision = "0002_pipeline_archive"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("pipeline_archive",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("event_id",sa.String(36),nullable=False,unique=True),
        sa.Column("intersection_code",sa.String(80),nullable=False),
        sa.Column("origin",sa.String(16),nullable=False),
        sa.Column("payload",sa.JSON(),nullable=False),
        sa.Column("digest",sa.String(64),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint("origin = 'synthetic'",name="ck_pipeline_archive_origin"))
    op.create_index("ix_pipeline_archive_intersection_code","pipeline_archive",["intersection_code"])
    op.create_index("ix_pipeline_archive_created_at","pipeline_archive",["created_at"])

def downgrade():
    op.drop_index("ix_pipeline_archive_created_at",table_name="pipeline_archive")
    op.drop_index("ix_pipeline_archive_intersection_code",table_name="pipeline_archive")
    op.drop_table("pipeline_archive")
