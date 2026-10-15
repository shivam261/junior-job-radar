import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  BriefcaseBusiness,
  Building2,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Code2,
  ExternalLink,
  Filter,
  Globe2,
  Heart,
  LayoutGrid,
  ListFilter,
  LoaderCircle,
  MapPin,
  Menu,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Radio,
  X,
  Plus,
} from "lucide-react";
import { api } from "./api";
import type { Company, Job, JobPage, Run, Stats } from "./types";

type View = "discover" | "saved" | "companies" | "activity";
const brandColors: Record<string, [string, string]> = {
  autodesk: ["#f1f4f2", "#111"],
  mastercard: ["#fff0e8", "#de642c"],
  visa: ["#edf1fb", "#233d8b"],
  cisco: ["#e8f5fc", "#1685b8"],
  razorpay: ["#ebf1ff", "#3266cb"],
  "ge-vernova": ["#e9f5ed", "#1b795c"],
  "jpmorgan-chase": ["#f4ede5", "#80674d"],
  "deutsche-bank": ["#eff2fd", "#22408e"],
  "goldman-sachs": ["#eaf3fb", "#5c8dac"],
  hsbc: ["#fff0f0", "#d73a46"],
  atlassian: ["#eef3ff", "#346bd6"],
  zomato: ["#fdebeb", "#dc454f"],
};
function Logo({
  id,
  name,
  small = false,
}: {
  id: string;
  name: string;
  small?: boolean;
}) {
  const [bg, color] = brandColors[id] || ["#eef2ee", "#54736a"];
  return (
    <span
      className={"company-logo " + (small ? "small" : "")}
      style={{ background: bg, color }}
      aria-label={name}
    >
      {id === "mastercard" ? (
        <span className="mastercard-mark">
          <i />
          <i />
        </span>
      ) : id === "visa" ? (
        <em>VISA</em>
      ) : id === "cisco" ? (
        <span className="cisco-mark">
          ▥<b>cisco</b>
        </span>
      ) : id === "autodesk" ? (
        <span className="autodesk-mark">A</span>
      ) : id === "deutsche-bank" ? (
        <span className="db-mark">╱</span>
      ) : id === "hsbc" ? (
        <span>◆</span>
      ) : (
        name
          .split(/\s+/)
          .map((x) => x[0])
          .slice(0, 2)
          .join("")
      )}
    </span>
  );
}
function relative(date: string | null) {
  if (!date) return "Not refreshed yet";
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(date).getTime()) / 60000),
  );
  return minutes < 1
    ? "Just now"
    : minutes < 60
      ? `${minutes}m ago`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)}h ago`
        : `${Math.floor(minutes / 1440)}d ago`;
}
function experience(job: Job) {
  if (job.experience_min === null) return "Early career";
  if (job.experience_max === job.experience_min)
    return job.experience_min === 0
      ? "No experience required"
      : `${job.experience_min} years`;
  return job.experience_max !== null
    ? `${job.experience_min}–${job.experience_max} years`
    : `${job.experience_min}+ years`;
}
const statusText: Record<string, string> = {
  pending: "Not checked",
  healthy: "Connected",
  partial: "Partial coverage",
  error: "Needs attention",
  refreshing: "Refreshing",
};

export default function App() {
  const [view, setView] = useState<View>("discover"),
    [demo, setDemo] = useState(false),
    [companies, setCompanies] = useState<Company[]>([]),
    [stats, setStats] = useState<Stats | null>(null);
  const [jobs, setJobs] = useState<JobPage>({
      items: [],
      total: 0,
      page: 1,
      page_size: 12,
    }),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [query, setQuery] = useState(""),
    [debounced, setDebounced] = useState(""),
    [location, setLocation] = useState("India"),
    [selectedCompanies, setSelectedCompanies] = useState<string[]>([]),
    [confidence, setConfidence] = useState(""),
    [mode, setMode] = useState(""),
    [sort, setSort] = useState("newest"),
    [page, setPage] = useState(1);
  const [companyQuery, setCompanyQuery] = useState(""),
    [companySearch, setCompanySearch] = useState(""),
    [companyStatus, setCompanyStatus] = useState(""),
    [selected, setSelected] = useState<Job | null>(null),
    [notice, setNotice] = useState(""),
    [runs, setRuns] = useState<Run[]>([]),
    [mobileNav, setMobileNav] = useState(false),
    [mobileFilters, setMobileFilters] = useState(false),
    [refreshing, setRefreshing] = useState(false),
    [version, setVersion] = useState(0),
    [help, setHelp] = useState(false),
    [addingCompany, setAddingCompany] = useState(false),
    [savedStatus, setSavedStatus] = useState("all"),
    [pendingSave, setPendingSave] = useState<string[]>([]);
  const running = stats?.latest_run?.status === "running";
  const noticeTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastJobQuery = useRef("");
  function toast(message: string) {
    setNotice(message);
    if (noticeTimeout.current) clearTimeout(noticeTimeout.current);
    noticeTimeout.current = setTimeout(() => setNotice(""), 4500);
  }
  function navigate(next: View) {
    setView(next);
    setPage(1);
    setMobileNav(false);
    setSelected(null);
  }
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(t);
  }, [query]);
  useEffect(() => {
    setPage(1);
  }, [
    debounced,
    location,
    selectedCompanies,
    confidence,
    mode,
    sort,
    demo,
    savedStatus,
  ]);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [s, c] = await Promise.all([
          api<Stats>(`/stats?demo=${demo}`),
          api<Company[]>("/companies"),
        ]);
        if (active) {
          setStats(s);
          setCompanies(c);
        }
      } catch (e) {
        if (active)
          setError(
            e instanceof Error ? e.message : "Cannot reach the backend.",
          );
      }
    }
    load();
    const t = setInterval(load, running ? 2500 : 15000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [demo, running, version]);
  useEffect(() => {
    if (view !== "discover" && view !== "saved") return;
    let active = true;
    const controller = new AbortController();
    setError("");
    const params = new URLSearchParams({
      q: debounced,
      location,
      company: selectedCompanies.join(","),
      confidence,
      mode,
      sort,
      page: String(page),
      saved: String(view === "saved"),
      demo: String(demo),
      status: view === "saved" ? savedStatus : "open",
    });
    if (lastJobQuery.current !== params.toString()) {
      setLoading(true);
      lastJobQuery.current = params.toString();
    }
    api<JobPage>(`/jobs?${params}`, { signal: controller.signal })
      .then((data) => {
        if (active) setJobs(data);
      })
      .catch((e) => {
        if (active)
          setError(
            e.message === "Failed to fetch"
              ? "The backend is unavailable. Start FastAPI and try again."
              : e.message,
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [
    view,
    savedStatus,
    debounced,
    location,
    selectedCompanies,
    confidence,
    mode,
    sort,
    page,
    demo,
    version,
    running,
    stats?.latest_run?.completed,
  ]);
  useEffect(() => {
    if (view === "activity")
      api<Run[]>("/runs")
        .then(setRuns)
        .catch((e) => setError(e.message));
  }, [view, version, stats?.latest_run?.completed]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelected(null);
        setHelp(false);
        setAddingCompany(false);
        setMobileFilters(false);
        setMobileNav(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  async function refresh(company_id?: string) {
    setRefreshing(true);
    try {
      const r = await api<{ started: boolean }>("/refresh", {
        method: "POST",
        body: JSON.stringify({ company_id }),
      });
      toast(
        r.started
          ? "Refresh started. You can keep browsing."
          : "A refresh is already running.",
      );
      setVersion((v) => v + 1);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setRefreshing(false);
    }
  }
  async function bookmark(job: Job) {
    if (pendingSave.includes(job.id)) return;
    setPendingSave((p) => [...p, job.id]);
    try {
      await api(`/bookmarks/${job.id}`, {
        method: job.saved ? "DELETE" : "PUT",
      });
      if (selected?.id === job.id)
        setSelected({ ...selected, saved: !job.saved });
      setJobs((j) => ({
        ...j,
        items: j.items.map((x) =>
          x.id === job.id ? { ...x, saved: !x.saved } : x,
        ),
      }));
      toast(
        job.saved ? "Removed from saved jobs." : "Job saved to your shortlist.",
      );
      setVersion((v) => v + 1);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setPendingSave((p) => p.filter((id) => id !== job.id));
    }
  }
  async function toggleCompany(c: Company) {
    try {
      await api(`/companies/${c.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !c.enabled }),
      });
      setVersion((v) => v + 1);
      toast(`${c.name} ${c.enabled ? "paused" : "enabled"}.`);
    } catch (e) {
      toast((e as Error).message);
    }
  }
  function clearFilters() {
    setQuery("");
    setSelectedCompanies([]);
    setConfidence("");
    setMode("");
    setLocation("");
    setPage(1);
  }
  const navItems: { key: View; label: string; icon: typeof Search }[] = [
    { key: "discover", label: "Discover jobs", icon: LayoutGrid },
    { key: "saved", label: "Saved jobs", icon: Bookmark },
    { key: "companies", label: "Companies", icon: Building2 },
    { key: "activity", label: "Source activity", icon: Radio },
  ];
  const filtersCount =
    selectedCompanies.length +
    Number(!!confidence) +
    Number(!!mode) +
    Number(!!location);
  const visibleCompanies = companies.filter(
    (c) =>
      c.name.toLowerCase().includes(companySearch.toLowerCase()) &&
      (!companyStatus || c.status === companyStatus),
  );
  const filteredSidebarCompanies = companies.filter((c) =>
    c.name.toLowerCase().includes(companyQuery.toLowerCase()),
  );
  const titles = {
    discover: "Find your next chapter.",
    saved: "Good opportunities, kept close.",
    companies: "Great companies. One place.",
    activity: "A clear view of your sources.",
  };
  const subtitles = {
    discover:
      "Early-career software roles. Direct from the companies you want to join.",
    saved: "Your personal shortlist, ready when you are.",
    companies:
      "Choose the companies to follow and see exactly how their sources are doing.",
    activity:
      "Track refreshes, source coverage, and the freshness of your listings.",
  };
  return (
    <div className="app-shell">
      {mobileNav && (
        <button
          className="mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className={"sidebar " + (mobileNav ? "open" : "")}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("discover");
          }}
        >
          <span className="brand-symbol">
            L<ArrowUpRight size={18} />
          </span>
          <span>
            launchpad<span className="brand-dot">.</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">
            <Code2 size={18} />
          </span>
          <div>
            <strong>Your job workspace</strong>
            <span>Build a career you love</span>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              className={"nav-item " + (view === key ? "active" : "")}
              onClick={() => navigate(key)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {key === "saved" && !!stats?.saved && (
                <span className="nav-count">{stats.saved}</span>
              )}
              {key === "companies" && (
                <span className="nav-count subtle">
                  {stats?.total_companies || "—"}
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-tip">
          <span className="tip-icon">
            <Sparkles size={18} />
          </span>
          <strong>Small steps. Big possibilities.</strong>
          <p>Your first great role could be the next one you discover.</p>
          <button
            onClick={() => {
              navigate("discover");
              setSort("relevance");
            }}
          >
            Explore your matches <ArrowRight size={15} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <button className="help-link" onClick={() => setHelp(true)}>
            <CircleHelp size={18} />
            How Launchpad works
          </button>
          <div className="profile">
            <span>ST</span>
            <div>
              <strong>Your personal workspace</strong>
              <small>Local • No account needed</small>
            </div>
            <span className="online-dot" />
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open menu"
              onClick={() => setMobileNav(true)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{navItems.find((x) => x.key === view)?.label}</strong>
          </div>
          <div className="topbar-actions">
            <span className={"live-indicator " + (demo ? "demo" : "")}>
              <i />
              {demo ? "Demo preview" : "Official career sources"}
            </span>
            <button
              className="avatar"
              onClick={() => setHelp(true)}
              aria-label="Workspace information"
            >
              ST
            </button>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span /> YOUR NEXT CHAPTER STARTS HERE
              </div>
              <h1>{titles[view]}</h1>
              <p>{subtitles[view]}</p>
            </div>
            <button
              className="button secondary refresh-button"
              onClick={() => refresh()}
              disabled={refreshing || running}
            >
              <RefreshCw
                size={15}
                className={refreshing || running ? "spin" : ""}
              />
              {running ? "Refreshing…" : "Refresh openings"}
            </button>
          </div>
          {running && stats?.latest_run && (
            <div className="refresh-progress" role="status">
              <LoaderCircle size={15} className="spin" />
              <span>
                Checking official sources{" "}
                <strong>
                  {stats.latest_run.completed} / {stats.latest_run.total}
                </strong>
              </span>
              <div>
                <i
                  style={{
                    width: `${stats.latest_run.total ? (stats.latest_run.completed / stats.latest_run.total) * 100 : 0}%`,
                  }}
                />
              </div>
              <small>{stats.latest_run.matched} matches found</small>
            </div>
          )}
          {demo && (
            <div className="demo-banner">
              <Sparkles size={17} />
              <span>
                <strong>Demo preview</strong> · Illustrative listings for
                exploring the interface. These are not current vacancies.
              </span>
              <button
                onClick={() => {
                  setDemo(false);
                  setPage(1);
                }}
              >
                Return to live jobs <ArrowRight size={14} />
              </button>
            </div>
          )}
          <section className="stats-grid" aria-label="Workspace overview">
            {[
              {
                label: demo ? "Sample opportunities" : "Open opportunities",
                value: stats?.total,
                icon: BriefcaseBusiness,
                note: demo
                  ? "Illustrative roles"
                  : "Software engineering roles",
                color: "teal",
              },
              {
                label: "Companies tracked",
                value: stats?.tracked_companies,
                icon: Building2,
                note: `${stats?.healthy_sources || 0} sources fully connected`,
                color: "blue",
              },
              {
                label: "Confirmed experience",
                value: stats?.confirmed,
                icon: ShieldCheck,
                note: "Requirements fit 0–2 years",
                color: "amber",
              },
              {
                label: "Saved for later",
                value: stats?.saved,
                icon: Bookmark,
                note: "Your next possibilities",
                color: "purple",
              },
            ].map((s) => (
              <article className="stat-card" key={s.label}>
                <div>
                  <span className="stat-label">{s.label}</span>
                  <span className={"stat-icon " + s.color}>
                    <s.icon size={18} />
                  </span>
                </div>
                <strong className="stat-number">{s.value ?? "—"}</strong>
                <span className="stat-note">
                  {s.label === "Open opportunities" && (
                    <span className="tiny-dot" />
                  )}
                  {s.note}
                </span>
              </article>
            ))}
          </section>
          {(view === "discover" || view === "saved") && (
            <>
              {view === "discover" && (
                <section className="hero-banner">
                  <div className="hero-content">
                    <span className="hero-label">
                      <Sparkles size={13} /> LESS SEARCHING. MORE POSSIBILITIES.
                    </span>
                    <h2>
                      Big ambitions.
                      <br />
                      The right first step.
                    </h2>
                    <p>
                      Discover roles built for the beginning of your journey.
                    </p>
                    <div className="hero-chips">
                      <span>
                        <Check size={13} /> 0–2 years experience
                      </span>
                      <span>
                        <Check size={13} /> Direct company listings
                      </span>
                    </div>
                  </div>
                  <div className="hero-illustration" aria-hidden="true">
                    <div className="orbit orbit-one" />
                    <div className="orbit orbit-two" />
                    <div className="floating-chip chip-code">
                      <Code2 size={18} />
                    </div>
                    <div className="floating-chip chip-check">
                      <CheckCheck size={17} />
                    </div>
                    <div className="step step-one" />
                    <div className="step step-two" />
                    <div className="step step-three" />
                    <div className="growth-arrow">
                      <ArrowUpRight size={68} strokeWidth={1.8} />
                    </div>
                    <div className="hero-spark spark-one">✧</div>
                    <div className="hero-spark spark-two">✦</div>
                  </div>
                  <span className="banner-footnote">
                    A little closer to what’s next.
                  </span>
                </section>
              )}
              <section className="search-toolbar" aria-label="Job search">
                <label className="search-field">
                  <Search size={19} />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Job title, skill, or company"
                    aria-label="Search jobs"
                  />
                  {query && (
                    <button
                      className="icon-button"
                      onClick={() => setQuery("")}
                      aria-label="Clear search"
                    >
                      <X size={14} />
                    </button>
                  )}
                </label>
                <label className="location-field">
                  <MapPin size={18} />
                  <select
                    aria-label="Location"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                  >
                    <option value="">Anywhere</option>
                    <option value="India">India — all locations</option>
                    <option>Bengaluru</option>
                    <option>Pune</option>
                    <option>Hyderabad</option>
                    <option>Mumbai</option>
                    <option>Chennai</option>
                    <option>Gurugram</option>
                    <option>United States</option>
                    <option>United Kingdom</option>
                    <option>Remote</option>
                  </select>
                  <ChevronDown size={14} />
                </label>
                <button
                  className="button primary"
                  onClick={() => {
                    setDebounced(query);
                    setPage(1);
                  }}
                >
                  Find jobs <ArrowRight size={16} />
                </button>
                <button
                  className="button secondary filter-mobile-button"
                  onClick={() => setMobileFilters((v) => !v)}
                >
                  <SlidersHorizontal size={16} />
                  Filters
                </button>
              </section>
              <div
                className="location-shortcuts"
                aria-label="Quick location filters"
              >
                <span>
                  <MapPin size={13} /> Browse by location
                </span>
                <button
                  aria-pressed={location === "India"}
                  className={location === "India" ? "selected" : ""}
                  onClick={() => setLocation("India")}
                >
                  India
                </button>
                <button
                  aria-pressed={location === ""}
                  className={location === "" ? "selected" : ""}
                  onClick={() => setLocation("")}
                >
                  Worldwide
                </button>
                {view === "saved" && (
                  <label className="saved-status-control">
                    Job status{" "}
                    <select
                      value={savedStatus}
                      onChange={(e) => setSavedStatus(e.target.value)}
                      aria-label="Saved job status"
                    >
                      <option value="all">All saved roles</option>
                      <option value="open">Open roles</option>
                      <option value="closed">Closed / archived roles</option>
                    </select>
                    <ChevronDown size={12} />
                  </label>
                )}
              </div>
              <div className="jobs-layout">
                <aside
                  className={
                    "filter-panel " + (mobileFilters ? "show-mobile" : "")
                  }
                  aria-label="Job filters"
                >
                  <div className="filter-heading">
                    <h3>
                      <SlidersHorizontal size={16} />
                      Filters {filtersCount > 0 && <span>{filtersCount}</span>}
                    </h3>
                    <button className="text-button" onClick={clearFilters}>
                      Reset
                    </button>
                  </div>
                  <div className="filter-group">
                    <h4>Experience level</h4>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="confidence"
                        checked={confidence === ""}
                        onChange={() => setConfidence("")}
                      />
                      <span>All early-career matches</span>
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="confidence"
                        checked={confidence === "confirmed"}
                        onChange={() => setConfidence("confirmed")}
                      />
                      <span>Confirmed 0–2 years</span>
                      <ShieldCheck size={13} />
                    </label>
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="confidence"
                        checked={confidence === "possible"}
                        onChange={() => setConfidence("possible")}
                      />
                      <span>Possible matches</span>
                    </label>
                    <p className="filter-hint">
                      Possible matches use junior or graduate titles. Check the
                      posting’s requirements.
                    </p>
                  </div>
                  <div className="filter-group">
                    <h4>Work arrangement</h4>
                    {["", "Remote", "Hybrid", "Not specified"].map((m) => (
                      <label className="radio-label" key={m}>
                        <input
                          type="radio"
                          name="mode"
                          checked={mode === m}
                          onChange={() => setMode(m)}
                        />
                        <span>{m || "All arrangements"}</span>
                      </label>
                    ))}
                  </div>
                  <div className="filter-group company-filter">
                    <h4>
                      Companies<span>{companies.length}</span>
                    </h4>
                    <label className="mini-search">
                      <Search size={14} />
                      <input
                        aria-label="Find company filter"
                        value={companyQuery}
                        onChange={(e) => setCompanyQuery(e.target.value)}
                        placeholder="Find a company"
                      />
                    </label>
                    <div className="company-options">
                      {filteredSidebarCompanies.map((c) => (
                        <label className="checkbox-label" key={c.id}>
                          <input
                            type="checkbox"
                            checked={selectedCompanies.includes(c.id)}
                            onChange={() =>
                              setSelectedCompanies((ids) =>
                                ids.includes(c.id)
                                  ? ids.filter((x) => x !== c.id)
                                  : [...ids, c.id],
                              )
                            }
                          />
                          <span>{c.name}</span>
                          <small>{c.job_count}</small>
                        </label>
                      ))}
                      {!filteredSidebarCompanies.length && (
                        <p className="filter-hint">No companies found.</p>
                      )}
                    </div>
                  </div>
                  <div className="filter-trust">
                    <ShieldCheck size={20} />
                    <strong>Closer to the source</strong>
                    <p>
                      Open the original company posting to check details and
                      apply.
                    </p>
                  </div>
                </aside>
                <section className="job-results" aria-label="Job results">
                  <div className="results-header">
                    <div>
                      <h3>
                        {view === "saved"
                          ? "Your saved opportunities"
                          : "Recommended opportunities"}
                        <span>{jobs.total}</span>
                      </h3>
                      <p>
                        {loading
                          ? "Finding your possibilities…"
                          : `${jobs.total} ${view === "saved" ? "saved " : ""}roles${location ? ` in ${location}` : ""} matching your filters`}
                      </p>
                    </div>
                    <label className="sort-control">
                      Sort by{" "}
                      <select
                        value={sort}
                        aria-label="Sort jobs"
                        onChange={(e) => setSort(e.target.value)}
                      >
                        <option value="newest">Newest first</option>
                        <option value="relevance">Confirmed first</option>
                        <option value="company">Company A–Z</option>
                      </select>
                      <ChevronDown size={12} />
                    </label>
                  </div>
                  {selectedCompanies.length > 0 && (
                    <div className="active-filters">
                      {selectedCompanies.map((id) => (
                        <button
                          key={id}
                          onClick={() =>
                            setSelectedCompanies((ids) =>
                              ids.filter((x) => x !== id),
                            )
                          }
                        >
                          {companies.find((c) => c.id === id)?.name}
                          <X size={12} />
                        </button>
                      ))}
                    </div>
                  )}
                  {error ? (
                    <div className="empty-state">
                      <Radio size={32} />
                      <h3>Let’s reconnect.</h3>
                      <p>{error}</p>
                      <button
                        className="button primary"
                        onClick={() => setVersion((v) => v + 1)}
                      >
                        Try again
                      </button>
                    </div>
                  ) : loading ? (
                    <div className="job-grid">
                      {[1, 2, 3, 4].map((i) => (
                        <div className="skeleton-card" key={i}>
                          <div />
                          <span />
                          <span />
                          <span />
                        </div>
                      ))}
                    </div>
                  ) : jobs.items.length ? (
                    <>
                      <div className="job-grid">
                        {jobs.items.map((job) => (
                          <article
                            className={
                              "job-card " + (!job.active ? "closed-job" : "")
                            }
                            key={job.id}
                          >
                            <div className="job-card-top">
                              <Logo id={job.company_id} name={job.company} />
                              <div className="company-info">
                                <strong>{job.company}</strong>
                                <span>{job.sector}</span>
                              </div>
                              <button
                                className={
                                  "icon-button save-button " +
                                  (job.saved ? "saved" : "")
                                }
                                aria-label={
                                  job.saved
                                    ? `Unsave ${job.title}`
                                    : `Save ${job.title}`
                                }
                                aria-pressed={job.saved}
                                disabled={pendingSave.includes(job.id)}
                                onClick={() => bookmark(job)}
                              >
                                <Bookmark
                                  size={19}
                                  fill={job.saved ? "currentColor" : "none"}
                                />
                              </button>
                            </div>
                            <button
                              className="job-title"
                              onClick={() => setSelected(job)}
                            >
                              {job.title}
                              <ArrowUpRight size={17} />
                            </button>
                            <div className="job-location">
                              <MapPin size={14} />
                              <span>{job.location}</span>
                            </div>
                            <div className="job-meta">
                              <span>
                                <BriefcaseBusiness size={12} />
                                {experience(job)}
                              </span>
                              <span>
                                {job.work_mode === "Not specified"
                                  ? job.employment_type
                                  : job.work_mode}
                              </span>
                            </div>
                            <div className="skill-tags">
                              {job.skills.slice(0, 4).map((skill) => (
                                <span key={skill}>{skill}</span>
                              ))}
                              {!job.skills.length && (
                                <span>Software engineering</span>
                              )}
                            </div>
                            <div className="job-card-footer">
                              <span
                                className={"match-badge " + job.confidence}
                                title={job.evidence}
                              >
                                {job.confidence === "confirmed" ? (
                                  <ShieldCheck size={12} />
                                ) : (
                                  <Sparkles size={12} />
                                )}{" "}
                                {job.confidence === "confirmed"
                                  ? "Experience confirmed"
                                  : "Possible match"}
                              </span>
                              <span className="job-age">
                                <Clock3 size={12} />
                                {job.demo
                                  ? "Example"
                                  : job.posted_at
                                    ? relative(job.posted_at)
                                    : "Date unavailable"}
                              </span>
                            </div>
                            {!job.active && (
                              <div className="closed-job-note">
                                <Clock3 size={12} />{" "}
                                {job.closed_reason === "no_longer_matches"
                                  ? "No longer matches your experience filter"
                                  : "Closed · No longer listed"}{" "}
                                {job.closed_at
                                  ? `· ${new Date(job.closed_at).toLocaleDateString()}`
                                  : ""}
                              </div>
                            )}
                            {job.active &&
                              !job.demo &&
                              job.source_status !== "healthy" && (
                                <div className="uncertain-job-note">
                                  <Radio size={12} />
                                  {job.source_status === "error"
                                    ? "Source unavailable — verify availability"
                                    : "Partial source — verify availability"}
                                </div>
                              )}
                            <div className="job-card-source">
                              <span>
                                {job.demo
                                  ? "Demo listing"
                                  : `Checked ${relative(job.last_seen)}`}
                              </span>
                              <a
                                href={job.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {job.demo
                                  ? "Company careers"
                                  : job.active
                                    ? "View posting"
                                    : "View archived posting"}
                                <ArrowUpRight size={13} />
                              </a>
                            </div>
                          </article>
                        ))}
                      </div>
                      {jobs.total > 12 && (
                        <div className="pagination">
                          <span>
                            Showing {(page - 1) * 12 + 1}–
                            {Math.min(page * 12, jobs.total)} of {jobs.total}
                          </span>
                          <div>
                            <button
                              aria-label="Previous page"
                              disabled={page === 1}
                              onClick={() => setPage((p) => p - 1)}
                            >
                              <ChevronLeft size={16} />
                            </button>
                            <span>
                              {page} / {Math.ceil(jobs.total / 12)}
                            </span>
                            <button
                              aria-label="Next page"
                              disabled={page * 12 >= jobs.total}
                              onClick={() => setPage((p) => p + 1)}
                            >
                              <ChevronRight size={16} />
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="empty-state">
                      <span className="empty-icon">
                        {view === "saved" ? (
                          <Bookmark size={30} />
                        ) : (
                          <Search size={30} />
                        )}
                      </span>
                      <h3>
                        {view === "saved"
                          ? "Your shortlist starts here."
                          : stats?.total
                            ? "A different search could open a door."
                            : "Your next chapter is loading."}
                      </h3>
                      <p>
                        {view === "saved"
                          ? "Save a role with the bookmark icon and find it here. Try clearing filters if you already saved jobs."
                          : stats?.total
                            ? "No roles match these filters. Try another location or broaden your search."
                            : "Refresh official sources to collect current openings. You can explore the interface with clearly labeled sample jobs."}
                      </p>
                      <div className="empty-actions">
                        <button
                          className="button primary"
                          onClick={() =>
                            stats?.total || view === "saved"
                              ? clearFilters()
                              : refresh()
                          }
                          disabled={!!running}
                        >
                          {stats?.total || view === "saved"
                            ? "Clear filters"
                            : running
                              ? "Sources refreshing…"
                              : "Collect live openings"}
                        </button>
                        {!demo && !stats?.total && view === "discover" && (
                          <button
                            className="button secondary"
                            onClick={() => {
                              setDemo(true);
                              setPage(1);
                            }}
                          >
                            Preview demo <ArrowUpRight size={14} />
                          </button>
                        )}
                      </div>
                      <button
                        className="text-button"
                        onClick={() => navigate("companies")}
                      >
                        Check company coverage <ArrowRight size={13} />
                      </button>
                    </div>
                  )}
                  <div className="results-note">
                    <ShieldCheck size={14} />
                    <span>
                      Always apply on the company’s official site. Listings can
                      change between refreshes.
                    </span>
                  </div>
                </section>
              </div>
            </>
          )}
          {view === "companies" && (
            <section className="directory">
              <div className="section-intro">
                <div>
                  <h2>
                    Your company radar <span>{companies.length}</span>
                  </h2>
                  <p>
                    Public feeds where available. Transparent coverage, always.
                  </p>
                </div>
                <button
                  className="button primary"
                  onClick={() => setAddingCompany(true)}
                >
                  <Plus size={16} />
                  Add company
                </button>
              </div>
              <div className="directory-toolbar">
                <label className="search-field">
                  <Search size={18} />
                  <input
                    aria-label="Search companies"
                    value={companySearch}
                    onChange={(e) => setCompanySearch(e.target.value)}
                    placeholder="Search your companies…"
                  />
                </label>
                <label className="directory-select">
                  <Filter size={14} />
                  <select
                    value={companyStatus}
                    onChange={(e) => setCompanyStatus(e.target.value)}
                    aria-label="Source status filter"
                  >
                    <option value="">All source statuses</option>
                    {Object.entries(statusText).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="coverage-note">
                <ShieldCheck size={18} />
                <p>
                  <strong>
                    A company in the directory doesn’t guarantee complete
                    coverage.
                  </strong>{" "}
                  Connected feeds provide a full board snapshot within
                  collection limits. Partial sources may miss postings.
                  Unavailable sources keep their previous listings.
                </p>
              </div>
              <div className="company-grid">
                {visibleCompanies.map((c) => (
                  <article className="directory-card" key={c.id}>
                    <div className="directory-card-heading">
                      <Logo id={c.id} name={c.name} />
                      <div>
                        <h3>{c.name}</h3>
                        <span>
                          {c.sector}
                          {c.custom ? " · Added by you" : ""}
                        </span>
                      </div>
                      <button
                        className={"toggle " + (c.enabled ? "on" : "")}
                        role="switch"
                        aria-checked={!!c.enabled}
                        aria-label={`Track ${c.name}`}
                        onClick={() => toggleCompany(c)}
                      >
                        <i />
                      </button>
                    </div>
                    <div className={"source-status " + c.status}>
                      <i />
                      {statusText[c.status] || c.status}
                      <span>
                        {c.adapter === "html"
                          ? "Careers page"
                          : c.adapter === "auto"
                            ? "Auto detect"
                            : c.adapter}
                      </span>
                    </div>
                    {c.error && <p className="source-error">{c.error}</p>}
                    <div className="directory-metrics">
                      <span>
                        <strong>{c.job_count}</strong> live matches
                      </span>
                      <span>Checked {relative(c.last_checked)}</span>
                    </div>
                    <div className="directory-card-actions">
                      <a href={c.url} target="_blank" rel="noopener noreferrer">
                        Official careers <ExternalLink size={13} />
                      </a>
                      <button
                        aria-label={`Refresh ${c.name}`}
                        disabled={!!running || !c.enabled}
                        onClick={() => refresh(c.id)}
                      >
                        <RefreshCw size={14} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              {!visibleCompanies.length && (
                <div className="empty-state">
                  <Building2 size={30} />
                  <h3>No companies match.</h3>
                  <p>Try another name or source status.</p>
                </div>
              )}
            </section>
          )}
          {view === "activity" && (
            <section className="activity">
              <div className="section-intro">
                <div>
                  <h2>Refresh history</h2>
                  <p>
                    Automatic refresh every six hours while the backend is
                    running.
                  </p>
                </div>
                <span className="quiet-tag">
                  <Clock3 size={14} /> Live source checks
                </span>
              </div>
              <div className="activity-summary">
                <div>
                  <ShieldCheck size={23} />
                  <strong>
                    {stats?.healthy_sources || 0} connected sources
                  </strong>
                  <span>Full snapshots retrieved successfully</span>
                </div>
                <div>
                  <ListFilter size={23} />
                  <strong>
                    {companies.filter((c) => c.status === "partial").length}{" "}
                    partial sources
                  </strong>
                  <span>Read their official sites for complete listings</span>
                </div>
                <div>
                  <Radio size={23} />
                  <strong>
                    {companies.filter((c) => c.status === "error").length} need
                    attention
                  </strong>
                  <span>Source failures never erase previous jobs</span>
                </div>
              </div>
              {runs.length ? (
                <div className="run-table">
                  <div className="run-row table-heading">
                    <span>Started</span>
                    <span>Status</span>
                    <span>Sources checked</span>
                    <span>Matches</span>
                  </div>
                  {runs.map((r) => (
                    <div className="run-row" key={r.id}>
                      <span>
                        {new Date(r.started_at).toLocaleString(undefined, {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </span>
                      <span className={"run-status " + r.status}>
                        {r.status.replaceAll("_", " ")}
                      </span>
                      <span>
                        {r.completed} / {r.total}
                        <small>
                          {r.succeeded} successful · {r.failed} errors
                        </small>
                      </span>
                      <strong>{r.matched}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <RefreshCw size={30} />
                  <h3>A fresh start.</h3>
                  <p>Your first source refresh will appear here.</p>
                  <button className="button primary" onClick={() => refresh()}>
                    Start a refresh
                  </button>
                </div>
              )}
            </section>
          )}
          <footer className="page-footer">
            <span>Made for beginnings. Built for possibilities.</span>
            <span>
              launchpad<span className="brand-dot">.</span>
              <Heart size={11} />
            </span>
          </footer>
        </div>
      </main>
      {notice && (
        <div className="toast" role="status">
          <Check size={16} />
          {notice}
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {selected && (
        <JobDrawer
          job={selected}
          company={companies.find((c) => c.id === selected.company_id)}
          onClose={() => setSelected(null)}
          onSave={() => bookmark(selected)}
          saving={pendingSave.includes(selected.id)}
        />
      )}
      {addingCompany && (
        <AddCompanyDialog
          onClose={() => setAddingCompany(false)}
          onAdded={(company) => {
            setAddingCompany(false);
            setCompanySearch(company.name);
            setCompanyStatus("");
            setVersion((v) => v + 1);
            toast(
              "Company added. Its careers source is queued for collection.",
            );
          }}
        />
      )}
      {help && (
        <HelpDialog
          onClose={() => setHelp(false)}
          onDemo={() => {
            setHelp(false);
            setDemo((d) => !d);
            navigate("discover");
          }}
          demo={demo}
        />
      )}
    </div>
  );
}

function useDialog(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    (
      ref.current?.querySelector<HTMLElement>(
        "button:not(:disabled), a[href]",
      ) || ref.current
    )?.focus();
    function trap(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab") return;
      const targets = ref.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], input, select, [tabindex="0"]',
      );
      if (!targets?.length) return;
      const first = targets[0],
        last = targets[targets.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", trap);
    return () => {
      document.body.style.overflow = old;
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, []);
  return ref;
}
function JobDrawer({
  job,
  company,
  onClose,
  onSave,
  saving,
}: {
  job: Job;
  company: Company | undefined;
  onClose: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  const ref = useDialog(onClose);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className="job-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
      >
        <header>
          <span>Opportunity details</span>
          <button
            className="icon-button"
            aria-label="Close details"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>
        <div className="drawer-body">
          <div className="drawer-company">
            <Logo id={job.company_id} name={job.company} />
            <div>
              <strong>{job.company}</strong>
              <span>{job.sector}</span>
            </div>
          </div>
          <h2 id="drawer-title">{job.title}</h2>
          <p className="job-location">
            <MapPin size={16} />
            {job.location}
          </p>
          <div className="job-meta">
            <span>{experience(job)}</span>
            <span>{job.employment_type}</span>
            <span>{job.work_mode}</span>
          </div>
          {!job.active && (
            <div className="drawer-closed">
              <Clock3 size={17} />
              <div>
                <strong>
                  {job.closed_reason === "no_longer_matches"
                    ? "This role no longer matches the experience filter."
                    : "This role is no longer in the employer’s complete results."}
                </strong>
                <p>
                  Your saved description is kept for reference. It was archived{" "}
                  {job.closed_at
                    ? new Date(job.closed_at).toLocaleDateString()
                    : "after a successful refresh"}
                  . The original posting may no longer be available.
                </p>
              </div>
            </div>
          )}
          {job.demo && (
            <div className="drawer-warning">
              <Sparkles size={16} />
              This is demonstration data, not a current vacancy. Its link opens
              the company careers page.
            </div>
          )}
          <div className={"match-explanation " + job.confidence}>
            <h3>
              {job.confidence === "confirmed" ? (
                <ShieldCheck size={18} />
              ) : (
                <Sparkles size={18} />
              )}
              Why this role matched
            </h3>
            <p>{job.evidence}</p>
            <small>
              {job.confidence === "confirmed"
                ? "The stated experience requirement fits our conservative 0–2 year filter. Read the full posting for other eligibility requirements."
                : "Years are not specified. Early-career wording is a suggestion, not confirmed eligibility."}
            </small>
          </div>
          <h3 className="drawer-section-heading">Skills mentioned</h3>
          <div className="skill-tags">
            {job.skills.length ? (
              job.skills.map((s) => <span key={s}>{s}</span>)
            ) : (
              <span>No skills extracted</span>
            )}
          </div>
          <h3 className="drawer-section-heading">From the original posting</h3>
          <div className="description">{job.description}</div>
          <div className="source-details">
            <ShieldCheck size={18} />
            <div>
              <strong>
                {job.demo ? "Demo source" : `Collected from ${job.adapter}`}
              </strong>
              <p>
                Last checked {relative(job.last_seen)}
                {job.posted_at
                  ? ` · Posted ${new Date(job.posted_at).toLocaleDateString()}`
                  : ""}
              </p>
              {company?.status !== "healthy" && !job.demo && (
                <small>
                  This source is{" "}
                  {statusText[company?.status || "pending"].toLowerCase()}.
                  Confirm availability on the employer site.
                </small>
              )}
            </div>
          </div>
        </div>
        <footer>
          <button
            className={"button secondary " + (job.saved ? "saved" : "")}
            onClick={onSave}
            disabled={saving}
          >
            <Bookmark size={16} fill={job.saved ? "currentColor" : "none"} />
            {job.saved ? "Saved" : "Save job"}
          </button>
          <a
            className="button primary"
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {job.demo
              ? "View company careers"
              : job.active
                ? "View original posting"
                : "View archived posting"}
            <ArrowUpRight size={17} />
          </a>
        </footer>
      </div>
    </div>
  );
}
function HelpDialog({
  onClose,
  onDemo,
  demo,
}: {
  onClose: () => void;
  onDemo: () => void;
  demo: boolean;
}) {
  const ref = useDialog(onClose);
  return (
    <div
      className="modal-backdrop centered"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className="help-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
      >
        <button
          className="icon-button help-close"
          aria-label="Close help"
          onClick={onClose}
        >
          <X size={20} />
        </button>
        <span className="help-emblem">
          <Sparkles size={26} />
        </span>
        <h2 id="help-title">A calmer way to find what’s next.</h2>
        <p>
          Launchpad collects public company careers listings and finds
          early-career software engineering roles.
        </p>
        <div className="help-step">
          <span>01</span>
          <div>
            <strong>Explore official sources</strong>
            <p>
              Refresh your tracked company sources. Check Companies for
              connected, partial, or unavailable feeds. Coverage varies by
              employer.
            </p>
          </div>
        </div>
        <div className="help-step">
          <span>02</span>
          <div>
            <strong>Understand your matches</strong>
            <p>
              Confirmed matches state experience within 0–2 years. Possible
              matches use graduate or junior titles without stating years.
              Senior titles and requirements above two years are excluded.
            </p>
          </div>
        </div>
        <div className="help-step">
          <span>03</span>
          <div>
            <strong>Save, review, and apply</strong>
            <p>
              Keep a shortlist in your local SQLite database. Open the
              employer’s original posting to verify details and apply directly.
            </p>
          </div>
        </div>
        <div className="help-note">
          This is a personal local workspace. Bookmarks are shared by browsers
          using this instance. Collection runs only while the backend is
          running.
        </div>
        <button className="button primary" onClick={onDemo}>
          {demo ? "Return to live listings" : "Explore the demo interface"}
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}

function AddCompanyDialog({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: (company: Company) => void;
}) {
  const ref = useDialog(onClose);
  const [name, setName] = useState(""),
    [url, setUrl] = useState(""),
    [sector, setSector] = useState("Technology"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const company = await api<Company>("/companies", {
        method: "POST",
        body: JSON.stringify({ name, url, sector, refresh: true }),
      });
      onAdded(company);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="modal-backdrop centered"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className="help-dialog add-company-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-company-title"
      >
        <button
          className="icon-button help-close"
          aria-label="Close add company"
          onClick={onClose}
        >
          <X size={20} />
        </button>
        <span className="help-emblem">
          <Building2 size={25} />
        </span>
        <h2 id="add-company-title">Add a company to your radar.</h2>
        <p>
          Enter its name and official careers page. We’ll find its recruiting
          feed where available and collect matching software roles.
        </p>
        <form onSubmit={submit}>
          <label>
            Company name
            <input
              required
              minLength={2}
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Acme"
              autoComplete="organization"
            />
          </label>
          <label>
            Careers page URL
            <input
              required
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://company.com/careers"
              maxLength={2048}
            />
          </label>
          <label>
            Industry
            <select value={sector} onChange={(e) => setSector(e.target.value)}>
              {[
                "Technology",
                "Finance",
                "Consumer tech",
                "IT services",
                "Industrial tech",
                "Other",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <div className="source-discovery-note">
            <ShieldCheck size={18} />
            <p>
              Workday, Greenhouse, Lever, SmartRecruiters, Ashby, Oracle, and
              Atlassian sources are detected automatically. Other public pages
              use the general collector. Access and coverage appear in the
              company card.
            </p>
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? (
              <>
                <LoaderCircle size={16} className="spin" />
                Adding company…
              </>
            ) : (
              <>
                <Plus size={16} />
                Add & collect openings
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
