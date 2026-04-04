export type Bucket = "now" | "read" | "skim" | "later";
export type FeedbackType =
  | "important"
  | "not_important"
  | "mute_sender"
  | "remind_sender";
export type ViewMode = "busy" | "normal";
export type ModelSource = "baseline" | "explicit" | "implicit" | "content" | "context" | "behavior";

export interface EmailItem {
  id: number;
  thread_id?: string;
  sender: string;
  subject: string;
  snippet: string;
  has_attachment: boolean;
  is_cc: boolean;
  received_at: string;
  score: number;
  bucket: Bucket;
  needs_action: boolean;
  body?: string;
  busy_summary?: string;
  action_items?: string;
  reason_summary?: string;
  model_summary?: string;
  score_breakdown?: ScoreBreakdownItem[];
}

export interface ThreadMessageItem {
  id: number;
  sender: string;
  subject: string;
  snippet: string;
  received_at: string;
}

export interface ThreadContextResponse {
  thread_id: string;
  current_email_id: number;
  messages: ThreadMessageItem[];
}

export interface InboxResponse {
  bucket: Bucket;
  items: EmailItem[];
}

export interface SendEmailInput {
  to: string;
  cc: string;
  subject: string;
  body: string;
  reply_to_email_id?: number | null;
}

export interface ScoreBreakdownItem {
  label: string;
  value: number;
  detail: string;
  source: ModelSource;
}

export interface FeatureWeightItem {
  key: string;
  label: string;
  description: string;
  value: number;
}

export interface SenderProfileItem {
  sender: string;
  explicit_state: string;
  learned_affinity: number;
  open_count: number;
  quick_close_count: number;
  reply_count: number;
  important_count: number;
  not_important_count: number;
  mute_count: number;
  remind_count: number;
  last_interaction_at?: string | null;
}

export interface ThreadProfileItem {
  thread_id: string;
  subject_hint: string;
  learned_affinity: number;
  open_count: number;
  quick_close_count: number;
  reply_count: number;
  important_count: number;
  not_important_count: number;
  mute_count: number;
  remind_count: number;
  last_interaction_at?: string | null;
}

export interface InteractionSummary {
  total_events: number;
  open_count: number;
  quick_close_count: number;
  reply_count: number;
  important_feedback_count: number;
  not_important_feedback_count: number;
  mute_count: number;
  remind_count: number;
}

export interface UserModel {
  email: string;
  important_senders: string[];
  muted_senders: string[];
  feature_weights: FeatureWeightItem[];
  sender_profiles: SenderProfileItem[];
  thread_profiles: ThreadProfileItem[];
  interaction_summary: InteractionSummary;
  scrutability_notes: string[];
}

export interface UserModelUpdateInput {
  important_senders: string[];
  muted_senders: string[];
  feature_weights: Record<string, number>;
}
