"""AI Customer Support Agent — modular agent package.

Re-exports key functions for convenient top-level access.
"""

from .orchestrator import process_incoming_email, handle_sms_reply, save_discovered_contact, auto_close_stale_visits
from .triage_agent import ai_triage
from .customer_matcher import verify_customer_match
from .thread_manager import get_or_create_thread, update_thread_status
from .job_manager import evaluate_next_action
from .communicator import send_email_response, send_sms, send_approval_request, notify_others
from .customer_matcher import match_customer
from .classifier import classify_and_draft, get_correction_history, build_context_prompt, SYSTEM_PROMPT
from .mail_agent import decode_email_header, extract_text_body, strip_quoted_reply, strip_email_signature, _clean_html, _unwrap_embedded_mime
from .comment_pipeline import CommentPipeline
from .comment_classifier import classify_comment
from .deepblue_responder import DeepBlueResponder
from .command_executor import CommandExecutor
from .resolution_evaluator import ResolutionEvaluator

__all__ = [
    "process_incoming_email",
    "handle_sms_reply",
    "save_discovered_contact",
    "auto_close_stale_visits",
    "get_or_create_thread",
    "update_thread_status",
    "evaluate_next_action",
    "send_email_response",
    "send_sms",
    "send_approval_request",
    "notify_others",
    "match_customer",
    "classify_and_draft",
    "get_correction_history",
    "build_context_prompt",
    "SYSTEM_PROMPT",
    "decode_email_header",
    "extract_text_body",
    "strip_quoted_reply",
    "strip_email_signature",
    "_clean_html",
    "_unwrap_embedded_mime",
    "CommentPipeline",
    "classify_comment",
    "DeepBlueResponder",
    "CommandExecutor",
    "ResolutionEvaluator",
]
