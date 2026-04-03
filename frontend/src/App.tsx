import { useEffect, useMemo, useRef, useState } from "react";
import {
  clearStoredUserEmail,
  getAuthStatus,
  getEmail,
  getGoogleAuthUrl,
  getInbox,
  getStoredUserEmail,
  seedInbox,
  sendFeedback,
  setStoredUserEmail,
  trackEvent
} from "./api";
import { BucketTabs } from "./components/BucketTabs";
import { EmailDetail } from "./components/EmailDetail";
import { EmailList } from "./components/EmailList";
import type { Bucket, EmailItem, FeedbackType, ViewMode } from "./types";
import "./styles.css";

const DEMO_FOCUS_MODE_KEY = "smart_inbox_demo_focus_mode";
const DEMO_FOCUS_COUNT = 6;
const DEMO_DEFAULT_COUNT = 32;

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
  const [mode, setMode] = useState<ViewMode>("busy");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [authEmail, setAuthEmail] = useState<string | null>(getStoredUserEmail());
  const [authConnected, setAuthConnected] = useState(false);
  const [demoFocusMode, setDemoFocusMode] = useState<boolean>(getStoredDemoFocusMode());
  const bootedRef = useRef(false);

  const selectedFromList = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId]
  );

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
        if (status.email) {
          setAuthEmail(status.email);
        } else if (!emailFromCallback) {
          clearStoredUserEmail();
          setAuthEmail(null);
        }

        const activeEmail = status.email ?? emailFromCallback;
        if (activeEmail) {
          await seedInbox(DEMO_DEFAULT_COUNT);
        } else {
          await seedInbox(getDemoSeedCount(demoFocusMode), { trimToCount: true });
        }
        await loadBucket("now");
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
    try {
      await syncDemoInbox("now");
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
        await trackEvent(selectedId, "open");
      } catch (e) {
        setError((e as Error).message);
      }
    };
    void loadDetail();
  }, [selectedId, mode]);

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
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <main className="app">
      <header className="header">
        <h1>Smart Inbox</h1>
        <p>Priority-focused inbox with Busy and Normal reading modes.</p>
        <div className="auth-bar">
          <span>{authEmail ? `Signed in: ${authEmail}` : "Using demo account"}</span>
          {!authConnected ? (
            <button className="feedback-btn" onClick={() => void onConnectGoogle()}>
              Connect Gmail
            </button>
          ) : null}
          {authEmail ? (
            <button className="feedback-btn" onClick={() => void onUseDemo()}>
              Switch to Demo
            </button>
          ) : null}
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
      {error ? <div className="error">{error}</div> : null}
      <section className="layout">
        <aside className="list-panel">
          {loading ? (
            <div className="empty">Loading...</div>
          ) : (
            <EmailList
              items={items}
              selectedId={selectedId}
              onSelect={(id) => setSelectedId(id)}
            />
          )}
        </aside>
        <EmailDetail
          email={selected ?? selectedFromList}
          mode={mode}
          onModeChange={setMode}
          onFeedback={(action) => void onFeedback(action)}
        />
      </section>
    </main>
  );
}

export default App;
