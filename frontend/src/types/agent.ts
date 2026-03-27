/**
 * Shared TypeScript interfaces for agent-related features (inbox, jobs, dashboard).
 */

export interface AgentAction {
  id: string;
  agent_message_id: string;
  action_type: string;
  description: string;
  assigned_to: string | null;
  due_date: string | null;
  status: string;
  task_count?: number;
  tasks_completed?: number;
  completed_at: string | null;
  created_at: string | null;
  from_email?: string;
  customer_name?: string;
  subject?: string;
  is_suggested?: boolean;
  suggestion_confidence?: string | null;
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
  invoice_id?: string | null;
  matched_customer_id?: string | null;
  task_count?: number;
  tasks_completed?: number;
  tasks?: JobTask[];
  from_email?: string;
  customer_name?: string;
  subject?: string;
  email_body?: string;
  our_response?: string;
  related_jobs?: RelatedJob[];
}

export interface AgentStats {
  total: number;
  pending: number;
  sent: number;
  auto_sent: number;
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
  matched_customer_id: string | null;
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
  visibility_permission: string | null;
  delivered_to: string | null;
}

export interface TimelineMessage {
  id: string;
  direction: string;
  from_email: string;
  to_email: string;
  subject: string | null;
  body: string | null;
  category: string | null;
  urgency: string | null;
  status: string;
  draft_response: string | null;
  received_at: string | null;
  sent_at: string | null;
  approved_by: string | null;
}

export interface ThreadDetail {
  id: string;
  contact_email: string;
  subject: string | null;
  customer_name: string | null;
  status: string;
  urgency: string | null;
  category: string | null;
  message_count: number;
  has_pending: boolean;
  assigned_to_user_id: string | null;
  assigned_to_name: string | null;
  assigned_at: string | null;
  visibility_permission: string | null;
  delivered_to: string | null;
  routing_rule_id: string | null;
  timeline: TimelineMessage[];
  actions: unknown[];
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
