import { useEffect, useMemo, useRef, useState } from "react";
import {
  clearStoredUserEmail,
  getAuthStatus,
  getEmail,
  getGoogleAuthUrl,
  getInbox,
  getStoredUserEmail,
  getUserModel,
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

function App() {
  const [bucket, setBucket] = useState<Bucket>("now");
  const [items, setItems] = useState<EmailItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selected, setSelected] = useState<EmailItem | null>(null);
  const [mode, setMode] = useState<ViewMode>("normal");
  const [loading, setLoading] = useState(false);
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
  const selectedStartRef = useRef<number | null>(null);
  const lastSelectedIdRef = useRef<number | null>(null);

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

  async function loadBucket(target: Bucket, preferredId: number | null = null) {
    setLoading(true);
    setError("");
    try {
      const inbox = await getInbox(target);
      setItems(inbox.items);
      const nextSelectedId =
        preferredId != null && inbox.items.some((item) => item.id === preferredId)
          ? preferredId
          : (inbox.items[0]?.id ?? null);
      setSelectedId(nextSelectedId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
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
        const emailFromCallback = url.searchParams.get("email");
        if (emailFromCallback) {
          setStoredUserEmail(emailFromCallback);
          setAuthEmail(emailFromCallback);
          const cleanUrl = `${url.origin}/`;
          window.history.replaceState({}, "", cleanUrl);
        }

        const status = await getAuthStatus();
        setAuthConnected(status.connected);
        setCanSend(status.can_send);
        if (status.email) {
          setAuthEmail(status.email);
        } else if (!emailFromCallback) {
          clearStoredUserEmail();
          setAuthEmail(null);
          setCanSend(false);
        }

        const activeEmail = status.email ?? emailFromCallback;
        if (activeEmail) {
          await seedInbox(DEMO_DEFAULT_COUNT);
        } else {
          await seedInbox(getDemoSeedCount(demoFocusMode), { trimToCount: true });
        }
        await loadBucket("now");
        await loadUserModel(true);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    };
    void boot();
  }, []);

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
            <div className="auth-actions">
              {!authConnected ? (
                <button type="button" className="btn btn-primary" onClick={() => void onConnectGoogle()}>
                  Connect Gmail
                </button>
              ) : null}
              {authConnected && !canSend ? (
                <button type="button" className="btn btn-ghost" onClick={() => void onConnectGoogle()}>
                  Reconnect for send
                </button>
              ) : null}
              {authConnected ? (
                <button type="button" className="btn btn-ghost" onClick={onComposeNew}>
                  Compose
                </button>
              ) : null}
              <button
                type="button"
                className={`btn btn-ghost ${modelOpen ? "toggle-active" : ""}`}
                onClick={() => {
                  const next = !modelOpen;
                  setModelOpen(next);
                  if (next) {
                    void loadUserModel();
                  }
                }}
              >
                User model
              </button>
              {authEmail ? (
                <button type="button" className="btn btn-ghost" onClick={() => void onUseDemo()}>
                  Use demo
                </button>
              ) : null}
            </div>
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
      <BucketTabs value={bucket} onChange={(b) => void onBucketChange(b)} />
      {error ? <div className="error" role="alert">{error}</div> : null}
      <section className="layout" aria-label="Inbox layout">
        <aside className="list-panel" id="panel-inbox" role="tabpanel" aria-label="Message list">
          <div className="list-panel__head">
            <h2 className="list-panel__title">In this zone</h2>
            <span className="list-panel__count">{loading ? "…" : items.length}</span>
          </div>
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
              />
            )}
          </div>
        </aside>
        <div className="detail-stack">
          <EmailDetail
            email={activeEmail}
            mode={mode}
            canReply={authConnected && canSend}
            onModeChange={setMode}
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
