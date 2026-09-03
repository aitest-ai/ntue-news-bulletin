"use client";

import { useEffect, useMemo, useState } from "react";
import { NTUE_LOGO_DATA_URI } from "./branding";

type NewsItem={title:string;url:string;source:string;publisher?:string;publish_time?:string|null;task:string};
type Feed={updated_at:string|null;items:NewsItem[]};
const SOCIAL=new Set(["Dcard","PTT","Threads","Instagram"]);

export default function Home(){
  const [feed,setFeed]=useState<Feed|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [query,setQuery]=useState("");
  const [newsSource,setNewsSource]=useState("");
  const [socialSource,setSocialSource]=useState("");

  async function refresh(){
    setLoading(true);setError("");
    try{const r=await fetch(`/data/news.json?t=${Date.now()}`,{cache:"no-store"});if(!r.ok)throw new Error(`HTTP ${r.status}`);setFeed(await r.json())}
    catch(e:any){setError(`資料載入失敗：${e?.message||"未知錯誤"}`)}finally{setLoading(false)}
  }
  useEffect(()=>{refresh()},[]);

  const all=feed?.items||[];
  const searched=useMemo(()=>{const q=query.trim().toLowerCase();return all.filter(x=>!q||`${x.title} ${x.source} ${x.publisher||""}`.toLowerCase().includes(q))},[all,query]);
  const newsSources=useMemo(()=>Array.from(new Set(all.filter(x=>!SOCIAL.has(x.source)).map(x=>x.source))).sort((a,b)=>a.localeCompare(b,"zh-Hant")),[all]);
  const socialSources=useMemo(()=>Array.from(new Set(all.filter(x=>SOCIAL.has(x.source)).map(x=>x.source))).sort((a,b)=>a.localeCompare(b,"zh-Hant")),[all]);
  const news=searched.filter(x=>!SOCIAL.has(x.source)&&(!newsSource||x.source===newsSource));
  const social=searched.filter(x=>SOCIAL.has(x.source)&&(!socialSource||x.source===socialSource));
  const today=new Date().toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"});
  const todayCount=all.filter(x=>x.publish_time&&new Date(x.publish_time).toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"})===today).length;

  return <main className="dashboard">
    <style jsx global>{`
      *{box-sizing:border-box}.dashboard{min-height:100vh;background:#f3f6fa;color:#14213d;padding:28px;font-family:Arial,"Noto Sans TC",sans-serif}
      .hero{max-width:1480px;margin:0 auto 16px;background:#fff;border-radius:18px;padding:20px 24px;display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap;border-top:5px solid #0d2147;box-shadow:0 5px 20px rgba(20,45,80,.05)}
      .brand{display:flex;align-items:center;gap:15px}.brand img{width:72px;height:68px;object-fit:contain}.school{font-size:19px;font-weight:900;color:#0d2147}.en{font-size:12px;font-family:Georgia,serif;color:#667085;margin-top:2px}.hero h1{font-size:29px;margin:7px 0 0;color:#102a56}
      .actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;justify-content:flex-end}.actions a,.actions button{padding:11px 15px;border-radius:10px;font-weight:800;text-decoration:none;font-size:14px}.primary{background:#0d2147;color:#fff}.secondary{background:#e8eef7;color:#0d2147}.refresh{border:1px solid #cbd5e1;background:#fff;color:#0d2147;cursor:pointer}.updated{width:100%;text-align:right;font-size:12px;color:#6b7280}
      .report-banner{max-width:1480px;margin:0 auto 16px;background:linear-gradient(135deg,#0b1f45 0%,#16396f 100%);border-radius:18px;padding:22px 26px;display:flex;align-items:center;justify-content:space-between;gap:24px;box-shadow:0 10px 28px rgba(13,33,71,.18);color:#fff;overflow:hidden;position:relative}.report-banner:after{content:"";position:absolute;right:-70px;top:-95px;width:240px;height:240px;border-radius:50%;background:rgba(255,255,255,.06)}.report-copy{position:relative;z-index:1}.report-kicker{font-size:12px;font-weight:800;letter-spacing:.12em;opacity:.78}.report-banner h2{margin:5px 0 6px;font-size:25px}.report-banner p{margin:0;color:#dce7f7;font-size:14px;line-height:1.6}.report-cta{position:relative;z-index:1;display:inline-flex;align-items:center;justify-content:center;min-width:190px;padding:14px 20px;border-radius:12px;background:#fff;color:#0d2147;text-decoration:none;font-weight:900;box-shadow:0 4px 16px rgba(0,0,0,.12)}
      .error{max-width:1480px;margin:0 auto 14px;background:#fff0f0;color:#a11919;padding:12px;border-radius:10px}.summary{max-width:1480px;margin:0 auto 16px;display:grid;grid-template-columns:repeat(4,minmax(130px,1fr)) minmax(230px,2fr);gap:10px}.stat,.search{background:#fff;border:1px solid #e5eaf1;border-radius:13px}.stat{padding:14px 16px}.stat span{display:block;font-size:12px;color:#667085;font-weight:800}.stat b{display:block;font-size:28px;color:#0d2147;margin-top:3px}.search{width:100%;padding:12px 14px;font-size:14px;outline:none}
      .columns{max-width:1480px;margin:0 auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.panel{background:#fff;border-radius:16px;padding:19px;border:1px solid #e5eaf1;min-width:0}.panel-head{display:flex;justify-content:space-between;align-items:center;gap:10px;border-bottom:2px solid #0d2147;padding-bottom:10px}.panel-head h2{margin:0;font-size:20px;color:#0d2147}.panel-tools{display:flex;align-items:center;gap:8px}.source-select{max-width:210px;padding:7px 30px 7px 10px;border:1px solid #d5dde8;border-radius:8px;background:#fff;color:#344054;font-size:12.5px}.count{font-size:13px;color:#667085;white-space:nowrap}.row{display:flex;gap:11px;padding:14px 0;border-bottom:1px solid #edf0f4}.pill{align-self:flex-start;min-width:72px;text-align:center;font-size:11.5px;font-weight:800;padding:6px 8px;border-radius:999px}.pill-news{color:#315caa;background:#edf3ff}.pill-social{color:#7a3e00;background:#fff3e6}.item-title{color:#14213d;text-decoration:none;font-weight:750;line-height:1.55;overflow-wrap:anywhere}.meta{font-size:11.5px;color:#8a94a7;margin-top:5px}.empty{padding:30px;color:#8a94a7;text-align:center}
      @media(max-width:1100px){.panel-head{align-items:flex-start;flex-direction:column}.panel-tools{width:100%}.source-select{flex:1;max-width:none}}@media(max-width:980px){.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.search{grid-column:1/-1}.columns{grid-template-columns:1fr}.report-banner{align-items:flex-start}}@media(max-width:620px){.dashboard{padding:14px}.hero{padding:16px}.brand img{width:58px;height:55px}.hero h1{font-size:23px}.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.report-banner{padding:18px;flex-direction:column}.report-banner h2{font-size:21px}.report-cta{width:100%}}
    `}</style>

    <section className="hero">
      <div className="brand"><img src={NTUE_LOGO_DATA_URI} alt="國立臺北教育大學校徽"/><div><div className="school">國立臺北教育大學</div><div className="en">National Taipei University of Education</div><h1>媒體與公開輿情監測</h1></div></div>
      <div className="actions"><a href="/reports" className="primary">AI 輿情報告</a><a href="/settings" className="secondary">設定</a><button onClick={refresh} className="refresh">{loading?"更新中…":"重新整理"}</button><div className="updated">最後更新：{fmtUpdated(feed?.updated_at)}</div></div>
    </section>

    <section className="report-banner">
      <div className="report-copy"><div className="report-kicker">AI PUBLIC OPINION REPORT</div><h2>AI 輿情報告</h2><p>彙整近期新聞與社群討論，快速掌握重要議題、趨勢與風險訊號。</p></div>
      <a href="/reports" className="report-cta">立即產生報告 →</a>
    </section>

    {error&&<div className="error">{error}</div>}

    <section className="summary">
      <div className="stat"><span>目前資料</span><b>{all.length}</b></div><div className="stat"><span>今日新增</span><b>{todayCount}</b></div><div className="stat"><span>新聞報導</span><b>{all.filter(x=>!SOCIAL.has(x.source)).length}</b></div><div className="stat"><span>社群討論</span><b>{all.filter(x=>SOCIAL.has(x.source)).length}</b></div><input className="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜尋標題或來源"/>
    </section>

    <section className="columns">
      <FeedColumn title="新聞報導" items={news} sources={newsSources} selectedSource={newsSource} onSourceChange={setNewsSource}/>
      <FeedColumn title="社群討論" items={social} sources={socialSources} selectedSource={socialSource} onSourceChange={setSocialSource} social/>
    </section>
  </main>
}

function FeedColumn({title,items,sources,selectedSource,onSourceChange,social=false}:{title:string;items:NewsItem[];sources:string[];selectedSource:string;onSourceChange:(value:string)=>void;social?:boolean}){
  return <section className="panel">
    <div className="panel-head"><h2>{title}</h2><div className="panel-tools"><select className="source-select" value={selectedSource} onChange={e=>onSourceChange(e.target.value)}><option value="">全部來源</option>{sources.map(source=><option key={source} value={source}>{source}</option>)}</select><span className="count">{items.length} 筆</span></div></div>
    {items.length===0?<div className="empty">目前沒有符合條件的內容</div>:items.map((x,i)=><article className="row" key={`${x.url}-${i}`}><div className={`pill ${social?"pill-social":"pill-news"}`}>{x.source}</div><div style={{minWidth:0,flex:1}}><a href={x.url} target="_blank" rel="noreferrer" className="item-title">{x.title}</a><div className="meta">{x.publisher&&x.publisher!==x.source?`${x.publisher} · `:""}{fmtDate(x.publish_time)}</div></div></article>)}
  </section>
}
function fmtDate(v?:string|null){if(!v)return"日期未提供";const d=new Date(v);return Number.isNaN(d.getTime())?"日期未提供":d.toLocaleString("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}
function fmtUpdated(v?:string|null){if(!v)return"尚未更新";const d=new Date(v);return Number.isNaN(d.getTime())?"未知":d.toLocaleString("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}
