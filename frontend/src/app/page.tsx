"use client";

import { useEffect, useMemo, useState } from "react";
import { NTUE_LOGO_DATA_URI } from "./branding";

type NewsItem = { title:string; url:string; source:string; publisher?:string; publish_time?:string|null; keyword?:string; task:string };
type HealthItem = { task:string; source:string; status:string; count:number; error?:string|null };
type Feed = { updated_at:string|null; keywords:string[]; items:NewsItem[]; source_health:HealthItem[]; summary?:Record<string,number> };

const SOCIAL = new Set(["Dcard","PTT","Threads","Instagram"]);

export default function Home(){
  const [feed,setFeed]=useState<Feed|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [keyword,setKeyword]=useState("");
  const [source,setSource]=useState("");
  const [query,setQuery]=useState("");

  async function refresh(){
    setLoading(true); setError("");
    try{
      const r=await fetch(`/data/news.json?t=${Date.now()}`,{cache:"no-store"});
      if(!r.ok) throw new Error(`HTTP ${r.status}`);
      setFeed(await r.json());
    }catch(e:any){setError(`資料載入失敗：${e?.message||"未知錯誤"}`)}
    finally{setLoading(false)}
  }
  useEffect(()=>{refresh()},[]);

  const sources=useMemo(()=>Array.from(new Set((feed?.items||[]).map(x=>x.source))).sort(),[feed]);
  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return (feed?.items||[]).filter(x=>{
      if(keyword && x.keyword!==keyword) return false;
      if(source && x.source!==source) return false;
      if(q && !`${x.title} ${x.source} ${x.publisher||""}`.toLowerCase().includes(q)) return false;
      return true;
    });
  },[feed,keyword,source,query]);

  const stats=useMemo(()=>{
    const items=feed?.items||[];
    const today=new Date().toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"});
    const todayCount=items.filter(x=>x.publish_time && new Date(x.publish_time).toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"})===today).length;
    return {total:items.length,today:todayCount,social:items.filter(x=>SOCIAL.has(x.source)).length,sources:new Set(items.map(x=>x.source)).size};
  },[feed]);

  return <main style={s.page}>
    <section style={s.hero}>
      <div style={s.brandBlock}>
        <img src={NTUE_LOGO_DATA_URI} alt="國立臺北教育大學校徽" style={s.logo}/>
        <div><div style={s.school}>國立臺北教育大學</div><div style={s.schoolEn}>National Taipei University of Education</div><h1 style={s.title}>媒體與公開輿情監測</h1></div>
      </div>
      <div style={s.heroActions}>
        <a href="/reports" style={s.reportButton}>產生 AI 輿情報告</a>
        <button onClick={refresh} style={s.refreshButton}>{loading?"更新中…":"重新整理"}</button>
        <div style={s.updated}>最後更新：{fmtUpdated(feed?.updated_at)}</div>
      </div>
    </section>

    {error && <div style={s.error}>{error}</div>}

    <section style={s.statsGrid}>
      <Stat label="目前資料" value={stats.total}/>
      <Stat label="今日內容" value={stats.today}/>
      <Stat label="社群／論壇" value={stats.social}/>
      <Stat label="實際來源" value={stats.sources}/>
    </section>

    <section style={s.filterPanel}>
      <div style={s.chips}><Chip active={!keyword} onClick={()=>setKeyword("")}>全部關鍵字</Chip>{(feed?.keywords||[]).map(k=><Chip key={k} active={keyword===k} onClick={()=>setKeyword(k)}>{k}</Chip>)}</div>
      <div style={s.filterRow}>
        <select value={source} onChange={e=>setSource(e.target.value)} style={s.select}><option value="">全部來源</option>{sources.map(x=><option key={x}>{x}</option>)}</select>
        <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜尋標題或來源" style={s.search}/>
        {(keyword||source||query)&&<button onClick={()=>{setKeyword("");setSource("");setQuery("")}} style={s.clear}>清除</button>}
      </div>
    </section>

    <section style={s.contentGrid}>
      <div style={s.panel}>
        <div style={s.panelHeader}><h2 style={s.panelTitle}>最新輿情</h2><span style={s.count}>{filtered.length} 筆</span></div>
        {loading&&!feed?<div style={s.empty}>資料載入中…</div>:filtered.length===0?<div style={s.empty}>目前沒有符合條件的內容</div>:filtered.map((x,i)=><article key={`${x.url}-${i}`} style={s.newsRow}>
          <div style={SOCIAL.has(x.source)?s.socialPill:s.sourcePill}>{x.source}</div>
          <div style={{minWidth:0,flex:1}}><a href={x.url} target="_blank" rel="noreferrer" style={s.newsTitle}>{x.title}</a><div style={s.meta}>{x.publisher&&x.publisher!==x.source?`${x.publisher} · `:""}{x.keyword||""}{x.keyword?" · ":""}{fmtDate(x.publish_time)}</div></div>
        </article>)}
      </div>
      <aside style={s.sidePanel}>
        <a href="/reports" style={s.reportCard}><div style={{fontSize:13,opacity:.8}}>主管快速入口</div><div style={{fontSize:22,fontWeight:900,margin:"5px 0"}}>AI 輿情報告</div><div style={{fontSize:13,lineHeight:1.5}}>自動整理近期重點、趨勢、風險與建議處置</div><div style={{marginTop:14,fontWeight:800}}>立即產生 →</div></a>
        <div style={s.panel}><h2 style={s.panelTitle}>來源狀態</h2>{(feed?.source_health||[]).map(h=><div key={h.task} style={s.statusRow}><span><span style={{color:h.status==="healthy"?"#2d9a67":"#c2413d"}}>●</span> {h.source}</span><strong>{h.count}</strong></div>)}</div>
      </aside>
    </section>
  </main>
}

function Stat({label,value}:{label:string;value:number}){return <div style={s.stat}><div style={s.statLabel}>{label}</div><div style={s.statValue}>{value}</div></div>}
function Chip({active,onClick,children}:{active:boolean;onClick:()=>void;children:React.ReactNode}){return <button onClick={onClick} style={active?s.chipActive:s.chip}>{children}</button>}
function fmtDate(v?:string|null){if(!v)return"日期未提供";const d=new Date(v);return Number.isNaN(d.getTime())?"日期未提供":d.toLocaleString("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}
function fmtUpdated(v?:string|null){if(!v)return"尚未更新";const d=new Date(v);return Number.isNaN(d.getTime())?"未知":d.toLocaleString("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}

const s:Record<string,React.CSSProperties>={
  page:{minHeight:"100vh",background:"#f3f6fa",color:"#14213d",padding:"28px 28px 48px",fontFamily:"Arial,'Noto Sans TC',sans-serif"},
  hero:{maxWidth:1420,margin:"0 auto 20px",background:"white",borderRadius:18,padding:"20px 24px",display:"flex",justifyContent:"space-between",alignItems:"center",gap:20,flexWrap:"wrap",boxShadow:"0 5px 20px rgba(20,45,80,.06)",borderTop:"5px solid #0d2147"},
  brandBlock:{display:"flex",alignItems:"center",gap:16},logo:{width:76,height:70,objectFit:"contain"},school:{fontSize:20,fontWeight:900,color:"#0d2147"},schoolEn:{fontSize:12,fontFamily:"Georgia,serif",color:"#596579",marginTop:2},title:{fontSize:30,margin:"8px 0 0",color:"#102a56"},heroActions:{display:"flex",alignItems:"center",gap:9,flexWrap:"wrap",justifyContent:"flex-end"},reportButton:{background:"#0d2147",color:"white",textDecoration:"none",padding:"13px 18px",borderRadius:10,fontWeight:900,boxShadow:"0 4px 12px rgba(13,33,71,.18)"},refreshButton:{border:"1px solid #cbd5e1",background:"white",padding:"12px 15px",borderRadius:10,fontWeight:800,cursor:"pointer"},updated:{fontSize:12,color:"#6b7280",width:"100%",textAlign:"right"},
  error:{maxWidth:1420,margin:"0 auto 16px",background:"#fff0f0",color:"#a11919",padding:12,borderRadius:10},statsGrid:{maxWidth:1420,margin:"0 auto 16px",display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:12},stat:{background:"white",padding:"18px 20px",borderRadius:14,border:"1px solid #e5eaf1"},statLabel:{fontSize:13,fontWeight:800,color:"#667085"},statValue:{fontSize:34,fontWeight:900,marginTop:4,color:"#0d2147"},
  filterPanel:{maxWidth:1420,margin:"0 auto 16px",background:"white",padding:16,borderRadius:14,border:"1px solid #e5eaf1"},chips:{display:"flex",gap:7,flexWrap:"wrap",marginBottom:12},chip:{border:"1px solid #d5dde8",background:"white",borderRadius:999,padding:"7px 11px",cursor:"pointer"},chipActive:{border:"1px solid #0d2147",background:"#0d2147",color:"white",borderRadius:999,padding:"7px 11px",cursor:"pointer"},filterRow:{display:"flex",gap:8,flexWrap:"wrap"},select:{padding:"10px 12px",border:"1px solid #d5dde8",borderRadius:9,background:"white"},search:{flex:"1 1 240px",padding:"10px 12px",border:"1px solid #d5dde8",borderRadius:9},clear:{border:0,background:"#eef2f6",padding:"10px 12px",borderRadius:9,cursor:"pointer"},
  contentGrid:{maxWidth:1420,margin:"0 auto",display:"grid",gridTemplateColumns:"minmax(0,2.2fr) minmax(270px,.75fr)",gap:16},panel:{background:"white",borderRadius:16,padding:20,border:"1px solid #e5eaf1"},panelHeader:{display:"flex",justifyContent:"space-between",alignItems:"center",borderBottom:"2px solid #0d2147",paddingBottom:10},panelTitle:{margin:0,fontSize:19,color:"#0d2147"},count:{fontSize:13,color:"#667085"},newsRow:{display:"flex",gap:12,padding:"15px 0",borderBottom:"1px solid #edf0f4"},sourcePill:{alignSelf:"flex-start",minWidth:74,textAlign:"center",fontSize:12,fontWeight:800,color:"#315caa",background:"#edf3ff",padding:"6px 8px",borderRadius:999},socialPill:{alignSelf:"flex-start",minWidth:74,textAlign:"center",fontSize:12,fontWeight:800,color:"#7a3e00",background:"#fff3e6",padding:"6px 8px",borderRadius:999},newsTitle:{color:"#14213d",textDecoration:"none",fontWeight:750,lineHeight:1.55,overflowWrap:"anywhere"},meta:{fontSize:12,color:"#8a94a7",marginTop:5},empty:{padding:28,color:"#8a94a7",textAlign:"center"},sidePanel:{display:"flex",flexDirection:"column",gap:14},reportCard:{display:"block",background:"#0d2147",color:"white",textDecoration:"none",padding:22,borderRadius:16,boxShadow:"0 7px 20px rgba(13,33,71,.18)"},statusRow:{display:"flex",justifyContent:"space-between",padding:"11px 0",borderBottom:"1px solid #eef1f5",fontSize:14}
};
