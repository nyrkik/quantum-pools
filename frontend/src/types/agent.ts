/**
 * Shared TypeScript interfaces for agent-related features (inbox, jobs, dashboard).
 */

export interface AgentAction {
  id: string;
  agent_message_id: string;
  thread_id?: string | null;
  case_id?: string | null;
  case_number?: string | null;
  case_title?: string | null;
  action_type: string;
  description: string;
  assigned_to: string | null;
  due_date: string | null;
  status: string;
  job_path?: "internal" | "customer";
  invoice_ids?: string[];
  task_count?: number;
  tasks_completed?: number;
  completed_at: string | null;
  created_at: string | null;
  from_email?: string;
  customer_name?: string;
  subject?: string;
}

export interface ActionComment {
  id: string;
  author: string;
  text: string;
  created_at: string;
}

export interface RelatedJob {
  id: string;
  action_type: string;
  description: string;
  status: string;
  comments: { author: string; text: string }[];
}

export interface JobTask {
  id: string;
  title: string;
  assigned_to: string | null;
  status: string;
  sort_order: number;
  due_date: string | null;
  completed_by: string | null;
  created_by: string | null;
}

export interface ActionDetail extends AgentAction {
  comments?: ActionComment[];
  notes?: string | null;
  invoice_ids?: string[];
  matched_customer_id?: string | null;
  task_count?: number;
  tasks_completed?: number;
  tasks?: JobTask[];
  from_email?: string;
  customer_name?: string;
  subject?: string;
  email_body?: string;
  our_response?: string;
  response_is_draft?: boolean;
  thread_messages?: { direction: string; from_email: string; to_email: string; subject: string; body: string; created_at: string }[];
  related_jobs?: RelatedJob[];
}

export interface AgentStats {
  total: number;
  pending: number;
  sent: number;
  rejected: number;
  ignored: number;
  by_category: Record<string, number>;
  by_urgency: Record<string, number>;
  recent_24h: number;
  open_actions: number;
  overdue_actions: number;
  avg_response_seconds: number | null;
  stale_pending: number;
}

export interface Thread {
  id: string;
  contact_email: string;
  subject: string | null;
  customer_name: string | null;
  contact_name: string | null;
  customer_address: string | null;
  matched_customer_id: string | null;
  case_id: string | null;
  case_number?: string | null;
  case_title?: string | null;
  status: string;
  urgency: string | null;
  category: string | null;
  message_count: number;
  last_message_at: string | null;
  last_direction: string;
  last_snippet: string | null;
  has_pending: boolean;
  has_open_actions: boolean;
  assigned_to_user_id: string | null;
  assigned_to_name: string | null;
  assigned_at: string | null;
  is_unread: boolean;
  visibility_role_slugs: string[] | null;
  delivered_to: string | null;
  sender_tag: string | null;
  contact_person_name?: string | null;
  // Most recent OUTBOUND from_name on the thread. Used by the inbox row
  // to show "↑ Kim replied" so teammates see who responded last without
  // opening the thread (FB-50). Null when the latest outbound has no
  // from_name (very old rows).
  last_outbound_from_name?: string | null;
  // Sticky AI marker — true once the classifier auto-closed this thread,
  // never clears. Drives the "AI" row pill in every Handled view.
  was_auto_handled?: boolean;
  // Subset: AI auto-closed AND the user hasn't ack'd the in-thread feedback
  // banner yet. Banner stops rendering once this flips false.
  is_auto_handled?: boolean;
  // Phase 3 — cached AI summary payload. Null when no summary has been
  // generated (short thread, low confidence, or inbox_v2 off for org).
  ai_summary_payload?: {
    version: number;
    ask: string | null;
    state: string | null;
    open_items: string[];
    red_flags: string[];
    linked_refs: { type: string; id: string; label?: string | null }[];
    confidence: number;
    proposal_ids: string[];
  } | null;
}

export interface TimelineMessage {
  id: string;
  direction: string;
  from_email: string;
  from_name?: string | null;
  to_email: string;
  subject: string | null;
  body: string | null;
  body_html?: string | null;
  category: string | null;
  urgency: string | null;
  status: string;
  // Phase 5 Step 5 closeout: AI drafts live exclusively on staged
  // `email_reply` proposals — the UI renders <ProposalCard/> here.
  email_reply_proposal_id?: string | null;
  received_at: string | null;
  sent_at: string | null;
  approved_by: string | null;
  delivery_status?: string | null;
  delivery_error?: string | null;
  first_opened_at?: string | null;
  open_count?: number;
  attachments?: { id: string; filename: string; url: string; mime_type: string; file_size: number }[];
}

export interface ThreadDetail {
  id: string;
  contact_email: string;
  subject: string | null;
  customer_name: string | null;
  matched_customer_id: string | null;
  case_id: string | null;
  case_number?: string | null;
  case_title?: string | null;
  status: string;
  urgency: string | null;
  category: string | null;
  message_count: number;
  has_pending: boolean;
  has_open_actions: boolean;
  assigned_to_user_id: string | null;
  assigned_to_name: string | null;
  assigned_at: string | null;
  visibility_role_slugs: string[] | null;
  delivered_to: string | null;
  folder_id: string | null;
  is_unread: boolean;
  sender_tag: string | null;
  is_auto_handled?: boolean;
  was_auto_handled?: boolean;
  contact_person_name?: string | null;
  is_historical?: boolean;
  // Phase 5: present when an AI-drafted estimate is staged or already
  // accepted for this thread. Lets the UI render "View Draft →" or
  // "View Estimate →" instead of offering a fresh "Draft Estimate" click
  // that would silently hit the backend's existing-record short-circuit.
  pending_estimate_proposal_id?: string | null;
  linked_estimate_invoice_id?: string | null;
  timeline: TimelineMessage[];
  actions: unknown[];
}

export interface ServiceCase {
  id: string;
  case_number: string;
  title: string;
  customer_id: string | null;
  customer_name: string | null;
  billing_name: string | null;
  status: string;
  priority: string;
  assigned_to_name: string | null;
  manager_name: string | null;
  current_actor_name: string | null;
  source: string;
  job_count: number;
  open_job_count: number;
  thread_count: number;
  invoice_count: number;
  total_invoiced: number;
  total_paid: number;
  flags: {
    estimate_approved: boolean;
    estimate_rejected: boolean;
    payment_received: boolean;
    customer_replied: boolean;
    jobs_complete: boolean;
    invoice_overdue: boolean;
    stale: boolean;
  };
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface CaseJob {
  id: string;
  description: string;
  action_type: string;
  status: string;
  assigned_to: string | null;
  due_date: string | null;
  completed_at: string | null;
  created_at: string;
  closed_by_case_cascade?: boolean;
}

export interface CaseThread {
  id: string;
  subject: string | null;
  contact_email: string;
  status: string;
  message_count: number;
  last_snippet: string | null;
  last_message_at: string | null;
}

export interface CaseInvoice {
  id: string;
  invoice_number: string | null;
  document_type: string;
  subject: string | null;
  status: string;
  total: number;
  balance: number;
  created_at: string;
}

export interface CaseTimelineEntry {
  id: string;
  type: "email" | "comment" | "invoice_event" | "job_event" | "system";
  timestamp: string;
  title: string;
  body: string | null;
  actor: string | null;
  metadata: Record<string, unknown>;
}

export interface CaseDetail extends ServiceCase {
  jobs: CaseJob[];
  threads: CaseThread[];
  invoices: CaseInvoice[];
  timeline: CaseTimelineEntry[];
}

export interface AgentMessage {
  id: string;
  from_email: string;
  subject: string | null;
  category: string | null;
  status: string;
  customer_name: string | null;
  received_at: string | null;
}
