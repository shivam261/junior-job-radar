import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";

export type User = {
  id: string;
  email: string | null;
  username: string | null;
  name: string;
  role: "user" | "admin";
  active: number;
  created_at: string;
  last_login: string | null;
  alerts_enabled: number;
  alert_interval: number;
  alert_keywords: string;
  alert_location: string;
  last_email_at: string | null;
  email_error: string | null;
};
type AuthConfig = { google_enabled: boolean; mail_enabled: boolean };

export function AuthGate({
  children,
}: {
  children: (
    user: User,
    signOut: () => Promise<void>,
    update: (u: User) => void,
  ) => React.ReactNode;
}) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [settings, setSettings] = useState<AuthConfig | null>(null);
  const [master, setMaster] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(
    new URLSearchParams(window.location.search).has("auth_error")
      ? "Google sign-in was cancelled. Try again when ready."
      : "",
  );
  useEffect(() => {
    let active = true;
    api<User>("/auth/me")
      .then((u) => {
        if (active) setUser(u);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setChecking(false);
      });
    api<AuthConfig>("/auth/config")
      .then((c) => {
        if (active) setSettings(c);
      })
      .catch(() => {
        if (active)
          setError("Cannot reach the service. Please try again shortly.");
      });
    const expired = () => {
      setUser(null);
      setError("Your session expired. Please sign in again.");
    };
    window.addEventListener("session-expired", expired);
    return () => {
      active = false;
      window.removeEventListener("session-expired", expired);
    };
  }, []);
  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const u = await api<User>("/auth/master/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setPassword("");
      setUser(u);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    await api("/auth/logout", { method: "POST" });
    setUser(null);
    setPassword("");
    setError("");
  }
  if (checking)
    return (
      <main className="auth-screen">
        <p role="status">Opening your workspace…</p>
      </main>
    );
  if (user) return children(user, signOut, setUser);
  return (
    <main className="auth-screen">
      <section className="auth-card">
        <a className="auth-brand" href="/">
          launchpad.
        </a>
        <span className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</span>
        <h1>{master ? "Master account" : "Your next role starts here."}</h1>
        <p>
          {master
            ? "Sign in to manage accounts and career sources."
            : "Discover early-career jobs, keep your own shortlist, and receive fresh opportunities by email."}
        </p>
        {error && (
          <p className="account-message error" role="alert">
            {error}
          </p>
        )}
        {master ? (
          <form className="account-form" onSubmit={login}>
            <label>
              Username
              <input
                required
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                maxLength={100}
              />
            </label>
            <label>
              Password
              <input
                required
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                maxLength={256}
              />
            </label>
            <button className="button primary" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        ) : (
          <>
            {settings?.google_enabled ? (
              <a
                className="button primary google-signin"
                href="/api/auth/google"
              >
                Continue with Google
              </a>
            ) : (
              <p className="account-message">
                Google sign-in is waiting for the site owner to finish setup.
              </p>
            )}
            <p className="auth-note">
              New here? Google sign-in creates your account automatically.
              Returning? It signs you in. New accounts receive six-hourly job
              alerts; you can turn these off in your account.
            </p>
          </>
        )}
        <button
          className="auth-switch"
          onClick={() => {
            setMaster(!master);
            setError("");
          }}
        >
          {master ? "Back to Google sign-in" : "Master account sign-in"}
        </button>
      </section>
    </main>
  );
}

export function AccountPanel({
  user,
  onUpdate,
}: {
  user: User;
  onUpdate: (u: User) => void;
}) {
  const [enabled, setEnabled] = useState(!!user.alerts_enabled);
  const [interval, setIntervalValue] = useState(user.alert_interval);
  const [keywords, setKeywords] = useState(user.alert_keywords);
  const [location, setLocation] = useState(user.alert_location);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newUsername, setNewUsername] = useState(user.username || "");
  const [newPassword, setNewPassword] = useState("");
  useEffect(() => {
    api<{ configured: boolean }>("/account/email-status")
      .then((s) => setConfigured(s.configured))
      .catch((e) => setError(e.message));
  }, []);
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      onUpdate(
        await api<User>("/account/alerts", {
          method: "PUT",
          body: JSON.stringify({ enabled, interval, keywords, location }),
        }),
      );
      setMessage("Email preferences saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function credentials(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api("/auth/master/credentials", {
        method: "PUT",
        body: JSON.stringify({
          current_password: currentPassword,
          username: newUsername,
          password: newPassword,
        }),
      });
      onUpdate(await api<User>("/auth/me"));
      setCurrentPassword("");
      setNewPassword("");
      setMessage(
        "Master credentials updated. Other sessions have been signed out.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="account-panel">
      <div className="account-card">
        <h2>{user.name}</h2>
        <p>{user.email || user.username}</p>
        <p>
          {user.role === "admin" ? "Master account" : "Google account"} · Joined{" "}
          {new Date(user.created_at).toLocaleDateString()}
        </p>
      </div>
      {message && (
        <p className="account-message" role="status">
          {message}
        </p>
      )}
      {error && (
        <p className="account-message error" role="alert">
          {error}
        </p>
      )}
      <div className="account-card">
        <h2>Job email alerts</h2>
        <p>
          New jobs and direct employer links, sent to{" "}
          {user.email || "your account email"}. Your preferences apply only to
          your account.
        </p>
        {configured === false && (
          <p className="account-message">
            Email delivery is waiting for Gmail setup. Your preferences will be
            saved.
          </p>
        )}
        {user.email_error && (
          <p className="account-message error">{user.email_error}</p>
        )}
        <form className="account-form" onSubmit={save}>
          <label className="account-check">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              disabled={!user.email}
            />
            Email me new jobs
          </label>
          <label>
            Frequency
            <select
              value={interval}
              onChange={(e) => setIntervalValue(Number(e.target.value))}
            >
              <option value={21600}>After collection · every 6 hours</option>
              <option value={86400}>Once daily</option>
            </select>
          </label>
          <label>
            Keywords (optional)
            <input
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="e.g. Python backend"
              maxLength={200}
            />
            <small>All words must appear in the title or description.</small>
          </label>
          <label>
            Location contains (optional)
            <input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. India"
              maxLength={100}
            />
          </label>
          <p className="auth-note">
            Only jobs discovered since you joined are emailed. Each digest
            includes up to 100 new matches. Unsent matches remain eligible for
            later digests. No matches means no email.
          </p>
          <p>
            Last email:{" "}
            {user.last_email_at
              ? new Date(user.last_email_at).toLocaleString()
              : "No emails sent yet"}
          </p>
          <button className="button primary" disabled={busy}>
            {busy ? "Saving…" : "Save email preferences"}
          </button>
        </form>
      </div>
      {user.role === "admin" && (
        <div className="account-card">
          <h2>Master credentials</h2>
          <form className="account-form" onSubmit={credentials}>
            <label>
              Current password
              <input
                required
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                maxLength={256}
              />
            </label>
            <label>
              New username
              <input
                required
                autoComplete="username"
                minLength={3}
                maxLength={100}
                pattern="[a-zA-Z0-9_.\-]+"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
              />
            </label>
            <label>
              New password
              <input
                required
                type="password"
                autoComplete="new-password"
                minLength={16}
                maxLength={256}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </label>
            <button className="button secondary" disabled={busy}>
              Update master credentials
            </button>
          </form>
        </div>
      )}
    </section>
  );
}

type ManagedUser = User & { saved_count: number; emailed_jobs: number };
export function AdminPanel() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  useEffect(() => {
    api<ManagedUser[]>("/admin/users")
      .then(setUsers)
      .catch((e) => setError(e.message));
  }, []);
  async function toggle(user: ManagedUser) {
    setBusy(user.id);
    setError("");
    try {
      await api(`/admin/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({ active: !user.active }),
      });
      setUsers(await api<ManagedUser[]>("/admin/users"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="account-panel">
      <div className="account-card">
        <h2>Connected accounts ({users.length})</h2>
        <p>
          Disabling an account immediately revokes its sessions and pauses email
          delivery.
        </p>
        {error && (
          <p className="account-message error" role="alert">
            {error}
          </p>
        )}
        <div className="accounts-table-wrap">
          <table className="accounts-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Access</th>
                <th>Saved</th>
                <th>Alerts</th>
                <th>Last sign-in</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    <strong>{u.name}</strong>
                    <br />
                    {u.email || u.username}
                  </td>
                  <td>{u.role === "admin" ? "Master" : "User"}</td>
                  <td>{u.saved_count}</td>
                  <td>
                    {u.alerts_enabled ? "On" : "Off"}
                    <br />
                    {u.emailed_jobs} jobs sent
                  </td>
                  <td>
                    {u.last_login
                      ? new Date(u.last_login).toLocaleString()
                      : "Never"}
                  </td>
                  <td>
                    {u.role === "admin" ? (
                      "Active"
                    ) : (
                      <button
                        className="button secondary"
                        disabled={busy === u.id}
                        onClick={() => toggle(u)}
                      >
                        {u.active ? "Disable" : "Enable"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
