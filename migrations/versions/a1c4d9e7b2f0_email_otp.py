"""email verification and otp codes

Revision ID: a1c4d9e7b2f0
Revises: e3bf65fcd791
Create Date: 2026-11-09 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4d9e7b2f0'
down_revision = 'e3bf65fcd791'
branch_labels = None
depends_on = None


def upgrade():
    # Existing users (including the admin) stay verified so nobody is locked out.
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False,
                                     server_default=sa.true()))
    op.create_table('otp_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('otp_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_otp_codes_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('otp_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_otp_codes_user_id'))
    op.drop_table('otp_codes')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email_verified')
