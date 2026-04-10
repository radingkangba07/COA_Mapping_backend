"""rename files to project_files, source_erp to source_system, job status queued, add file ids to jobs

Revision ID: 80363d0e89b7
Revises: 5f4d22303d15
Create Date: 2026-04-09 20:02:25.650028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '80363d0e89b7'
down_revision: Union[str, Sequence[str], None] = '5f4d22303d15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Rename files table to project_files
    op.rename_table('files', 'project_files')

    # 2. Add company_id column to project_files
    op.add_column('project_files', sa.Column('company_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_project_files_company_id', 'project_files', 'companies',
        ['company_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index(op.f('ix_project_files_company_id'), 'project_files', ['company_id'], unique=False)

    # 3. Update file_type default from 'upload' to 'source_erp'
    op.alter_column('project_files', 'file_type', server_default='source_erp')

    # 4. Rename source_erp -> source_system, target_erp -> target_system in projects
    op.alter_column('projects', 'source_erp', new_column_name='source_system')
    op.alter_column('projects', 'target_erp', new_column_name='target_system')

    # 5. Change jobs status default from 'pending' to 'queued'
    op.alter_column('jobs', 'status', server_default='queued')

    # 6. Add file ID columns and triggered_by to jobs
    op.add_column('jobs', sa.Column('source_file_id', sa.UUID(), nullable=True))
    op.add_column('jobs', sa.Column('target_file_id', sa.UUID(), nullable=True))
    op.add_column('jobs', sa.Column('mapping_file_id', sa.UUID(), nullable=True))
    op.add_column('jobs', sa.Column('account_type_mapping_file_id', sa.UUID(), nullable=True))
    op.add_column('jobs', sa.Column('triggered_by', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_jobs_triggered_by', 'jobs', 'users',
        ['triggered_by'], ['id'], ondelete='SET NULL',
    )

    # 7. Rename is_deleted -> is_active (inverse default)
    op.alter_column('project_files', 'is_deleted', new_column_name='is_active')
    op.execute("UPDATE project_files SET is_active = NOT is_active")
    op.alter_column('project_files', 'is_active', server_default='true')


def downgrade() -> None:
    """Downgrade schema."""
    # 7. Revert is_active -> is_deleted
    op.alter_column('project_files', 'is_active', new_column_name='is_deleted')
    op.execute("UPDATE project_files SET is_deleted = NOT is_deleted")
    op.alter_column('project_files', 'is_deleted', server_default='false')

    # 6. Remove file ID columns and triggered_by from jobs
    op.drop_constraint('fk_jobs_triggered_by', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'triggered_by')
    op.drop_column('jobs', 'account_type_mapping_file_id')
    op.drop_column('jobs', 'mapping_file_id')
    op.drop_column('jobs', 'target_file_id')
    op.drop_column('jobs', 'source_file_id')

    # 5. Revert jobs status default
    op.alter_column('jobs', 'status', server_default='pending')

    # 4. Rename back source_system -> source_erp, target_system -> target_erp
    op.alter_column('projects', 'source_system', new_column_name='source_erp')
    op.alter_column('projects', 'target_system', new_column_name='target_erp')

    # 3. Revert file_type default
    op.alter_column('project_files', 'file_type', server_default='upload')

    # 2. Remove company_id from project_files
    op.drop_index(op.f('ix_project_files_company_id'), table_name='project_files')
    op.drop_constraint('fk_project_files_company_id', 'project_files', type_='foreignkey')
    op.drop_column('project_files', 'company_id')

    # 1. Rename project_files back to files
    op.rename_table('project_files', 'files')
