"""Added chapter

Revision ID: 4f46e426f94e
Revises: fa4284e85eec
Create Date: 2022-11-04 12:07:09.143014

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4f46e426f94e'
down_revision = 'fa4284e85eec'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'chapter',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String),
        sa.Column('num', sa.Integer),
        sa.Column('story_id', sa.Integer, sa.ForeignKey('story.id')))

    op.create_table(
        'following_stories',
        sa.Column('story_id', sa.Integer, sa.ForeignKey('story.id')))

def downgrade():
    op.drop_table('chapter')
    op.drop_table('following_stories')
