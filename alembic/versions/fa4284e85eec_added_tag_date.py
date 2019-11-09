"""Added tag date

Revision ID: fa4284e85eec
Revises: 
Create Date: 2019-10-26 13:28:22.712435

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fa4284e85eec'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_added', sa.DateTime(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.drop_column('date_added')

    # ### end Alembic commands ###
