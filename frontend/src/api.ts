import type { Bucket, FeedbackType, InboxResponse, ViewMode, EmailItem } from "./types";

const API_BASE = "http://127.0.0.1:8000/api";
const USER_EMAIL_KEY = "smart_inbox_user_email";

interface SeedInboxOptions {
  trimToCount?: boolean;
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Request failed");
  }
  return res.json() as Promise<T>;
}

function getHeaders() {
  const email = localStorage.getItem(USER_EMAIL_KEY);
  const headers: Record<string, string> = {};
  if (email) {
    headers["X-User-Email"] = email;
  }
  return headers;
}

export function getStoredUserEmail(): string | null {
  return localStorage.getItem(USER_EMAIL_KEY);
}

export function setStoredUserEmail(email: string) {
  localStorage.setItem(USER_EMAIL_KEY, email.trim().toLowerCase());
}

export function clearStoredUserEmail() {
  localStorage.removeItem(USER_EMAIL_KEY);
}

export async function getGoogleAuthUrl(): Promise<string> {
  const data = await parse<{ auth_url: string }>(await fetch(`${API_BASE}/auth/google/start`));
  return data.auth_url;
}

export async function getAuthStatus(): Promise<{ connected: boolean; email: string | null }> {
  return parse<{ connected: boolean; email: string | null }>(
    await fetch(`${API_BASE}/auth/status`, {
      headers: getHeaders()
    })
  );
}

export async function seedInbox(seedCount = 24, options: SeedInboxOptions = {}): Promise<void> {
  await parse(
    await fetch(`${API_BASE}/sync/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getHeaders() },
      body: JSON.stringify({
        seed_count: seedCount,
        trim_to_count: options.trimToCount ?? false
      })
    })
  );
}

export async function getInbox(bucket: Bucket): Promise<InboxResponse> {
  return parse<InboxResponse>(
    await fetch(`${API_BASE}/inbox?bucket=${bucket}`, {
      headers: getHeaders()
    })
  );
}

export async function getEmail(emailId: number, mode: ViewMode): Promise<EmailItem> {
  return parse<EmailItem>(
    await fetch(`${API_BASE}/emails/${emailId}?mode=${mode}`, {
      headers: getHeaders()
    })
  );
}

export async function sendFeedback(emailId: number, feedbackType: FeedbackType): Promise<void> {
  await parse(
    await fetch(`${API_BASE}/emails/${emailId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getHeaders() },
      body: JSON.stringify({ feedback_type: feedbackType })
    })
  );
}

export async function trackEvent(
  emailId: number,
  eventType: "open" | "quick_close" | "reply",
  dwellMs = 0
): Promise<void> {
  await parse(
    await fetch(`${API_BASE}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getHeaders() },
      body: JSON.stringify({ email_id: emailId, event_type: eventType, dwell_ms: dwellMs })
    })
  );
}
