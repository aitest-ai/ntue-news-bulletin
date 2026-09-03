"use client";

import { useEffect, useMemo, useState } from "react";

type FeedItem = {
  title: string;
  url: string;
  source: string;
  publisher?: string;
  publish_time?: string | null;
  keyword?: string;
  task?: string;
};

type Feed = { updated_at: string | null; items: FeedItem[] };

type Topic = { topic: string; trend: string; sentiment: string; volume: number; explanation: string; sources: string[] };
type Risk = { category: string; level: string; reason: string };
type Action = { unit: string; action: string; priority: string };
type Notable = { title: string; source: string; reason: string };
type Report = {
  executive_title: string;
  signal: string;
  overall_risk: string;
  immediate_action: boolean;
  immediate_action_reason: string;
  confidence_note: string;
  top_points: string[];
  summary: string;
  topics: Topic[];
  sentiment_counts: { positive: number; neutral: number; negative: number; uncertain: number };
  risk_matrix: Risk[];
  recommended_actions: Action[];
  notable_items: Notable[];
  conclusion: string;
};

export default function ReportsPage() {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [days, setDays] = useState(7);
  const [password, setPassword] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`/data/news.json?t=${Date.now()}`, { cache: "no-store" })
      .then(r => r.json())
      .then(setFeed)
      .catch(() => setError("無法讀取目前輿情資料"));
  }, []);

  const selectedItems = useMemo(() => {
    const cutoff = Date.now() - days * 86400000;
    return (feed?.items || []).filter(item => {
      if (!item.publish_time) return true;
      const t = new Date(item.publish_time).getTime();
      return Number.isNaN(t) ? true : t >= cutoff;
    });
  }, [feed, days]);

  const sourceStats = useMemo(() => {
    const m = new Map<string, number>();
    selectedItems.forEach(i => m.set(i.source, (m.get(i.source) || 0) + 1));
    return Array.from(m.entries()).sort((a,b) => b[1] - a[1]);
  }, [selectedItems]);

  async function generate() {
    setLoading(true); setError("");
    try {
      const res = await fetch("/api/ai-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, periodDays: days, items: selectedItems }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || "產生失敗");
      setReport(data.report); setMeta(data.meta);
    } catch (e: any) {
      setError(e?.message || "產生報告失敗");
    } finally { setLoading(false); }
  }

  return <main className="report-shell">
    <style jsx global>{`
      body{margin:0;background:#eef2f7;color:#111827;font-family:Arial,"Noto Sans TC",sans-serif}
      .report-shell{padding:24px}.toolbar{max-width:1100px;margin:0 auto 18px;background:white;padding:16px;border-radius:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;box-shadow:0 5px 20px rgba(20,40,80,.08)}
      .toolbar input,.toolbar select{padding:10px 12px;border:1px solid #cfd7e5;border-radius:9px}.btn{border:0;border-radius:9px;padding:10px 15px;font-weight:700;cursor:pointer}.primary{background:#102a56;color:white}.secondary{background:#e8eef7;color:#102a56}
      .paper{width:min(1100px,calc(100vw - 48px));margin:0 auto;background:white;padding:28px 34px;box-sizing:border-box;box-shadow:0 8px 30px rgba(30,50,80,.12)}
      .mast{text-align:center;border-bottom:3px solid #102a56;padding-bottom:14px}.mast h1{margin:4px 0;font-size:30px;color:#0d2147}.mast .en{font-family:Georgia,serif;font-size:15px}.meta-row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:2px solid #102a56;font-weight:700}
      .grid2{display:grid;grid-template-columns:1.3fr .85fr;gap:14px;margin-top:14px}.section{border:1px solid #9cabbd}.section h2{margin:0;background:#102a56;color:white;font-size:17px;padding:8px 12px}.section-body{padding:12px 14px;line-height:1.65}.signal{font-size:22px;font-weight:800;text-align:center;padding:18px}.signal small{display:block;font-size:13px;color:#667085;margin-top:8px;font-weight:500}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.stat{border:1px solid #d5dde8;padding:10px;text-align:center}.stat b{display:block;font-size:24px;margin-top:3px}.topic{border-bottom:1px solid #e5e7eb;padding:9px 0}.topic:last-child{border:0}.tag{display:inline-block;padding:2px 7px;border-radius:999px;background:#edf2f8;font-size:12px;margin-right:5px}.risk-table{width:100%;border-collapse:collapse}.risk-table th,.risk-table td{border:1px solid #b9c3d1;padding:7px;text-align:left;vertical-align:top;font-size:13px}.risk-table th{background:#edf2f8}.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.action{border:1px solid #ccd5e1;padding:10px}.muted{color:#667085;font-size:12px}.error{max-width:1100px;margin:0 auto 14px;background:#fff1f1;color:#a11919;padding:12px;border-radius:10px}.empty{padding:70px;text-align:center;color:#667085}
      @media(max-width:800px){.grid2,.actions{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.paper{width:100%;padding:18px}.meta-row{flex-direction:column}}
      @media print{@page{size:A4;margin:8mm}body{background:white}.no-print{display:none!important}.report-shell{padding:0}.paper{width:100%;box-shadow:none;padding:0}.section{break-inside:avoid}.grid2{break-inside:avoid}}
    `}</style>

    <div className="toolbar no-print">
      <a href="/" className="btn secondary" style={{textDecoration:"none"}}>← 返回監測首頁</a>
      <select value={days} onChange={e=>setDays(Number(e.target.value))}><option value={1}>最近 24 小時</option><option value={3}>最近 3 天</option><option value={7}>最近 7 天</option><option value={14}>最近 14 天</option><option value={30}>最近 30 天</option></select>
      <input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="管理密碼" />
      <button className="btn primary" onClick={generate} disabled={loading}>{loading?"Gemini 分析中…":"產生 AI 輿情報告"}</button>
      {report && <button className="btn secondary" onClick={()=>window.print()}>列印／另存 PDF</button>}
      <span className="muted">本期可分析 {selectedItems.length} 筆資料</span>
    </div>
    {error && <div className="error no-print">{error}</div>}

    {!report ? <div className="paper empty">選擇監測期間並輸入管理密碼後，由 Gemini 2.5 Flash 產生固定格式輿情報告。</div> :
    <article className="paper">
      <header className="mast"><div style={{fontSize:23,fontWeight:800}}>國立臺北教育大學</div><div className="en">National Taipei University of Education</div><h1>媒體與公開輿情趨勢報告</h1><div className="en">Media & Public Opinion Monitoring Report</div></header>
      <div className="meta-row"><span>監測期間：最近 {days} 天</span><span>資料筆數：{meta?.analyzed_items ?? selectedItems.length}</span><span>AI 模型：Gemini 2.5 Flash</span><span>燈號：{signalIcon(report.signal)} {report.signal}</span></div>

      <div className="grid2">
        <section className="section"><h2>一、近期三大重點</h2><div className="section-body"><ol>{report.top_points.map((x,i)=><li key={i}>{x}</li>)}</ol></div></section>
        <section className="section"><h2>二、是否需立即處理</h2><div className="signal">{report.immediate_action?"⚠️ 建議立即處理":"✅ 目前不需立即處理"}<small>{report.immediate_action_reason}</small></div></section>
      </div>

      <div className="grid2">
        <section className="section"><h2>三、監測量與來源</h2><div className="section-body"><div className="stats"><div className="stat">總資料<b>{selectedItems.length}</b></div><div className="stat">新聞媒體<b>{selectedItems.filter(i=>!["Dcard","PTT","Threads","Instagram"].includes(i.source)).length}</b></div><div className="stat">社群／論壇<b>{selectedItems.filter(i=>["Dcard","PTT","Threads","Instagram"].includes(i.source)).length}</b></div><div className="stat">來源數<b>{sourceStats.length}</b></div></div><p className="muted">主要來源：{sourceStats.slice(0,8).map(([s,n])=>`${s} ${n}`).join("、")}</p></div></section>
        <section className="section"><h2>四、AI 輿情摘要</h2><div className="section-body">{report.summary}<p className="muted">可信度提示：{report.confidence_note}</p></div></section>
      </div>

      <section className="section" style={{marginTop:14}}><h2>五、近期討論話題與趨勢</h2><div className="section-body">{report.topics.map((t,i)=><div className="topic" key={i}><b>{t.topic}</b> <span className="tag">{t.trend}</span><span className="tag">{t.sentiment}</span><span className="tag">約 {t.volume} 筆</span><div>{t.explanation}</div><div className="muted">來源：{t.sources.join("、")}</div></div>)}</div></section>

      <div className="grid2">
        <section className="section"><h2>六、情緒訊號</h2><div className="section-body"><div className="stats"><div className="stat">負面<b>{report.sentiment_counts.negative}</b></div><div className="stat">中性<b>{report.sentiment_counts.neutral}</b></div><div className="stat">正面<b>{report.sentiment_counts.positive}</b></div><div className="stat">不確定<b>{report.sentiment_counts.uncertain}</b></div></div></div></section>
        <section className="section"><h2>七、整體風險研判</h2><div className="signal">{signalIcon(report.signal)} {report.signal}<small>綜合風險：{report.overall_risk}</small></div></section>
      </div>

      <section className="section" style={{marginTop:14}}><h2>八、風險評估</h2><div className="section-body"><table className="risk-table"><thead><tr><th>評估項目</th><th>等級</th><th>說明</th></tr></thead><tbody>{report.risk_matrix.map((r,i)=><tr key={i}><td>{r.category}</td><td>{r.level}</td><td>{r.reason}</td></tr>)}</tbody></table></div></section>

      <section className="section" style={{marginTop:14}}><h2>九、建議處置分工</h2><div className="section-body actions">{report.recommended_actions.map((a,i)=><div className="action" key={i}><b>{a.unit}</b><div className="tag">{a.priority}</div><p>{a.action}</p></div>)}</div></section>

      {report.notable_items?.length>0 && <section className="section" style={{marginTop:14}}><h2>十、值得持續觀察的內容</h2><div className="section-body"><ul>{report.notable_items.map((n,i)=><li key={i}><b>{n.title}</b>（{n.source}）－{n.reason}</li>)}</ul></div></section>}

      <section className="section" style={{marginTop:14}}><h2>十一、結論</h2><div className="section-body">{report.conclusion}</div></section>
      <div style={{textAlign:"center",marginTop:18,fontWeight:700,color:"#102a56"}}>系統自動彙整 · AI 輔助研判 · 最終判斷仍應由校方人員確認</div>
    </article>}
  </main>;
}

function signalIcon(s:string){return s==="紅燈"?"🔴":s==="橙燈"?"🟠":s==="黃燈"?"🟡":"🟢"}
