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

  async function refresh(){
    setLoading(true);setError("");
    try{const r=await fetch(`/data/news.json?t=${Date.now()}`,{cache:"no-store"});if(!r.ok)throw new Error(`HTTP ${r.status}`);setFeed(await r.json())}
    catch(e:any){setError(`資料載入失敗：${e?.message||"未知錯誤"}`)}finally{setLoading(false)}
  }
  useEffect(()=>{refresh()},[]);

  const filtered=useMemo(()=>{const q=query.trim().toLowerCase();return (feed?.items||[]).filter(x=>!q||`${x.title} ${x.source} ${x.publisher||""}`.toLowerCase().includes(q))},[feed,query]);
  const news=filtered.filter(x=>!SOCIAL.has(x.source));
  const social=filtered.filter(x=>SOCIAL.has(x.source));
  const all=feed?.items||[];
  const today=new Date().toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"});
  const todayCount=all.filter(x=>x.publish_time&&new Date(x.publish_time).toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"})===today).length;

  return <main className="dashboard">
    <style jsx global>{`
      *{box-sizing:border-box}.dashboard{min-height:100vh;background:#f3f6fa;color:#14213d;padding:28px;font-family:Arial,"Noto Sans TC",sans-serif}
      .hero{max-width:1480px;margin:0 auto 16px;background:#fff;border-radius:18px;padding:20px 24px;display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap;border-top:5px solid #0d2147;box-shadow:0 5px 20px rgba(20,45,80,.05)}
      .brand{display:flex;align-items:center;gap:15px}.brand img{width:72px;height:68px;object-fit:contain}.school{font-size:19px;font-weight:900;color:#0d2147}.en{font-size:12px;font-family:Georgia,serif;color:#667085;margin-top:2px}.hero h1{font-size:29px;margin:7px 0 0;color:#102a56}
      .actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;justify-content:flex-end}.actions a,.actions button{padding:11px 15px;border-radius:10px;font-weight:800;text-decoration:none;font-size:14px}.primary{background:#0d2147;color:#fff}.secondary{background:#e8eef7;color:#0d2147}.refresh{border:1px solid #cbd5e1;background:#fff;color:#0d2147;cursor:pointer}.updated{width:100%;text-align:right;font-size:12px;color:#6b7280}
      .error{max-width:1480px;margin:0 auto 14px;background:#fff0f0;color:#a11919;padding:12px;border-radius:10px}.summary{max-width:1480px;margin:0 auto 16px;display:grid;grid-template-columns:repeat(4,minmax(130px,1fr)) minmax(230px,2fr);gap:10px}.stat,.search{background:#fff;border:1px solid #e5eaf1;border-radius:13px}.stat{padding:14px 16px}.stat span{display:block;font-size:12px;color:#667085;font-weight:800}.stat b{display:block;font-size:28px;color:#0d2147;margin-top:3px}.search{width:100%;padding:12px 14px;font-size:14px;outline:none}
      .columns{max-width:1480px;margin:0 auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.panel{background:#fff;border-radius:16px;padding:19px;border:1px solid #e5eaf1;min-width:0}.panel-head{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #0d2147;padding-bottom:10px}.panel-head h2{margin:0;font-size:20px;color:#0d2147}.count{font-size:13px;color:#667085}.row{display:flex;gap:11px;padding:14px 0;border-bottom:1px solid #edf0f4}.pill{align-self:flex-start;min-width:72px;text-align:center;font-size:11.5px;font-weight:800;padding:6px 8px;border-radius:999px}.pill-news{color:#315caa;background:#edf3ff}.pill-social{color:#7a3e00;background:#fff3e6}.item-title{color:#14213d;text-decoration:none;font-weight:750;line-height:1.55;overflow-wrap:anywhere}.meta{font-size:11.5px;color:#8a94a7;margin-top:5px}.empty{padding:30px;color:#8a94a7;text-align:center}
      @media(max-width:980px){.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.search{grid-column:1/-1}.columns{grid-template-columns:1fr}}@media(max-width:620px){.dashboard{padding:14px}.hero{padding:16px}.brand img{width:58px;height:55px}.hero h1{font-size:23px}.summary{grid-template-columns:repeat(2,minmax(0,1fr))}}
    `}</style>

    <section className="hero">
      <div className="brand"><img src={NTUE_LOGO_DATA_URI} alt="國立臺北教育大學校徽"/><div><div className="school">國立臺北教育大學</div><div className="en">National Taipei University of Education</div><h1>媒體與公開輿情監測</h1></div></div>
      <div className="actions"><a href="/reports" className="primary">AI 輿情報告</a><a href="/settings" className="secondary">設定</a><button onClick={refresh} className="refresh">{loading?"更新中…":"重新整理"}</button><div className="updated">最後更新：{fmtUpdated(feed?.updated_at)}</div></div>
    </section>

    {error&&<div className="error">{error}</div>}

    <section className="summary">
      <div className="stat"><span>目前資料</span><b>{all.length}</b></div><div className="stat"><span>今日新增</span><b>{todayCount}</b></div><div className="stat"><span>新聞報導</span><b>{all.filter(x=>!SOCIAL.has(x.source)).length}</b></div><div className="stat"><span>社群討論</span><b>{all.filter(x=>SOCIAL.has(x.source)).length}</b></div><input className="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜尋標題或來源"/>
    </section>

    <section className="columns"><FeedColumn title="新聞報導" items={news}/><FeedColumn title="社群討論" items={social} social/></section>
  </main>
}

function FeedColumn({title,items,social=false}:{title:string;items:NewsItem[];social?:boolean}){return <section className="panel"><div className="panel-head"><h2>{title}</h2><span className="count">{items.length} 筆</span></div>{items.length===0?<div className="empty">目前沒有符合條件的內容</div>:items.map((x,i)=><article className="row" key={`${x.url}-${i}`}><div className={`pill ${social?"pill-social":"pill-news"}`}>{x.source}</div><div style={{minWidth:0,flex:1}}><a href={x.url} target="_blank" rel="noreferrer" className="item-title">{x.title}</a><div className="meta">{x.publisher&&x.publisher!==x.source?`${x.publisher} · `:""}{fmtDate(x.publish_time)}</div></div></article>)}</section>}
function fmtDate(v?:string|null){if(!v)return"日期未提供";const d=new Date(v);return Number.isNaN(d.getTime())?"日期未提供":d.toLocaleString("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}
function fmtUpdated(v?:string|null){if(!v)return"尚未更新";const d=new Date(v);return Number.isNaN(d.getTime())?"未知":d.toLocaleString("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}
