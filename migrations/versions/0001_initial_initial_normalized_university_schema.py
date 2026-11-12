"""initial normalized university schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-11-11 23:00:09.047541

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Reviewed: additive initial schema; btree_gist provides GiST integer equality.
    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public')
    op.create_table('clubs',
    sa.Column('club_id', sa.Integer(), nullable=False),
    sa.Column('club_name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(club_name)) > 0', name=op.f('ck_clubs_club_name_not_blank')),
    sa.PrimaryKeyConstraint('club_id', name=op.f('pk_clubs')),
    sa.UniqueConstraint('club_name', name=op.f('uq_clubs_club_name'))
    )
    op.create_table('users',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=512), nullable=False),
    sa.Column('role', sa.String(length=20), server_default='student', nullable=False),
    sa.CheckConstraint("role IN ('student', 'club_admin', 'system_admin')", name=op.f('ck_users_valid_role')),
    sa.CheckConstraint('length(trim(email)) > 0 AND email = lower(trim(email))', name=op.f('ck_users_normalized_email')),
    sa.CheckConstraint('length(trim(full_name)) > 0', name=op.f('ck_users_full_name_not_blank')),
    sa.CheckConstraint('length(trim(password_hash)) > 0', name=op.f('ck_users_password_hash_not_blank')),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_users'))
    )
    op.create_index('ix_users_full_name', 'users', ['full_name'], unique=False)
    op.create_index('uq_users_email', 'users', ['email'], unique=True)
    op.create_table('venues',
    sa.Column('venue_id', sa.Integer(), nullable=False),
    sa.Column('venue_name', sa.String(length=150), nullable=False),
    sa.Column('location', sa.String(length=255), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.CheckConstraint('capacity > 0', name=op.f('ck_venues_positive_capacity')),
    sa.CheckConstraint('length(trim(location)) > 0', name=op.f('ck_venues_location_not_blank')),
    sa.CheckConstraint('length(trim(venue_name)) > 0', name=op.f('ck_venues_venue_name_not_blank')),
    sa.PrimaryKeyConstraint('venue_id', name=op.f('pk_venues')),
    sa.UniqueConstraint('venue_name', name=op.f('uq_venues_venue_name'))
    )
    op.create_table('club_admins',
    sa.Column('club_admin_id', sa.Integer(), nullable=False),
    sa.Column('club_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.club_id'], name=op.f('fk_club_admins_club_id_clubs'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], name=op.f('fk_club_admins_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('club_admin_id', name=op.f('pk_club_admins')),
    sa.UniqueConstraint('club_id', 'user_id', name='uq_club_admins_club_user')
    )
    op.create_index(op.f('ix_club_admins_user_id'), 'club_admins', ['user_id'], unique=False)
    op.create_table('events',
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('club_id', sa.Integer(), nullable=False),
    sa.Column('venue_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='scheduled', nullable=False),
    postgresql.ExcludeConstraint((sa.column('venue_id'), '='), (sa.text("tstzrange(start_time, end_time, '[)')"), '&&'), where=sa.text("status <> 'cancelled'"), using='gist', name='ex_events_venue_time'),
    sa.CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name=op.f('ck_events_valid_status')),
    sa.CheckConstraint('capacity > 0', name=op.f('ck_events_positive_capacity')),
    sa.CheckConstraint('end_time > start_time', name=op.f('ck_events_valid_time_range')),
    sa.CheckConstraint('length(trim(title)) > 0', name=op.f('ck_events_title_not_blank')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.club_id'], name=op.f('fk_events_club_id_clubs'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['venue_id'], ['venues.venue_id'], name=op.f('fk_events_venue_id_venues'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('event_id', name=op.f('pk_events'))
    )
    op.create_index(op.f('ix_events_club_id'), 'events', ['club_id'], unique=False)
    op.create_index(op.f('ix_events_start_time'), 'events', ['start_time'], unique=False)
    op.create_index(op.f('ix_events_status'), 'events', ['status'], unique=False)
    op.create_index(op.f('ix_events_title'), 'events', ['title'], unique=False)
    op.create_index(op.f('ix_events_venue_id'), 'events', ['venue_id'], unique=False)
    op.create_table('students',
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('student_number', sa.String(length=40), nullable=False),
    sa.Column('department', sa.String(length=100), nullable=False),
    sa.Column('batch', sa.String(length=30), nullable=False),
    sa.CheckConstraint('length(trim(batch)) > 0', name=op.f('ck_students_batch_not_blank')),
    sa.CheckConstraint('length(trim(department)) > 0', name=op.f('ck_students_department_not_blank')),
    sa.CheckConstraint('length(trim(student_number)) > 0', name=op.f('ck_students_student_number_not_blank')),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], name=op.f('fk_students_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('student_id', name=op.f('pk_students')),
    sa.UniqueConstraint('student_number', name=op.f('uq_students_student_number')),
    sa.UniqueConstraint('user_id', name=op.f('uq_students_user_id'))
    )
    op.create_index(op.f('ix_students_department'), 'students', ['department'], unique=False)
    op.create_table('club_memberships',
    sa.Column('membership_id', sa.Integer(), nullable=False),
    sa.Column('club_id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.CheckConstraint("status IN ('active', 'cancelled')", name=op.f('ck_club_memberships_valid_status')),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.club_id'], name=op.f('fk_club_memberships_club_id_clubs'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['student_id'], ['students.student_id'], name=op.f('fk_club_memberships_student_id_students'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('membership_id', name=op.f('pk_club_memberships')),
    sa.UniqueConstraint('club_id', 'student_id', name='uq_club_memberships_club_student')
    )
    op.create_index(op.f('ix_club_memberships_student_id'), 'club_memberships', ['student_id'], unique=False)
    op.create_table('event_expenses',
    sa.Column('expense_id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('expense_date', sa.Date(), nullable=False),
    sa.CheckConstraint('amount >= 0', name=op.f('ck_event_expenses_nonnegative_amount')),
    sa.CheckConstraint('length(trim(description)) > 0', name=op.f('ck_event_expenses_description_not_blank')),
    sa.ForeignKeyConstraint(['event_id'], ['events.event_id'], name=op.f('fk_event_expenses_event_id_events'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('expense_id', name=op.f('pk_event_expenses'))
    )
    op.create_index(op.f('ix_event_expenses_event_id'), 'event_expenses', ['event_id'], unique=False)
    op.create_index(op.f('ix_event_expenses_expense_date'), 'event_expenses', ['expense_date'], unique=False)
    op.create_table('registrations',
    sa.Column('registration_id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='registered', nullable=False),
    sa.CheckConstraint("status IN ('registered', 'cancelled', 'attended')", name=op.f('ck_registrations_valid_status')),
    sa.ForeignKeyConstraint(['event_id'], ['events.event_id'], name=op.f('fk_registrations_event_id_events'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['student_id'], ['students.student_id'], name=op.f('fk_registrations_student_id_students'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('registration_id', name=op.f('pk_registrations')),
    sa.UniqueConstraint('event_id', 'student_id', name='uq_registrations_event_student')
    )
    op.create_index('ix_registrations_event_status', 'registrations', ['event_id', 'status'], unique=False)
    op.create_index(op.f('ix_registrations_student_id'), 'registrations', ['student_id'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_registrations_student_id'), table_name='registrations')
    op.drop_index('ix_registrations_event_status', table_name='registrations')
    op.drop_table('registrations')
    op.drop_index(op.f('ix_event_expenses_expense_date'), table_name='event_expenses')
    op.drop_index(op.f('ix_event_expenses_event_id'), table_name='event_expenses')
    op.drop_table('event_expenses')
    op.drop_index(op.f('ix_club_memberships_student_id'), table_name='club_memberships')
    op.drop_table('club_memberships')
    op.drop_index(op.f('ix_students_department'), table_name='students')
    op.drop_table('students')
    op.drop_index(op.f('ix_events_venue_id'), table_name='events')
    op.drop_index(op.f('ix_events_title'), table_name='events')
    op.drop_index(op.f('ix_events_status'), table_name='events')
    op.drop_index(op.f('ix_events_start_time'), table_name='events')
    op.drop_index(op.f('ix_events_club_id'), table_name='events')
    op.drop_table('events')
    op.drop_index(op.f('ix_club_admins_user_id'), table_name='club_admins')
    op.drop_table('club_admins')
    op.drop_table('venues')
    op.drop_index('uq_users_email', table_name='users')
    op.drop_index('ix_users_full_name', table_name='users')
    op.drop_table('users')
    op.drop_table('clubs')
    # ### end Alembic commands ###
