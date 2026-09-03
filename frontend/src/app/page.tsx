"use client";

import { useEffect, useMemo, useState } from "react";

type NewsItem = {
  title: string;
  url: string;
  source: string;
  publisher?: string;
  publish_time: string;
  keyword: string;
  task: string;
};

type HealthItem = {
  task: string;
  source: string;
  status: string;
  count: number;
  error?: string | null;
};

type Feed = {
  updated_at: string | null;
  keywords: string[];
  items: NewsItem[];
  source_health: HealthItem[];
  summary: {
    total: number;
    fresh_this_run: number;
    healthy_tasks: number;
    failed_tasks: number;
  };
};

const SOCIAL = new Set(["Dcard", "PTT", "Threads", "Instagram"]);

export default function Home() {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/data/news.json?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setFeed(await res.json());
    } catch (err: any) {
      setError(`資料載入失敗：${err?.message || "未知錯誤"}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  const sources = useMemo(() => {
    return Array.from(new Set((feed?.items || []).map(item => item.source))).sort();
  }, [feed]);

  const filtered = useMemo(() => {
    const text = query.trim().toLowerCase();
    return (feed?.items || []).filter(item => {
      if (keyword && item.keyword !== keyword) return false;
      if (source && item.source !== source) return false;
      if (text) {
        const haystack = `${item.title} ${item.source} ${item.publisher || ""}`.toLowerCase();
        if (!haystack.includes(text)) return false;
      }
      return true;
    });
  }, [feed, keyword, source, query]);

  const stats = useMemo(() => {
    const items = feed?.items || [];
    const today = new Date().toLocaleDateString("zh-TW", { timeZone: "Asia/Taipei" });
    const todayCount = items.filter(item => {
      const d = new Date(item.publish_time);
      return !Number.isNaN(d.getTime()) && d.toLocaleDateString("zh-TW", { timeZone: "Asia/Taipei" }) === today;
    }).length;
    return {
      total: items.length,
      today: todayCount,
      social: items.filter(item => SOCIAL.has(item.source)).length,
      sources: new Set(items.map(item => item.source)).size,
    };
  }, [feed]);

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <div>
          <div style={styles.badge}>NTUE Opinion Monitor · Resilient Tasks</div>
          <h1 style={styles.title}>國北教大輿情監測</h1>
          <p style={styles.muted}>公開新聞與社群來源自動彙整；各來源獨立執行，單一來源失敗不影響其他來源。</p>
        </div>
        <div style={styles.headerRight}>
          <div style={styles.updated}>最後更新：{formatUpdated(feed?.updated_at)}</div>
          <button onClick={refresh} style={styles.primary}>{loading ? "更新中…" : "重新讀取"}</button>
        </div>
      </header>

      {error && <div style={styles.errorBox}>{error}</div>}

      <section style={styles.statsGrid}>
        <Stat label="目前資料" value={stats.total} note="近 30 天相關內容" />
        <Stat label="今日內容" value={stats.today} note="依原始發布日期" />
        <Stat label="社群／論壇" value={stats.social} note="Dcard・PTT・Threads・IG" />
        <Stat label="實際來源" value={stats.sources} note="新聞媒體與社群平台" />
      </section>

      <section style={styles.filterPanel}>
        <div style={styles.filterGroup}>
          <span style={styles.filterLabel}>關鍵字</span>
          <div style={styles.chips}>
            <Chip active={!keyword} onClick={() => setKeyword("")}>全部</Chip>
            {(feed?.keywords || []).map(k => <Chip key={k} active={keyword === k} onClick={() => setKeyword(k)}>{k}</Chip>)}
          </div>
        </div>
        <div style={styles.filterRow}>
          <select value={source} onChange={e => setSource(e.target.value)} style={styles.select}>
            <option value="">全部來源</option>
            {sources.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜尋標題、來源…" style={styles.search} />
          {(keyword || source || query) && <button onClick={() => { setKeyword(""); setSource(""); setQuery(""); }} style={styles.clear}>清除篩選</button>}
        </div>
      </section>

      <section style={styles.contentGrid}>
        <div style={styles.panel}>
          <div style={styles.panelHeader}>
            <div>
              <h2 style={styles.panelTitle}>最新相關內容</h2>
              <p style={styles.muted}>目前顯示 {filtered.length} 筆；日期不明或 1970 異常資料不會進入清單。</p>
            </div>
          </div>

          {loading && !feed ? <p style={styles.empty}>資料載入中…</p> : filtered.length === 0 ? <p style={styles.empty}>目前沒有符合條件的內容。</p> : filtered.map((item, index) => (
            <article key={`${item.url}-${index}`} style={styles.newsRow}>
              <div style={SOCIAL.has(item.source) ? styles.socialPill : styles.sourcePill}>{item.source}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <a href={item.url} target="_blank" rel="noreferrer" style={styles.newsTitle}>{item.title}</a>
                <div style={styles.meta}>
                  {item.publisher && item.publisher !== item.source ? `${item.publisher} · ` : ""}{item.keyword} · {formatDate(item.publish_time)}
                </div>
              </div>
            </article>
          ))}
        </div>

        <aside style={styles.panel}>
          <h2 style={styles.panelTitle}>來源健康狀態</h2>
          <p style={styles.muted}>每次收集都分開記錄，某一來源失敗時仍保留其他來源結果。</p>
          {(feed?.source_health || []).map(h => (
            <div key={h.task} style={styles.statusRow}>
              <div>
                <span style={h.status === "healthy" ? styles.dotOk : h.status === "failed" ? styles.dotBad : styles.dotWait}>●</span>
                <strong>{h.source}</strong>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={styles.statusCount}>{h.count} 筆</div>
                <div style={styles.statusText}>{statusText(h.status)}</div>
              </div>
            </div>
          ))}
          <div style={styles.infoBox}>
            <strong>目前正式架構</strong>
            <p style={{ ...styles.muted, marginBottom: 0 }}>GitHub Actions 定時收集 → JSON 保存 → Vercel 自動部署。網站不再依賴 Render 或外部資料庫，因此不會因資料庫連線或冷啟動整站失效。</p>
          </div>
        </aside>
      </section>
    </main>
  );
}

function Stat({ label, value, note }: { label: string; value: number; note: string }) {
  return <div style={styles.stat}><div style={styles.statLabel}>{label}</div><div style={styles.statValue}>{value}</div><div style={styles.muted}>{note}</div></div>;
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button onClick={onClick} style={active ? styles.chipActive : styles.chip}>{children}</button>;
}

function formatDate(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime()) || d.getFullYear() <= 1971) return "日期未提供";
  return d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function formatUpdated(value?: string | null) {
  if (!value) return "尚未完成首次收集";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "未知";
  return d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function statusText(value: string) {
  if (value === "healthy") return "正常";
  if (value === "failed") return "本輪失敗";
  return "等待首次執行";
}

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#f5f7fb", color: "#182033", padding: "34px 28px 50px", fontFamily: "Arial, 'Noto Sans TC', sans-serif" },
  header: { maxWidth: 1420, margin: "0 auto 24px", display: "flex", justifyContent: "space-between", gap: 24, alignItems: "flex-start", flexWrap: "wrap" },
  headerRight: { display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", justifyContent: "flex-end" },
  badge: { display: "inline-block", fontSize: 12, fontWeight: 800, letterSpacing: .7, color: "#315caa", background: "#e9f1ff", padding: "7px 11px", borderRadius: 999 },
  title: { fontSize: 34, lineHeight: 1.2, margin: "9px 0 8px" },
  muted: { color: "#758096", fontSize: 14, lineHeight: 1.6 },
  updated: { color: "#667085", fontSize: 13 },
  primary: { border: 0, borderRadius: 11, padding: "11px 17px", background: "#2458a6", color: "white", fontWeight: 800, cursor: "pointer" },
  errorBox: { maxWidth: 1420, margin: "0 auto 18px", padding: "13px 16px", color: "#a31616", background: "#fff0f0", border: "1px solid #ffd1d1", borderRadius: 12 },
  statsGrid: { maxWidth: 1420, margin: "0 auto 18px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14 },
  stat: { background: "white", borderRadius: 18, padding: 20, boxShadow: "0 4px 18px rgba(30,55,90,.05)" },
  statLabel: { fontSize: 14, fontWeight: 800 }, statValue: { fontSize: 35, fontWeight: 850, margin: "7px 0" },
  filterPanel: { maxWidth: 1420, margin: "0 auto 18px", background: "white", borderRadius: 18, padding: 18, boxShadow: "0 4px 18px rgba(30,55,90,.04)" },
  filterGroup: { marginBottom: 14 }, filterLabel: { display: "block", fontWeight: 800, fontSize: 14, marginBottom: 10 },
  chips: { display: "flex", flexWrap: "wrap", gap: 8 },
  chip: { border: "1px solid #d9e1ed", background: "white", borderRadius: 999, padding: "8px 12px", color: "#475467", cursor: "pointer" },
  chipActive: { border: "1px solid #2458a6", background: "#2458a6", color: "white", borderRadius: 999, padding: "8px 12px", cursor: "pointer" },
  filterRow: { display: "flex", gap: 10, flexWrap: "wrap" },
  select: { minWidth: 160, padding: "10px 12px", border: "1px solid #d9e1ed", borderRadius: 10, background: "white" },
  search: { flex: "1 1 250px", minWidth: 210, padding: "10px 13px", border: "1px solid #d9e1ed", borderRadius: 10, fontSize: 14 },
  clear: { border: 0, background: "#f2f4f7", borderRadius: 10, padding: "10px 13px", color: "#475467", cursor: "pointer" },
  contentGrid: { maxWidth: 1420, margin: "0 auto", display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(285px, .72fr)", gap: 18 },
  panel: { background: "white", borderRadius: 20, padding: 22, boxShadow: "0 4px 18px rgba(30,55,90,.05)" },
  panelHeader: { display: "flex", justifyContent: "space-between", gap: 12 }, panelTitle: { margin: "0 0 5px", fontSize: 20 },
  newsRow: { display: "flex", gap: 14, padding: "17px 0", borderBottom: "1px solid #edf0f5" },
  sourcePill: { alignSelf: "flex-start", minWidth: 78, textAlign: "center", fontSize: 12, fontWeight: 800, color: "#315caa", background: "#edf3ff", padding: "7px 9px", borderRadius: 999 },
  socialPill: { alignSelf: "flex-start", minWidth: 78, textAlign: "center", fontSize: 12, fontWeight: 800, color: "#7a3e00", background: "#fff3e6", padding: "7px 9px", borderRadius: 999 },
  newsTitle: { color: "#172033", textDecoration: "none", fontWeight: 750, lineHeight: 1.6, overflowWrap: "anywhere" },
  meta: { marginTop: 7, color: "#8a94a7", fontSize: 12, lineHeight: 1.5 }, empty: { color: "#8a94a7", padding: "30px 0" },
  statusRow: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "13px 0", borderBottom: "1px solid #edf0f5", fontSize: 14 },
  dotOk: { color: "#2d9a66", marginRight: 7 }, dotBad: { color: "#d04444", marginRight: 7 }, dotWait: { color: "#98a2b3", marginRight: 7 },
  statusCount: { fontWeight: 800, fontSize: 13 }, statusText: { color: "#98a2b3", fontSize: 11, marginTop: 2 },
  infoBox: { marginTop: 18, padding: 16, background: "#f7f9fc", borderRadius: 14 },
};
