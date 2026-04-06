import type {
  Bucket,
  EmailItem,
  FeedbackType,
  InboxResponse,
  SendEmailInput,
  ThreadContextResponse,
  UserModel,
  UserModelUpdateInput,
  ViewMode
} from "./types";

const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ||
  "http://127.0.0.1:8010/api";
const USER_EMAIL_KEY = "smart_inbox_user_email";

interface SeedInboxOptions {
  trimToCount?: boolean;
  /** Gmail sync can take a long time (many API round-trips); demo uses the default. */
  syncTimeoutMs?: number;
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

/** Same identity as X-User-Email; some browsers/extensions drop custom headers on GET. */
function withUserQuery(pathWithQuery: string): string {
  const email = localStorage.getItem(USER_EMAIL_KEY);
  if (!email) return pathWithQuery;
  const joiner = pathWithQuery.includes("?") ? "&" : "?";
  return `${pathWithQuery}${joiner}user_email=${encodeURIComponent(email)}`;
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

export async function getAuthStatus(): Promise<{
  connected: boolean;
  email: string | null;
  can_send: boolean;
}> {
  return parse<{
    connected: boolean;
    email: string | null;
    can_send: boolean;
  }>(
    await fetch(withUserQuery(`${API_BASE}/auth/status`), {
      headers: getHeaders()
    })
  );
}

const SYNC_TIMEOUT_MS = 120_000;
/** Gmail list+fetch does many API calls; allow the server to finish before the client aborts. */
export const GMAIL_SYNC_TIMEOUT_MS = 360_000;

export async function seedInbox(seedCount = 24, options: SeedInboxOptions = {}): Promise<void> {
  const timeoutMs = options.syncTimeoutMs ?? SYNC_TIMEOUT_MS;
  const controller = new AbortController();
  const t = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    await parse(
      await fetch(withUserQuery(`${API_BASE}/sync/run`), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getHeaders() },
        body: JSON.stringify({
          seed_count: seedCount,
          trim_to_count: options.trimToCount ?? false
        }),
        signal: controller.signal
      })
    );
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      throw new Error(
      "Sync timed out. Your inbox may still be updating on the server — try Sync again in a moment."
    );
    }
    throw e;
  } finally {
    window.clearTimeout(t);
  }
}

const ALL_BUCKETS: Bucket[] = ["now", "read", "skim", "later"];

function mergeInboxByDate(targetBucket: Bucket, parts: InboxResponse[]): InboxResponse {
  const byId = new Map<number, EmailItem>();
  for (const part of parts) {
    for (const item of part.items) {
      byId.set(item.id, item);
    }
  }
  const items = Array.from(byId.values())
    .sort((a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime())
    .slice(0, 200);
  return { bucket: targetBucket, items };
}

export async function getInbox(
  bucket: Bucket,
  listView: ViewMode = "busy",
  options?: { signal?: AbortSignal }
): Promise<InboxResponse> {
  const view = listView === "normal" ? "normal" : "busy";
  const normalExtra = listView === "normal" ? "&all_messages=true" : "";
  const res = await fetch(
    withUserQuery(
      `${API_BASE}/inbox?bucket=${encodeURIComponent(bucket)}&view=${encodeURIComponent(view)}${normalExtra}`
    ),
    {
      headers: getHeaders(),
      cache: "no-store",
      signal: options?.signal
    }
  );
  let data = await parse<InboxResponse>(res);

  // Older API builds ignore `view`/`all_messages` and only filter by `bucket`, so Normal looked
  // empty while mail sat in other zones. Merge all buckets when the primary normal list is empty.
  if (listView === "normal" && (!data.items || data.items.length === 0)) {
    const signal = options?.signal;
    const partials = await Promise.all(
      ALL_BUCKETS.map((b) =>
        fetch(
          withUserQuery(`${API_BASE}/inbox?bucket=${encodeURIComponent(b)}`),
          { headers: getHeaders(), cache: "no-store", signal }
        ).then((r) => parse<InboxResponse>(r))
      )
    );
    data = mergeInboxByDate(bucket, partials);
  }

  return data;
}

export async function getEmail(emailId: number, mode: ViewMode): Promise<EmailItem> {
  return parse<EmailItem>(
    await fetch(withUserQuery(`${API_BASE}/emails/${emailId}?mode=${mode}`), {
      headers: getHeaders()
    })
  );
}

export async function getEmailThread(emailId: number): Promise<ThreadContextResponse> {
  return parse<ThreadContextResponse>(
    await fetch(withUserQuery(`${API_BASE}/emails/${emailId}/thread`), {
      headers: getHeaders()
    })
  );
}

export async function sendFeedback(emailId: number, feedbackType: FeedbackType): Promise<void> {
  await parse(
    await fetch(withUserQuery(`${API_BASE}/emails/${emailId}/feedback`), {
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
    await fetch(withUserQuery(`${API_BASE}/events`), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getHeaders() },
      body: JSON.stringify({ email_id: emailId, event_type: eventType, dwell_ms: dwellMs })
    })
  );
}

export async function sendEmail(payload: SendEmailInput): Promise<void> {
  await parse(
    await fetch(withUserQuery(`${API_BASE}/mail/send`), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getHeaders() },
      body: JSON.stringify(payload)
    })
  );
}

export async function getUserModel(): Promise<UserModel> {
  return parse<UserModel>(
    await fetch(withUserQuery(`${API_BASE}/model`), {
      headers: getHeaders()
    })
  );
}

export async function updateUserModel(payload: UserModelUpdateInput): Promise<UserModel> {
  return parse<UserModel>(
    await fetch(withUserQuery(`${API_BASE}/model`), {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...getHeaders() },
      body: JSON.stringify(payload)
    })
  );
}
