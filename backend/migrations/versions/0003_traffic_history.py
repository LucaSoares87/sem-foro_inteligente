from alembic import op
import sqlalchemy as sa
revision="0003_traffic_history"
down_revision="0002_pipeline_archive"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("traffic_windows",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("source_id",sa.String(80),nullable=False),
        sa.Column("analytics_epoch",sa.String(36),nullable=False),
        sa.Column("start_sequence",sa.BigInteger(),nullable=False),
        sa.Column("payload",sa.JSON(),nullable=False),
        sa.Column("digest",sa.String(64),nullable=False),
        sa.UniqueConstraint("source_id","analytics_epoch","start_sequence",name="uq_traffic_window"))
    op.create_index("ix_traffic_windows_source_id","traffic_windows",["source_id"])

def downgrade():
    op.drop_index("ix_traffic_windows_source_id",table_name="traffic_windows")
    op.drop_table("traffic_windows")
