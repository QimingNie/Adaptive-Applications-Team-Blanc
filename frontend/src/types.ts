export type Bucket = "now" | "read" | "skim" | "later";
export type FeedbackType =
  | "important"
  | "not_important"
  | "mute_sender"
  | "remind_sender";
export type ViewMode = "busy" | "normal";

export interface EmailItem {
  id: number;
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
}

export interface InboxResponse {
  bucket: Bucket;
  items: EmailItem[];
}
