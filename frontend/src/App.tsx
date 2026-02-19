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
  const bootedRef = useRef(false);

  const selectedFromList = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId]
  );

  async function loadBucket(target: Bucket) {
    setLoading(true);
    setError("");
    try {
      const inbox = await getInbox(target);
      setItems(inbox.items);
      const firstId = inbox.items[0]?.id ?? null;
      setSelectedId(firstId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
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
        }

        await seedInbox(32);
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

  function onUseDemo() {
    clearStoredUserEmail();
    setAuthEmail(null);
    setAuthConnected(false);
    void loadBucket(bucket);
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
    await sendFeedback(selected.id, action);
    await loadBucket(bucket);
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
            <button className="feedback-btn" onClick={onUseDemo}>
              Switch to Demo
            </button>
          ) : null}
        </div>
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
