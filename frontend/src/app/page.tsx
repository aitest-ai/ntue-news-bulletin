"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type NewsItem = {
  id: number;
  title: string;
  url: string;
  source: string;
  publish_time: string | null;
  keyword: string;
};

type KeywordItem = { id: number; word: string };

const socialSources = new Set(["Dcard", "PTT", "Threads", "Instagram"]);

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [news, setNews] = useState<NewsItem[]>([]);
  const [keywords, setKeywords] = useState<KeywordItem[]>([]);
  const [selectedKeyword, setSelectedKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("bulletin_token") : null;
    if (saved) setToken(saved);
  }, []);

  useEffect(() => {
    if (token) refresh();
  }, [token, selectedKeyword]);

  const headers = useMemo(() => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${token || ""}`,
  }), [token]);

  async function api(path: string, options: RequestInit = {}) {
    const res = await fetch(path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    if (res.status === 401) {
      localStorage.removeItem("bulletin_token");
      setToken(null);
      throw new Error("登入已過期");
    }
    return res;
  }

  async function login(e: FormEvent) {
    e.preventDefault();
    setMessage("");
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) return setMessage("密碼錯誤");
    const data = await res.json();
    localStorage.setItem("bulletin_token", data.access_token);
    setToken(data.access_token);
  }

  async function refresh() {
    setLoading(true);
    try {
      const kw = selectedKeyword ? `&keyword=${encodeURIComponent(selectedKeyword)}` : "";
      const [newsRes, kwRes] = await Promise.all([
        api(`/api/news?skip=0&limit=100${kw}`),
        api("/api/keywords"),
      ]);
      const newsData = await newsRes.json();
      const kwData = await kwRes.json();
      setNews(newsData.items || []);
      setKeywords(kwData || []);
    } catch (err: any) {
      setMessage(err?.message || "載入失敗");
    } finally {
      setLoading(false);
    }
  }

  async function runNow() {
    setRunning(true);
    setMessage("正在啟動抓取任務…");
    try {
      const res = await api("/api/news/fetch", { method: "POST" });
      const data = await res.json();
      setMessage(data.message || "已啟動背景抓取");
    } catch (err: any) {
      setMessage(err?.message || "啟動失敗");
    } finally {
      setRunning(false);
    }
  }

  const stats = useMemo(() => {
    const social = news.filter(n => socialSources.has(n.source)).length;
    const sources = new Set(news.map(n => n.source)).size;
    const today = new Date().toLocaleDateString("zh-TW", { timeZone: "Asia/Taipei" });
    const todayCount = news.filter(n => {
      if (!n.publish_time) return false;
      return new Date(n.publish_time).toLocaleDateString("zh-TW", { timeZone: "Asia/Taipei" }) === today;
    }).length;
    return { total: news.length, social, sources, todayCount };
  }, [news]);

  if (!token) {
    return <main style={styles.loginPage}>
      <form onSubmit={login} style={styles.loginCard}>
        <div style={styles.badge}>NTUE Opinion Monitor</div>
        <h1 style={styles.loginTitle}>國北教大輿情系統</h1>
        <p style={styles.muted}>輸入管理密碼後進入系統</p>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="管理密碼" style={styles.input} />
        <button style={styles.primary}>登入</button>
        {message && <p style={styles.error}>{message}</p>}
      </form>
    </main>;
  }

  return <main style={styles.page}>
    <header style={styles.header}>
      <div>
        <div style={styles.badge}>NTUE Opinion Monitor · Task-to-Task</div>
        <h1 style={styles.title}>國北教大輿情監測</h1>
        <p style={styles.muted}>各來源獨立抓取；單一來源失敗，不影響整體任務。</p>
      </div>
      <div style={styles.actions}>
        <button onClick={refresh} style={styles.secondary}>{loading ? "更新中…" : "重新整理"}</button>
        <button onClick={runNow} disabled={running} style={styles.primary}>{running ? "啟動中…" : "立即抓取"}</button>
        <button onClick={() => { localStorage.removeItem("bulletin_token"); setToken(null); }} style={styles.ghost}>登出</button>
      </div>
    </header>

    {message && <div style={styles.notice}>{message}</div>}

    <section style={styles.statsGrid}>
      <Stat label="目前顯示" value={stats.total} note="則內容" />
      <Stat label="今日內容" value={stats.todayCount} note="依發布日期" />
      <Stat label="社群／論壇" value={stats.social} note="Dcard・PTT・Threads" />
      <Stat label="資料來源" value={stats.sources} note="獨立來源" />
    </section>

    <section style={styles.toolbar}>
      <div>
        <strong>監測關鍵字</strong>
        <div style={styles.chips}>
          <button onClick={() => setSelectedKeyword("")} style={selectedKeyword === "" ? styles.chipActive : styles.chip}>全部</button>
          {keywords.map(k => <button key={k.id} onClick={() => setSelectedKeyword(k.word)} style={selectedKeyword === k.word ? styles.chipActive : styles.chip}>{k.word}</button>)}
        </div>
      </div>
    </section>

    <section style={styles.contentGrid}>
      <div style={styles.panel}>
        <div style={styles.panelHeader}>
          <div>
            <h2 style={styles.panelTitle}>最新輿情</h2>
            <p style={styles.muted}>新聞、校務與社群內容集中顯示</p>
          </div>
        </div>
        <div>
          {loading && news.length === 0 ? <p style={styles.empty}>資料載入中…</p> : news.length === 0 ? <p style={styles.empty}>目前沒有資料，請按「立即抓取」。</p> : news.map(item => <article key={item.id} style={styles.newsRow}>
            <div style={styles.sourcePill}>{item.source}</div>
            <div style={{ flex: 1 }}>
              <a href={item.url.startsWith("http") ? item.url : "#"} target="_blank" rel="noreferrer" style={styles.newsTitle}>{item.title}</a>
              <div style={styles.meta}>{item.keyword} · {formatDate(item.publish_time)}</div>
            </div>
          </article>)}
        </div>
      </div>

      <aside style={styles.panel}>
        <h2 style={styles.panelTitle}>系統狀態</h2>
        <p style={styles.muted}>新版先保留最需要的監控資訊。</p>
        <Status name="Google News" text="獨立 Task" />
        <Status name="社群搜尋" text="獨立 Task" />
        <Status name="日期防呆" text="已啟用" />
        <Status name="URL 去重" text="已啟用" />
        <div style={styles.infoBox}>
          <strong>新版差異</strong>
          <p style={{ ...styles.muted, marginBottom: 0 }}>抓取來源現在各自執行；Google News 或社群來源其中一邊失敗，另一邊仍會保存結果。</p>
        </div>
      </aside>
    </section>
  </main>;
}

function Stat({ label, value, note }: { label: string; value: number; note: string }) {
  return <div style={styles.stat}><div style={styles.statLabel}>{label}</div><div style={styles.statValue}>{value}</div><div style={styles.muted}>{note}</div></div>;
}

function Status({ name, text }: { name: string; text: string }) {
  return <div style={styles.statusRow}><span><span style={styles.dot}>●</span> {name}</span><span style={styles.muted}>{text}</span></div>;
}

function formatDate(value: string | null) {
  if (!value) return "日期未提供";
  const d = new Date(value);
  if (Number.isNaN(d.getTime()) || d.getFullYear() <= 1971) return "日期未提供";
  return d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#f5f7fb", color: "#172033", padding: "36px", fontFamily: "Arial, 'Noto Sans TC', sans-serif" },
  loginPage: { minHeight: "100vh", display: "grid", placeItems: "center", background: "#eef3fb", padding: 24 },
  loginCard: { width: "min(420px, 92vw)", background: "white", borderRadius: 24, padding: 32, boxShadow: "0 20px 60px rgba(30,55,90,.12)" },
  header: { display: "flex", justifyContent: "space-between", gap: 20, alignItems: "flex-start", maxWidth: 1400, margin: "0 auto 24px" },
  title: { fontSize: 32, margin: "8px 0" }, loginTitle: { fontSize: 30, margin: "12px 0 8px" },
  badge: { display: "inline-block", fontSize: 12, fontWeight: 700, letterSpacing: 1, color: "#315caa", background: "#eaf1ff", padding: "7px 10px", borderRadius: 999 },
  muted: { color: "#758096", fontSize: 14 }, error: { color: "#b42318" }, notice: { maxWidth: 1400, margin: "0 auto 20px", padding: "12px 16px", background: "#eef6ff", border: "1px solid #d6e7ff", borderRadius: 12 },
  actions: { display: "flex", gap: 8, flexWrap: "wrap" },
  primary: { border: 0, borderRadius: 10, padding: "11px 16px", background: "#2357a5", color: "white", fontWeight: 700, cursor: "pointer" },
  secondary: { border: "1px solid #ccd6e6", borderRadius: 10, padding: "11px 16px", background: "white", color: "#263248", fontWeight: 700, cursor: "pointer" },
  ghost: { border: 0, borderRadius: 10, padding: "11px 14px", background: "transparent", color: "#657086", cursor: "pointer" },
  input: { width: "100%", boxSizing: "border-box", margin: "18px 0 12px", padding: "13px 14px", border: "1px solid #ccd6e6", borderRadius: 10, fontSize: 16 },
  statsGrid: { maxWidth: 1400, margin: "0 auto 22px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14 },
  stat: { background: "white", borderRadius: 18, padding: 20, boxShadow: "0 4px 18px rgba(30,55,90,.05)" }, statLabel: { fontSize: 14, fontWeight: 700 }, statValue: { fontSize: 34, fontWeight: 800, margin: "6px 0" },
  toolbar: { maxWidth: 1400, margin: "0 auto 18px", background: "white", borderRadius: 18, padding: 18 }, chips: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 },
  chip: { border: "1px solid #dce3ee", background: "white", borderRadius: 999, padding: "8px 11px", cursor: "pointer" }, chipActive: { border: "1px solid #2357a5", background: "#2357a5", color: "white", borderRadius: 999, padding: "8px 11px", cursor: "pointer" },
  contentGrid: { maxWidth: 1400, margin: "0 auto", display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(280px, .8fr)", gap: 18 },
  panel: { background: "white", borderRadius: 20, padding: 22, boxShadow: "0 4px 18px rgba(30,55,90,.05)" }, panelHeader: { display: "flex", justifyContent: "space-between" }, panelTitle: { margin: "0 0 4px", fontSize: 20 },
  newsRow: { display: "flex", gap: 14, padding: "17px 0", borderBottom: "1px solid #edf0f5" }, sourcePill: { alignSelf: "flex-start", minWidth: 74, textAlign: "center", fontSize: 12, fontWeight: 700, color: "#315caa", background: "#edf3ff", padding: "7px 9px", borderRadius: 999 },
  newsTitle: { color: "#172033", textDecoration: "none", fontWeight: 700, lineHeight: 1.55 }, meta: { marginTop: 7, color: "#8a94a7", fontSize: 12 }, empty: { color: "#8a94a7", padding: "28px 0" },
  statusRow: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "13px 0", borderBottom: "1px solid #edf0f5", fontSize: 14 }, dot: { color: "#2e9b67" }, infoBox: { marginTop: 18, padding: 16, background: "#f7f9fc", borderRadius: 14 },
};
