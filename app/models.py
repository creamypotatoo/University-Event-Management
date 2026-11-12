"""Normalized domain models. Schema changes are managed exclusively by Alembic."""

from sqlalchemy.dialects.postgresql import ExcludeConstraint
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    user_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(20), nullable=False, server_default="student")
    __table_args__ = (
        db.CheckConstraint("role IN ('student', 'club_admin', 'system_admin')", name="valid_role"),
        db.CheckConstraint("length(trim(full_name)) > 0", name="full_name_not_blank"),
        db.CheckConstraint("length(trim(email)) > 0 AND email = lower(trim(email))", name="normalized_email"),
        db.CheckConstraint("length(trim(password_hash)) > 0", name="password_hash_not_blank"),
        db.Index("uq_users_email", "email", unique=True),
        db.Index("ix_users_full_name", "full_name"),
    )
    student = db.relationship("Student", back_populates="user", uselist=False)
    club_admin_assignments = db.relationship("ClubAdmin", back_populates="user")

    def get_id(self):
        return str(self.user_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password):
        try:
            return check_password_hash(self.password_hash, password)
        except (ValueError, TypeError):
            return False


class Student(db.Model):
    __tablename__ = "students"
    student_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False, unique=True)
    student_number = db.Column(db.String(40), nullable=False, unique=True)
    department = db.Column(db.String(100), nullable=False, index=True)
    batch = db.Column(db.String(30), nullable=False)
    __table_args__ = (
        db.CheckConstraint("length(trim(student_number)) > 0", name="student_number_not_blank"),
        db.CheckConstraint("length(trim(department)) > 0", name="department_not_blank"),
        db.CheckConstraint("length(trim(batch)) > 0", name="batch_not_blank"),
    )
    user = db.relationship("User", back_populates="student")
    memberships = db.relationship("ClubMembership", back_populates="student")
    registrations = db.relationship("Registration", back_populates="student")


class Club(db.Model):
    __tablename__ = "clubs"
    club_id = db.Column(db.Integer, primary_key=True)
    club_name = db.Column(db.String(150), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.true(), default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    __table_args__ = (db.CheckConstraint("length(trim(club_name)) > 0", name="club_name_not_blank"),)
    memberships = db.relationship("ClubMembership", back_populates="club")
    admin_assignments = db.relationship("ClubAdmin", back_populates="club")
    events = db.relationship("Event", back_populates="club")


class ClubMembership(db.Model):
    __tablename__ = "club_memberships"
    membership_id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.club_id", ondelete="RESTRICT"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.student_id", ondelete="RESTRICT"), nullable=False, index=True)
    joined_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    status = db.Column(db.String(20), nullable=False, server_default="active")
    __table_args__ = (
        db.UniqueConstraint("club_id", "student_id", name="uq_club_memberships_club_student"),
        db.CheckConstraint("status IN ('active', 'cancelled')", name="valid_status"),
    )
    club = db.relationship("Club", back_populates="memberships")
    student = db.relationship("Student", back_populates="memberships")


class ClubAdmin(db.Model):
    __tablename__ = "club_admins"
    club_admin_id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.club_id", ondelete="RESTRICT"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint("club_id", "user_id", name="uq_club_admins_club_user"),)
    club = db.relationship("Club", back_populates="admin_assignments")
    user = db.relationship("User", back_populates="club_admin_assignments")


class Venue(db.Model):
    __tablename__ = "venues"
    venue_id = db.Column(db.Integer, primary_key=True)
    venue_name = db.Column(db.String(150), nullable=False, unique=True)
    location = db.Column(db.String(255), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    __table_args__ = (
        db.CheckConstraint("capacity > 0", name="positive_capacity"),
        db.CheckConstraint("length(trim(venue_name)) > 0", name="venue_name_not_blank"),
        db.CheckConstraint("length(trim(location)) > 0", name="location_not_blank"),
    )
    events = db.relationship("Event", back_populates="venue")


class Event(db.Model):
    __tablename__ = "events"
    event_id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.club_id", ondelete="RESTRICT"), nullable=False, index=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.venue_id", ondelete="RESTRICT"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    start_time = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    end_time = db.Column(db.DateTime(timezone=True), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, server_default="scheduled", index=True)
    __table_args__ = (
        db.CheckConstraint("capacity > 0", name="positive_capacity"),
        db.CheckConstraint("end_time > start_time", name="valid_time_range"),
        db.CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name="valid_status"),
        db.CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        ExcludeConstraint(
            ("venue_id", "="),
            (db.func.tstzrange(start_time, end_time, "[)"), "&&"),
            where=db.text("status <> 'cancelled'"), using="gist",
            name="ex_events_venue_time",
        ).ddl_if(dialect="postgresql"),
    )
    club = db.relationship("Club", back_populates="events")
    venue = db.relationship("Venue", back_populates="events")
    registrations = db.relationship("Registration", back_populates="event")
    expenses = db.relationship("EventExpense", back_populates="event")


class Registration(db.Model):
    __tablename__ = "registrations"
    registration_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.event_id", ondelete="RESTRICT"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.student_id", ondelete="RESTRICT"), nullable=False, index=True)
    registered_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    status = db.Column(db.String(20), nullable=False, server_default="registered")
    __table_args__ = (
        db.UniqueConstraint("event_id", "student_id", name="uq_registrations_event_student"),
        db.CheckConstraint("status IN ('registered', 'cancelled', 'attended')", name="valid_status"),
        db.Index("ix_registrations_event_status", "event_id", "status"),
    )
    event = db.relationship("Event", back_populates="registrations")
    student = db.relationship("Student", back_populates="registrations")


class EventExpense(db.Model):
    __tablename__ = "event_expenses"
    expense_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.event_id", ondelete="RESTRICT"), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    expense_date = db.Column(db.Date, nullable=False, index=True)
    __table_args__ = (
        db.CheckConstraint("amount >= 0", name="nonnegative_amount"),
        db.CheckConstraint("length(trim(description)) > 0", name="description_not_blank"),
    )
    event = db.relationship("Event", back_populates="expenses")
