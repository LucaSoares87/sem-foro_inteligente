from alembic import op
import sqlalchemy as sa

revision="0006_queue_optimization"
down_revision="0005_operational_hardening"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("queue_states",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("source_id",sa.String(80),nullable=False),
        sa.Column("intersection_code",sa.String(80),nullable=False),
        sa.Column("queue_epoch",sa.String(36),nullable=False),
        sa.Column("frame_sequence",sa.BigInteger(),nullable=False),
        sa.Column("payload",sa.JSON(),nullable=False),
        sa.Column("digest",sa.String(64),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint("source_id","queue_epoch","frame_sequence",name="uq_queue_state"))
    op.create_index("ix_queue_states_source_id","queue_states",["source_id"])
    op.create_index("ix_queue_states_intersection_code","queue_states",["intersection_code"])
    op.create_index("ix_queue_states_created_at","queue_states",["created_at"])

    op.create_table("optimization_experiments",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("source_id",sa.String(80),nullable=False),
        sa.Column("intersection_code",sa.String(80),nullable=False),
        sa.Column("state_sha256",sa.String(64),nullable=False),
        sa.Column("payload",sa.JSON(),nullable=False),
        sa.Column("digest",sa.String(64),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint("source_id","state_sha256",name="uq_optimization_state"))
    op.create_index("ix_optimization_experiments_source_id","optimization_experiments",["source_id"])
    op.create_index("ix_optimization_experiments_intersection_code","optimization_experiments",["intersection_code"])
    op.create_index("ix_optimization_experiments_created_at","optimization_experiments",["created_at"])

def downgrade():
    op.drop_index("ix_optimization_experiments_created_at",table_name="optimization_experiments")
    op.drop_index("ix_optimization_experiments_intersection_code",table_name="optimization_experiments")
    op.drop_index("ix_optimization_experiments_source_id",table_name="optimization_experiments")
    op.drop_table("optimization_experiments")
    op.drop_index("ix_queue_states_created_at",table_name="queue_states")
    op.drop_index("ix_queue_states_intersection_code",table_name="queue_states")
    op.drop_index("ix_queue_states_source_id",table_name="queue_states")
    op.drop_table("queue_states")
