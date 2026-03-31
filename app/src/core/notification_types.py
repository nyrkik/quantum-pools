"""Centralized notification type constants.

Every notification type in the system is defined here. Do NOT use string
literals for notification types anywhere else.
"""

# Thread & Email
THREAD_ASSIGNED = "thread_assigned"

# Jobs
JOB_ASSIGNED = "job_assigned"
JOB_UPDATE = "job_update"
JOB_COMPLETED = "job_completed"
JOB_MENTION = "job_mention"

# Internal Messaging
INTERNAL_MESSAGE = "internal_message"
INTERNAL_MESSAGE_URGENT = "internal_message_urgent"
MESSAGE_ACKNOWLEDGED = "message_acknowledged"
MESSAGE_COMPLETED = "message_completed"

# System
FEEDBACK_SUBMITTED = "feedback_submitted"
EVAL_COMPLETE = "eval_complete"
