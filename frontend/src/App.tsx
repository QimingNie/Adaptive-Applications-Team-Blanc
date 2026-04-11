import { useEffect, useMemo, useRef, useState } from "react";
import {
  clearStoredUserEmail,
  getAuthStatus,
  getEmail,
  getGoogleAuthUrl,
  getInbox,
  getStoredUserEmail,
  getUserModel,
  GMAIL_SYNC_TIMEOUT_MS,
  seedInbox,
  sendEmail,
  sendFeedback,
  setStoredUserEmail,
  trackEvent,
  updateUserModel
} from "./api";
import { BucketTabs } from "./components/BucketTabs";
import { ComposePanel } from "./components/ComposePanel";
import { EmailDetail } from "./components/EmailDetail";
import { EmailList } from "./components/EmailList";
import { ModelInspector } from "./components/ModelInspector";
import type { Bucket, EmailItem, FeedbackType, UserModel, ViewMode } from "./types";
import "./styles.css";

const DEMO_FOCUS_MODE_KEY = "smart_inbox_demo_focus_mode";
const DEMO_FOCUS_COUNT = 6;
const DEMO_DEFAULT_COUNT = 32;
/** Gmail message fetches per sync (keep modest so the request returns before the client timeout). */
const GMAIL_SYNC_BATCH = 24;

interface ComposeDraft {
  to: string;
  cc: string;
  subject: string;
  body: string;
  replyToEmailId: number | null;
}

function createEmptyDraft(): ComposeDraft {
  return {
    to: "",
    cc: "",
    subject: "",
    body: "",
    replyToEmailId: null
  };
}

function buildReplySubject(subject: string) {
  return /^re:/i.test(subject) ? subject : `Re: ${subject}`;
}

function buildReplyBody(email: EmailItem) {
  const source = (email.body || email.snippet || "").trim();
  if (!source) {
    return "";
  }
  const quoted = source
    .split(/\r?\n/)
    .map((line) => `> ${line}`)
    .join("\n");
  return `\n\nOn ${new Date(email.received_at).toLocaleString()}, ${email.sender} wrote:\n${quoted}`;
}

function parseSenderList(value: string) {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function getStoredDemoFocusMode(): boolean {
  return localStorage.getItem(DEMO_FOCUS_MODE_KEY) === "true";
}

function setStoredDemoFocusMode(enabled: boolean) {
  localStorage.setItem(DEMO_FOCUS_MODE_KEY, enabled ? "true" : "false");
}

function isAbortError(e: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" && e instanceof DOMException && e.name === "AbortError") ||
    (e instanceof Error && e.name === "AbortError")
  );
}

function App() {
  const [bucket, setBucket] = useState<Bucket>("now");
  const [items, setItems] = useState<EmailItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selected, setSelected] = useState<EmailItem | null>(null);
  const [mode, setMode] = useState<ViewMode>("normal");
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string>("");
  const [authEmail, setAuthEmail] = useState<string | null>(getStoredUserEmail());
  const [authConnected, setAuthConnected] = useState(false);
  const [canSend, setCanSend] = useState(false);
  const [demoFocusMode, setDemoFocusMode] = useState<boolean>(getStoredDemoFocusMode());
  const [composerOpen, setComposerOpen] = useState(false);
  const [draft, setDraft] = useState<ComposeDraft>(createEmptyDraft());
  const [sendingEmail, setSendingEmail] = useState(false);
  const [sendStatus, setSendStatus] = useState("");
  const [modelOpen, setModelOpen] = useState(false);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelSaving, setModelSaving] = useState(false);
  const [userModel, setUserModel] = useState<UserModel | null>(null);
  const [importantDraft, setImportantDraft] = useState("");
  const [mutedDraft, setMutedDraft] = useState("");
  const [weightDraft, setWeightDraft] = useState<Record<string, string>>({});
  const bootedRef = useRef(false);
  const bootCompleteRef = useRef(false);
  const selectedStartRef = useRef<number | null>(null);
  const lastSelectedIdRef = useRef<number | null>(null);
  const inboxFetchAbortRef = useRef<AbortController | null>(null);
  /** Only the latest inbox fetch may update list state (avoids stale empty responses after sync). */
  const inboxFetchGenerationRef = useRef(0);
  const modeRef = useRef(mode);
  const bucketRef = useRef(bucket);
  const selectedIdRef = useRef(selectedId);
  modeRef.current = mode;
  bucketRef.current = bucket;
  selectedIdRef.current = selectedId;

  const selectedFromList = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId]
  );
  const activeEmail = selected ?? selectedFromList;

  function applyModelDrafts(model: UserModel) {
    setImportantDraft(model.important_senders.join(", "));
    setMutedDraft(model.muted_senders.join(", "));
    setWeightDraft(
      Object.fromEntries(model.feature_weights.map((weight) => [weight.key, String(weight.value)]))
    );
  }

  async function loadUserModel(silent = false) {
    if (!silent) {
      setModelLoading(true);
    }
    try {
      const model = await getUserModel();
      setUserModel(model);
      applyModelDrafts(model);
    } catch (e) {
      if (!silent) {
        setError((e as Error).message);
      }
    } finally {
      if (!silent) {
        setModelLoading(false);
      }
    }
  }

  async function loadBucket(
    target: Bucket,
    preferredId: number | null = null,
    opts?: { showLoading?: boolean; listView?: ViewMode }
  ) {
    const showLoading = opts?.showLoading !== false;
    const listView = opts?.listView ?? modeRef.current;
    const generation = ++inboxFetchGenerationRef.current;
    inboxFetchAbortRef.current?.abort();
    const ac = new AbortController();
    inboxFetchAbortRef.current = ac;
    if (showLoading) {
      setLoading(true);
    }
    setError("");
    try {
      const inbox = await getInbox(target, listView, { signal: ac.signal });
      if (generation !== inboxFetchGenerationRef.current) {
        return;
      }
      setItems(inbox.items);
      const nextSelectedId =
        preferredId != null && inbox.items.some((item) => item.id === preferredId)
          ? preferredId
          : (inbox.items[0]?.id ?? null);
      setSelectedId(nextSelectedId);
    } catch (e) {
      if (isAbortError(e)) {
        return;
      }
      setError((e as Error).message);
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }

  function getDemoSeedCount(focusMode: boolean) {
    return focusMode ? DEMO_FOCUS_COUNT : DEMO_DEFAULT_COUNT;
  }

  async function syncDemoInbox(targetBucket: Bucket, focusMode = demoFocusMode) {
    await seedInbox(getDemoSeedCount(focusMode), { trimToCount: true });
    setBucket(targetBucket);
    await loadBucket(targetBucket);
  }

  useEffect(() => {
    if (bootedRef.current) {
      return;
    }
    bootedRef.current = true;

    const boot = async () => {
      setLoading(true);
      try {
        const url = new URL(window.location.href);
        const emailFromOAuth = url.searchParams.get("email");

        if (emailFromOAuth) {
          setStoredUserEmail(emailFromOAuth);
          const cleanUrl = `${url.origin}/`;
          window.history.replaceState({}, "", cleanUrl);
        }

        const status = await getAuthStatus();
        setAuthConnected(status.connected);
        setCanSend(status.can_send);

        const norm = (e: string | null | undefined) => (e && e.trim().toLowerCase()) || "";
        // status.email ?? OAuth query ?? localStorage — only clear storage if all three are empty
        const resolvedEmail =
          norm(status.email) || norm(emailFromOAuth) || norm(getStoredUserEmail()) || null;

        if (resolvedEmail) {
          setAuthEmail(resolvedEmail);
          setStoredUserEmail(resolvedEmail);
        } else {
          clearStoredUserEmail();
          setAuthEmail(null);
        }

        const activeEmail = resolvedEmail;

        await loadBucket("now", null, { showLoading: false });

        void loadUserModel(true);

        void (async () => {
          setSyncing(true);
          try {
            if (activeEmail) {
              await seedInbox(GMAIL_SYNC_BATCH, {
                trimToCount: false,
                syncTimeoutMs: GMAIL_SYNC_TIMEOUT_MS
              });
            } else {
              await seedInbox(getDemoSeedCount(demoFocusMode), { trimToCount: true });
            }
          } catch (e) {
            setError((e as Error).message);
          } finally {
            try {
              await loadBucket(bucketRef.current, selectedIdRef.current, { showLoading: false });
            } catch (loadErr) {
              if (!isAbortError(loadErr)) {
                setError((loadErr as Error).message);
              }
            }
            setSyncing(false);
          }
        })();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
        bootCompleteRef.current = true;
      }
    };
    void boot();
  }, []);

  useEffect(() => {
    if (!bootCompleteRef.current) {
      return;
    }
    void loadBucket(bucket, selectedId, { showLoading: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload list when reading mode changes; bucket/selection handled elsewhere
  }, [mode]);

  async function onConnectGoogle() {
    try {
      const authUrl = await getGoogleAuthUrl();
      window.location.href = authUrl;
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onUseDemo() {
    clearStoredUserEmail();
    setAuthEmail(null);
    setAuthConnected(false);
    setCanSend(false);
    setComposerOpen(false);
    setDraft(createEmptyDraft());
    setSendStatus("");
    try {
      await syncDemoInbox("now");
      await loadUserModel(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onRefreshDemoInbox() {
    setSyncing(true);
    setError("");
    try {
      await seedInbox(getDemoSeedCount(demoFocusMode), { trimToCount: true });
      await loadBucket(bucket, selectedId, { showLoading: false });
      await loadUserModel(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  async function onSyncInbox() {
    setSyncing(true);
    setError("");
    try {
      await seedInbox(GMAIL_SYNC_BATCH, {
        trimToCount: false,
        syncTimeoutMs: GMAIL_SYNC_TIMEOUT_MS
      });
      await loadUserModel(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      try {
        await loadBucket(bucketRef.current, selectedIdRef.current, { showLoading: false });
      } catch (loadErr) {
        if (!isAbortError(loadErr)) {
          setError((loadErr as Error).message);
        }
      }
      setSyncing(false);
    }
  }

  async function onDemoFocusModeChange(enabled: boolean) {
    const previous = demoFocusMode;
    setDemoFocusMode(enabled);
    setStoredDemoFocusMode(enabled);

    try {
      await syncDemoInbox("now", enabled);
      await loadUserModel(true);
    } catch (e) {
      setDemoFocusMode(previous);
      setStoredDemoFocusMode(previous);
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    if (selectedId == null) {
      setSelected(null);
      return;
    }
    const loadDetail = async () => {
      try {
        const detail = await getEmail(selectedId, mode);
        setSelected(detail);
      } catch (e) {
        setError((e as Error).message);
      }
    };
    void loadDetail();
  }, [selectedId, mode]);

  useEffect(() => {
    const previousId = lastSelectedIdRef.current;
    const previousStarted = selectedStartRef.current;
    if (previousId != null && previousStarted != null && previousId !== selectedId) {
      const dwellMs = Date.now() - previousStarted;
      if (dwellMs < 6000) {
        void trackEvent(previousId, "quick_close", dwellMs).then(() => {
          if (modelOpen) {
            void loadUserModel(true);
          }
        });
      }
    }

    if (selectedId == null) {
      lastSelectedIdRef.current = null;
      selectedStartRef.current = null;
      return;
    }

    lastSelectedIdRef.current = selectedId;
    selectedStartRef.current = Date.now();
    void trackEvent(selectedId, "open").then(() => {
      if (modelOpen) {
        void loadUserModel(true);
      }
    });
  }, [selectedId]);

  async function onBucketChange(next: Bucket) {
    setBucket(next);
    await loadBucket(next);
  }

  async function onFeedback(action: FeedbackType) {
    if (!selected) {
      return;
    }
    try {
      await sendFeedback(selected.id, action);
      const updated = await getEmail(selected.id, mode);
      setSelected(updated);
      if (updated.bucket !== bucket) {
        setBucket(updated.bucket);
      }
      await loadBucket(updated.bucket, updated.id);
      await loadUserModel(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function onComposeNew() {
    setComposerOpen(true);
    setSendStatus("");
    setDraft(createEmptyDraft());
  }

  function onReply() {
    if (!activeEmail) {
      return;
    }
    setComposerOpen(true);
    setSendStatus("");
    setDraft({
      to: activeEmail.sender,
      cc: "",
      subject: buildReplySubject(activeEmail.subject),
      body: buildReplyBody(activeEmail),
      replyToEmailId: activeEmail.id
    });
  }

  function onComposeFieldChange(field: "to" | "cc" | "subject" | "body", value: string) {
    setDraft((current) => ({
      ...current,
      [field]: value
    }));
  }

  function onCloseComposer() {
    setComposerOpen(false);
    setDraft(createEmptyDraft());
  }

  async function onSendEmail() {
    setSendingEmail(true);
    setError("");
    setSendStatus("");
    try {
      await sendEmail({
        to: draft.to,
        cc: draft.cc,
        subject: draft.subject,
        body: draft.body,
        reply_to_email_id: draft.replyToEmailId
      });
      if (draft.replyToEmailId != null) {
        await trackEvent(draft.replyToEmailId, "reply");
      }
      setComposerOpen(false);
      setDraft(createEmptyDraft());
      setSendStatus("Email sent.");
      await loadUserModel(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSendingEmail(false);
    }
  }

  async function onSaveModel() {
    setModelSaving(true);
    setError("");
    try {
      const featureWeights = Object.fromEntries(
        Object.entries(weightDraft)
          .map(([key, value]) => [key, Number.parseFloat(value)])
          .filter(([, value]) => Number.isFinite(value))
      );
      const updated = await updateUserModel({
        important_senders: parseSenderList(importantDraft),
        muted_senders: parseSenderList(mutedDraft),
        feature_weights: featureWeights
      });
      setUserModel(updated);
      applyModelDrafts(updated);
      await loadBucket(bucket, selectedId);
      if (selectedId != null) {
        const detail = await getEmail(selectedId, mode);
        setSelected(detail);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setModelSaving(false);
    }
  }

  function onResetModelDrafts() {
    if (userModel) {
      applyModelDrafts(userModel);
    }
  }

  return (
    <main className="app">
      <div className="app-backdrop" aria-hidden="true" />
      {import.meta.env.DEV ? (
        <div className="dev-server-hint" role="status">
          Development: open <strong>http://127.0.0.1:5173</strong> (must match the Gmail redirect URL). Only one{" "}
          <code>npm run dev</code> at a time; if the port is busy, stop other Vite/Node dev servers, then restart. OAuth always
          sends you back to port <strong>5173</strong>, not 5174+.
        </div>
      ) : null}
      <header className="header">
        <div className="header-main">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true" />
            <div className="brand-text">
              <p className="brand-eyebrow">Adaptive application</p>
              <h1 className="brand-title">Smart Inbox</h1>
              <p className="brand-tagline">
                Priority zones and reading modes that adjust to how you work — not the other way around.
              </p>
            </div>
          </div>
          <div className="auth-card">
            <div className="auth-status">
              <span
                className={`auth-dot ${authEmail && authConnected ? "auth-dot--live" : ""}`}
                aria-hidden
              />
              <span className="auth-label">
                {authEmail ? (
                  <>
                    <span className="auth-strong">
                      {authConnected
                        ? canSend
                          ? "Gmail connected"
                          : "Gmail (read-only)"
                        : "Signed in"}
                    </span>
                    <span className="auth-email">
                      {authEmail}
                      {authConnected && !canSend
                        ? " — reconnect and approve send access to compose."
                        : ""}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="auth-strong">Demo mode</span>
                    <span className="auth-email">Sample inbox — connect Gmail when you are ready</span>
                  </>
                )}
              </span>
            </div>
            <div className="auth-mode-toggle" role="group" aria-label="Inbox view mode">
              <button
                type="button"
                className={mode === "normal" ? "auth-mode-btn auth-mode-btn--active" : "auth-mode-btn"}
                onClick={() => setMode("normal")}
              >
                Normal
              </button>
              <button
                type="button"
                className={mode === "busy" ? "auth-mode-btn auth-mode-btn--active" : "auth-mode-btn"}
                onClick={() => setMode("busy")}
              >
                Busy
              </button>
            </div>
            <div className="auth-actions" role="toolbar" aria-label="Account actions">
              {authEmail && !authConnected ? (
                <button type="button" className="btn btn-primary auth-actions__full" onClick={() => void onConnectGoogle()}>
                  Reconnect Gmail
                </button>
              ) : null}
              {authConnected && !canSend ? (
                <button type="button" className="btn btn-ghost auth-actions__full" onClick={() => void onConnectGoogle()}>
                  Reconnect for send
                </button>
              ) : null}
              <div className="auth-row3">
                {authConnected ? (
                  <button
                    type="button"
                    className="btn btn-ghost auth-row3__btn"
                    title="Sync inbox from Gmail"
                    onClick={() => void onSyncInbox()}
                    disabled={syncing}
                  >
                    {syncing ? "…" : "Sync"}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-ghost auth-row3__btn"
                    title="Reload sample emails"
                    onClick={() => void onRefreshDemoInbox()}
                    disabled={syncing}
                  >
                    {syncing ? "…" : "Refresh"}
                  </button>
                )}
                <button
                  type="button"
                  className={`btn btn-ghost auth-row3__btn ${modelOpen ? "toggle-active" : ""}`}
                  title="User model inspector"
                  onClick={() => {
                    const next = !modelOpen;
                    setModelOpen(next);
                    if (next) {
                      void loadUserModel();
                    }
                  }}
                >
                  Learning
                </button>
                {authEmail && authConnected ? (
                  <button
                    type="button"
                    className="btn btn-ghost auth-row3__btn"
                    title="Switch to sample inbox"
                    onClick={() => void onUseDemo()}
                  >
                    Demo
                  </button>
                ) : authEmail && !authConnected ? (
                  <button
                    type="button"
                    className="btn btn-ghost auth-row3__btn"
                    title="Use sample inbox (sign out Gmail)"
                    onClick={() => void onUseDemo()}
                  >
                    Demo
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-primary auth-row3__btn auth-row3__btn--primary"
                    title="Connect Google account"
                    onClick={() => void onConnectGoogle()}
                  >
                    Gmail
                  </button>
                )}
              </div>
            </div>
            {syncing ? <p className="auth-sync-hint" aria-live="polite">Updating inbox…</p> : null}
          </div>
        </div>
        {!authEmail ? (
          <div className="demo-controls">
            <label className="demo-toggle">
              <input
                type="checkbox"
                checked={demoFocusMode}
                disabled={loading}
                onChange={(event) => void onDemoFocusModeChange(event.target.checked)}
              />
              <span>Focus mode</span>
            </label>
            <span className="demo-note">
              {demoFocusMode
                ? `Keeping ${DEMO_FOCUS_COUNT} demo emails so score changes are easier to watch.`
                : `Keeping ${DEMO_DEFAULT_COUNT} demo emails for the fuller demo inbox.`}
            </span>
          </div>
        ) : null}
      </header>
      {mode === "busy" ? <BucketTabs value={bucket} onChange={(b) => void onBucketChange(b)} /> : null}
      {error ? <div className="error" role="alert">{error}</div> : null}
      <section className="layout" aria-label="Inbox layout">
        <aside
          className="list-panel"
          id="panel-inbox"
          role={mode === "busy" ? "tabpanel" : "region"}
          aria-label={mode === "busy" ? "Messages in selected zone" : "All messages"}
        >
          <div className="list-panel__head">
            <h2 className="list-panel__title">
              {mode === "normal" ? "All messages" : "In this zone"}
            </h2>
            <span className="list-panel__count">{loading || syncing ? "…" : items.length}</span>
          </div>
          {mode === "normal" ? <p className="list-panel__hint">Newest first — full messages on the right.</p> : null}
          <div className="list-panel__body">
            {loading ? (
              <div className="skeleton-list" aria-busy="true" aria-label="Loading messages">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} className="skeleton-row" />
                ))}
              </div>
            ) : (
              <EmailList
                items={items}
                selectedId={selectedId}
                onSelect={(id) => setSelectedId(id)}
                showAdaptiveMeta={mode === "busy"}
              />
            )}
          </div>
        </aside>
        <div className="detail-stack">
          <EmailDetail
            email={activeEmail}
            mode={mode}
            canReply={authConnected && canSend}
            onFeedback={(action) => void onFeedback(action)}
            onReply={onReply}
            onOpenThreadMessage={(id) => setSelectedId(id)}
          />
          <ModelInspector
            isOpen={modelOpen}
            loading={modelLoading}
            saving={modelSaving}
            model={userModel}
            importantDraft={importantDraft}
            mutedDraft={mutedDraft}
            weightDraft={weightDraft}
            onImportantChange={setImportantDraft}
            onMutedChange={setMutedDraft}
            onWeightChange={(key, value) =>
              setWeightDraft((current) => ({
                ...current,
                [key]: value
              }))
            }
            onSave={() => void onSaveModel()}
            onReset={onResetModelDrafts}
          />
          <ComposePanel
            isOpen={composerOpen}
            connected={authConnected}
            canSend={canSend}
            sending={sendingEmail}
            statusMessage={sendStatus}
            selectedEmail={activeEmail}
            to={draft.to}
            cc={draft.cc}
            subject={draft.subject}
            body={draft.body}
            onOpenNew={onComposeNew}
            onOpenReply={onReply}
            onClose={onCloseComposer}
            onReconnect={() => void onConnectGoogle()}
            onFieldChange={onComposeFieldChange}
            onSend={() => void onSendEmail()}
          />
        </div>
      </section>
    </main>
  );
}

export default App;
