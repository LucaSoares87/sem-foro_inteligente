from alembic import op
import sqlalchemy as sa

revision="0004_intersection_geography"
down_revision="0003_traffic_history"
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table("intersections") as batch:
        batch.add_column(sa.Column("district",sa.String(120),nullable=True))
        batch.add_column(sa.Column("latitude",sa.Float(),nullable=True))
        batch.add_column(sa.Column("longitude",sa.Float(),nullable=True))
        batch.add_column(sa.Column("enabled",sa.Boolean(),nullable=False,server_default=sa.true()))
        batch.add_column(sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
        batch.create_check_constraint("ck_intersection_coordinate_pair",
            "(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)")
        batch.create_check_constraint("ck_intersection_latitude","latitude IS NULL OR (latitude >= -90 AND latitude <= 90)")
        batch.create_check_constraint("ck_intersection_longitude","longitude IS NULL OR (longitude >= -180 AND longitude <= 180)")

def downgrade():
    with op.batch_alter_table("intersections") as batch:
        batch.drop_constraint("ck_intersection_longitude",type_="check")
        batch.drop_constraint("ck_intersection_latitude",type_="check")
        batch.drop_constraint("ck_intersection_coordinate_pair",type_="check")
        batch.drop_column("updated_at")
        batch.drop_column("enabled")
        batch.drop_column("longitude")
        batch.drop_column("latitude")
        batch.drop_column("district")
