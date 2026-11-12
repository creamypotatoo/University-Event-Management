"""Membership lifecycle rules; callers lock the owning Club until commit."""

from flask import abort

from app.extensions import db
from app.models import ClubMembership


def transition_membership(membership, club, target):
    if target not in {"active", "cancelled"}:
        abort(400, description="Choose active or cancelled membership status.")
    if target == "active" and not club.is_active:
        abort(409, description="This club is inactive and cannot accept or reactivate memberships.")
    membership.status = target
    return membership


def student_membership(club, student, target):
    record = db.session.scalar(db.select(ClubMembership).where(
        ClubMembership.club_id == club.club_id, ClubMembership.student_id == student.student_id
    ).with_for_update())
    if record is None:
        if target == "cancelled":
            return None  # Leaving a club never creates a membership row.
        record = ClubMembership(club_id=club.club_id, student_id=student.student_id)
        db.session.add(record)
    return transition_membership(record, club, target)
