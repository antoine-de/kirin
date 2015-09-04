"""Create table: vehicle_journey, real_time_update, stop_time, modification

Revision ID: 434d1e68281b
Revises: None
Create Date: 2015-09-03 10:49:19.801740

"""

# revision identifiers, used by Alembic.
revision = '434d1e68281b'
down_revision = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('vehicle_journey',
    sa.Column('id', postgresql.UUID(), nullable=False),
    sa.Column('circulation_date', sa.Date(), nullable=False),
    sa.Column('navitia_id', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('real_time_update',
    sa.Column('id', postgresql.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('vj_id', postgresql.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['vj_id'], ['vehicle_journey.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('modification',
    sa.Column('id', postgresql.UUID(), nullable=False),
    sa.Column('real_time_update_id', postgresql.UUID(), nullable=True),
    sa.Column('type', sa.Enum('add', 'delete', name='modification_type'), nullable=False),
    sa.ForeignKeyConstraint(['real_time_update_id'], ['real_time_update.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('stop_time',
    sa.Column('id', postgresql.UUID(), nullable=False),
    sa.Column('modification_id', postgresql.UUID(), nullable=True),
    sa.Column('departure', sa.DateTime(), nullable=False),
    sa.Column('arrival', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['modification_id'], ['modification.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('stop_time')
    op.drop_table('modification')
    op.drop_table('real_time_update')
    op.drop_table('vehicle_journey')
    ### end Alembic commands ###

    #https://bitbucket.org/zzzeek/alembic/issues/159/opdrop_column-never-ends-with-an-enum
    sa.Enum(name='modification_type').drop(op.get_bind(), checkfirst=False)