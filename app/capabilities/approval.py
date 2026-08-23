"""Project-owned approval status contract."""
from __future__ import annotations

from enum import StrEnum


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
