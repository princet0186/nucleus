# No persistent ORM models.
#
# Casualty identity tracking (CasualtyCard / TriageLog) was intentionally
# removed: Nucleus does not store who was affected or their situation.
# Mass-casualty handling produces triage-prioritization guidance only, with
# nothing identifiable persisted.
#
# This module is still imported by backend.db.session.init_db so that any
# future models registered against Base are picked up for table creation.
from backend.db.session import Base  # noqa: F401
