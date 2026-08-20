"""phase7_analytics_and_behavioral_intelligence

Revision ID: 4a9281e0cd45
Revises: 3f819a71bd32
Create Date: 2026-08-18 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4a9281e0cd45'
down_revision: Union[str, None] = '3f819a71bd32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. analytics_snapshots
    op.create_table(
        'analytics_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('broker', sa.String(length=50), nullable=False, server_default='EXNESS'),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=100), nullable=False),
        sa.Column('reconstruction_run_id', sa.UUID(), nullable=False),
        sa.Column('reconciliation_run_id', sa.UUID(), nullable=True),
        sa.Column('period_type', sa.String(length=32), nullable=False),
        sa.Column('start_time_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_trades', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('winning_trades', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('losing_trades', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('breakeven_trades', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('win_rate', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('loss_rate', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('gross_profit', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('gross_loss', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('net_pnl', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('profit_factor', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('expectancy', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('payoff_ratio', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('avg_trade', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('median_trade', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('avg_winner', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('avg_loser', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('largest_winner', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('largest_loser', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('max_drawdown_amount', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('max_drawdown_pct', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('recovery_factor', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('drawdown_duration_sec', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('recovery_duration_sec', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('avg_holding_sec', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('median_holding_sec', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('avg_winner_holding_sec', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('avg_loser_holding_sec', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('duration_ratio', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('total_volume_lots', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('avg_lot_size', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('max_lot_size', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('max_consecutive_wins', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('max_consecutive_losses', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('hhi_symbol_concentration', sa.Numeric(precision=8, scale=2), nullable=False, server_default='0.00'),
        sa.Column('top_symbol_volume_pct', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('currency', sa.String(length=16), nullable=False, server_default='USD'),
        sa.Column('is_compromised', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('data_integrity_score', sa.Numeric(precision=5, scale=2), nullable=False, server_default='100.00'),
        sa.Column('integrity_grade', sa.String(length=8), nullable=False, server_default='AAA'),
        sa.Column('calculation_version', sa.String(length=24), nullable=False, server_default='7.0.0'),
        sa.Column('metrics_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconstruction_run_id'], ['reconstruction_runs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reconciliation_run_id'], ['reconciliation_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_analytics_snap_acc_period', 'analytics_snapshots', ['tenant_id', 'account_number', 'period_type', 'end_time_utc'])
    op.create_index('ix_analytics_snap_run', 'analytics_snapshots', ['reconstruction_run_id'])

    # 2. analytics_feature_store
    op.create_table(
        'analytics_feature_store',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('broker', sa.String(length=50), nullable=False, server_default='EXNESS'),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=100), nullable=False),
        sa.Column('reconstruction_run_id', sa.UUID(), nullable=False),
        sa.Column('dimension_type', sa.String(length=32), nullable=False),
        sa.Column('dimension_key', sa.String(length=64), nullable=False),
        sa.Column('trade_count', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('win_count', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('loss_count', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('volume_lots', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('gross_profit', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('gross_loss', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('net_pnl', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('profit_factor', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('win_rate', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('expectancy', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('avg_holding_sec', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('features_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('calculation_version', sa.String(length=24), nullable=False, server_default='7.0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconstruction_run_id'], ['reconstruction_runs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'account_number', 'reconstruction_run_id', 'dimension_type', 'dimension_key', name='uq_feature_dim_key')
    )
    op.create_index('ix_feature_store_acc_dim', 'analytics_feature_store', ['tenant_id', 'account_number', 'dimension_type'])

    # 3. behavioral_patterns
    op.create_table(
        'behavioral_patterns',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('broker', sa.String(length=50), nullable=False, server_default='EXNESS'),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=100), nullable=False),
        sa.Column('reconstruction_run_id', sa.UUID(), nullable=False),
        sa.Column('pattern_type', sa.String(length=48), nullable=False),
        sa.Column('detection_rule_version', sa.String(length=24), nullable=False, server_default='1.0.0'),
        sa.Column('detection_status', sa.String(length=24), nullable=False, server_default='RULE_MATCHED'),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('evidence_strength', sa.String(length=24), nullable=False, server_default='STRONG'),
        sa.Column('window_start_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('supporting_trade_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('evidence_payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('affected_metrics', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='DETECTED'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconstruction_run_id'], ['reconstruction_runs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_behavioral_pat_acc_type', 'behavioral_patterns', ['tenant_id', 'account_number', 'pattern_type', 'severity'])
    op.create_index('ix_behavioral_pat_time', 'behavioral_patterns', ['tenant_id', 'account_number', 'window_start_utc'])

    # 4. trading_dna_profiles
    op.create_table(
        'trading_dna_profiles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('broker', sa.String(length=50), nullable=False, server_default='EXNESS'),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=100), nullable=False),
        sa.Column('reconstruction_run_id', sa.UUID(), nullable=False),
        sa.Column('primary_trading_style', sa.String(length=32), nullable=False),
        sa.Column('risk_appetite_grade', sa.String(length=24), nullable=False),
        sa.Column('consistency_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('discipline_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('execution_quality_score', sa.Numeric(precision=5, scale=2), nullable=False, server_default='100.00'),
        sa.Column('favored_instruments', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('favored_sessions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('radar_dimensions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('top_strengths', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('top_weaknesses', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('behavioral_tendencies', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('calculation_version', sa.String(length=24), nullable=False, server_default='7.0.0'),
        sa.Column('synthesized_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconstruction_run_id'], ['reconstruction_runs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_dna_profiles_acc', 'trading_dna_profiles', ['tenant_id', 'account_number', 'synthesized_at'])

    # 5. baseline_comparisons
    op.create_table(
        'baseline_comparisons',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('broker', sa.String(length=50), nullable=False, server_default='EXNESS'),
        sa.Column('account_number', sa.BigInteger(), nullable=False),
        sa.Column('server_name', sa.String(length=100), nullable=False),
        sa.Column('reconstruction_run_id', sa.UUID(), nullable=False),
        sa.Column('comparison_cohort', sa.String(length=48), nullable=False),
        sa.Column('current_start_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_end_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('baseline_start_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('baseline_end_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('metric_comparisons', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('detected_drifts', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('overall_trajectory', sa.String(length=24), nullable=False, server_default='STABLE'),
        sa.Column('calculation_version', sa.String(length=24), nullable=False, server_default='7.0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reconstruction_run_id'], ['reconstruction_runs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_baseline_comp_acc', 'baseline_comparisons', ['tenant_id', 'account_number', 'comparison_cohort'])


def downgrade() -> None:
    op.drop_table('baseline_comparisons')
    op.drop_table('trading_dna_profiles')
    op.drop_table('behavioral_patterns')
    op.drop_table('analytics_feature_store')
    op.drop_table('analytics_snapshots')
