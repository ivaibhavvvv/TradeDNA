"""phase6_reconciliation_and_data_integrity

Revision ID: 3f819a71bd32
Revises: 2e9527af86b5
Create Date: 2026-08-18 21:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3f819a71bd32'
down_revision: Union[str, None] = '2e9527af86b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. reconciliation_runs
    op.create_table(
        'reconciliation_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=64), nullable=False),
        sa.Column('reconstruction_run_id', sa.UUID(), nullable=False),
        sa.Column('snapshot_id', sa.UUID(), nullable=True),
        sa.Column('reconciliation_type', sa.String(length=32), nullable=False),
        sa.Column('as_of_time_msc', sa.BigInteger(), nullable=False),
        sa.Column('as_of_timestamp_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_start_msc', sa.BigInteger(), nullable=True),
        sa.Column('window_end_msc', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('discrepancy_count', sa.Integer(), nullable=False),
        sa.Column('critical_count', sa.Integer(), nullable=False),
        sa.Column('high_count', sa.Integer(), nullable=False),
        sa.Column('medium_count', sa.Integer(), nullable=False),
        sa.Column('low_count', sa.Integer(), nullable=False),
        sa.Column('info_count', sa.Integer(), nullable=False),
        sa.Column('data_integrity_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('integrity_grade', sa.String(length=8), nullable=False),
        sa.Column('is_clean', sa.Boolean(), nullable=False),
        sa.Column('reconciliation_engine_version', sa.String(length=24), nullable=False),
        sa.Column('tolerance_profile_version', sa.String(length=24), nullable=False),
        sa.Column('severity_policy_version', sa.String(length=24), nullable=False),
        sa.Column('instrument_spec_version', sa.String(length=24), nullable=False),
        sa.Column('fx_source_version', sa.String(length=24), nullable=False),
        sa.Column('execution_time_ms', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconstruction_run_id'], ['reconstruction_runs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['snapshot_id'], ['raw_account_snapshots.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_recon_runs_account_time', 'reconciliation_runs', ['tenant_id', 'account_number', 'as_of_time_msc'], unique=False)
    op.create_index('idx_recon_runs_status_clean', 'reconciliation_runs', ['status', 'is_clean'], unique=False)

    # 2. remediation_proposals
    op.create_table(
        'remediation_proposals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=64), nullable=False),
        sa.Column('discrepancy_id', sa.UUID(), nullable=True),
        sa.Column('proposal_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('proposed_action', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('execution_result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('new_reconstruction_run_id', sa.UUID(), nullable=True),
        sa.Column('new_reconciliation_run_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['new_reconciliation_run_id'], ['reconciliation_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['new_reconstruction_run_id'], ['reconstruction_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. reconciliation_discrepancies
    op.create_table(
        'reconciliation_discrepancies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('reconciliation_run_id', sa.UUID(), nullable=False),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=64), nullable=False),
        sa.Column('discrepancy_scope', sa.String(length=24), nullable=False),
        sa.Column('discrepancy_category', sa.String(length=48), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('entity_type', sa.String(length=24), nullable=False),
        sa.Column('entity_identifier', sa.String(length=128), nullable=False),
        sa.Column('broker_value', sa.String(length=128), nullable=False),
        sa.Column('canonical_value', sa.String(length=128), nullable=False),
        sa.Column('delta_value', sa.String(length=128), nullable=False),
        sa.Column('broker_source', sa.String(length=128), nullable=False),
        sa.Column('canonical_source', sa.String(length=128), nullable=False),
        sa.Column('currency', sa.String(length=16), nullable=False),
        sa.Column('tolerance_applied', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('root_cause_category', sa.String(length=48), nullable=True),
        sa.Column('remediation_proposal_id', sa.UUID(), nullable=True),
        sa.Column('details_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('acknowledged_by', sa.UUID(), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledgement_notes', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['acknowledged_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reconciliation_run_id'], ['reconciliation_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['remediation_proposal_id'], ['remediation_proposals.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_recon_disc_account_status', 'reconciliation_discrepancies', ['tenant_id', 'account_number', 'status'], unique=False)
    op.create_index('idx_recon_disc_run_severity', 'reconciliation_discrepancies', ['reconciliation_run_id', 'severity'], unique=False)

    # 4. reconciliation_account_summaries
    op.create_table(
        'reconciliation_account_summaries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('reconciliation_run_id', sa.UUID(), nullable=False),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=64), nullable=False),
        sa.Column('currency', sa.String(length=16), nullable=False),
        sa.Column('mt5_balance', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('mt5_equity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('mt5_margin', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('mt5_free_margin', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('mt5_floating_pl', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('canonical_balance', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('canonical_equity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('canonical_margin', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('canonical_free_margin', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('canonical_floating_pl', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('balance_delta', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('equity_delta', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('margin_delta', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('free_margin_delta', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('floating_pl_delta', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconciliation_run_id'], ['reconciliation_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reconciliation_run_id')
    )

    # 5. reconciliation_position_summaries
    op.create_table(
        'reconciliation_position_summaries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('reconciliation_run_id', sa.UUID(), nullable=False),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=64), nullable=False),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.Column('position_ticket', sa.BigInteger(), nullable=False),
        sa.Column('side', sa.String(length=8), nullable=False),
        sa.Column('mt5_volume', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('mt5_price_open', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('mt5_price_current', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('mt5_profit', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('mt5_swap', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('canonical_open_volume', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('canonical_vwap_entry', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('canonical_floating_pl', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('canonical_swap', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('volume_delta', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('price_delta', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('profit_delta', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('market_price_used', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('market_price_timestamp_msc', sa.BigInteger(), nullable=False),
        sa.Column('fx_rate_used', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('fx_rate_source', sa.String(length=64), nullable=False),
        sa.Column('instrument_spec_version', sa.String(length=24), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconciliation_run_id'], ['reconciliation_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. data_integrity_score_history
    op.create_table(
        'data_integrity_score_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=64), nullable=False),
        sa.Column('reconciliation_run_id', sa.UUID(), nullable=False),
        sa.Column('score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('grade', sa.String(length=8), nullable=False),
        sa.Column('active_discrepancies', sa.Integer(), nullable=False),
        sa.Column('critical_discrepancies', sa.Integer(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconciliation_run_id'], ['reconciliation_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_score_history_lookup', 'data_integrity_score_history', ['tenant_id', 'account_number', 'recorded_at'], unique=False)


def downgrade() -> None:
    op.drop_table('data_integrity_score_history')
    op.drop_table('reconciliation_position_summaries')
    op.drop_table('reconciliation_account_summaries')
    op.drop_table('reconciliation_discrepancies')
    op.drop_table('remediation_proposals')
    op.drop_table('reconciliation_runs')
