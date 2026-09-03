"use client";

import { useEffect, useMemo, useState } from "react";
import { NTUE_LOGO_DATA_URI } from "./branding";

type NewsItem={title:string;url:string;source:string;publisher?:string;publish_time?:string|null;keyword?:string;task:string};
type Feed={updated_at:string|null;keywords:string[];items:NewsItem[]};
const SOCIAL=new Set(["Dcard","PTT","Threads","Instagram"]);

export default function Home(){
  const [feed,setFeed]=useState<Feed|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [query,setQuery]=useState("");

  async function refresh(){setLoading(true);setError("");try{const r=await fetch(`/data/news.json?t=${Date.now()}`,{cache:"no-store"});if(!r.ok)throw new Error(`HTTP ${r.status}`);setFeed(await r.json())}catch(e:any){setError(`資料載入失敗：${e?.message||"未知錯誤"}`)}finally{setLoading(false)}}
  useEffect(()=>{refresh()},[]);

  const filtered=useMemo(()=>{const q=query.trim().toLowerCase();return (feed?.items||[]).filter(x=>!q||`${x.title} ${x.source} ${x.publisher||""}`.toLowerCase().includes(q))},[feed,query]);
  const news=filtered.filter(x=>!SOCIAL.has(x.source));
  const social=filtered.filter(x=>SOCIAL.has(x.source));
  const today=new Date().toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"});
  const todayCount=(feed?.items||[]).filter(x=>x.publish_time&&new Date(x.publish_time).toLocaleDateString("zh-TW",{timeZone:"Asia/Taipei"})===today).length;

  return <main style={s.page}>
    <section style={s.hero}>
      <div style={s.brand}><img src={NTUE_LOGO_DATA_URI} alt="國立臺北教育大學校徽" style={s.logo}/><div><div style={s.school}>國立臺北教育大學</div><div style={s.en}>National Taipei University of Education</div><h1 style={s.title}>媒體與公開輿情監測</h1></div></div>
      <div style={s.actions}><a href="/reports" style={s.primary}>AI 輿情報告</a><a href="/settings" style={s.secondary}>設定</a><button onClick={refresh} style={s.secondaryBtn}>{loading?"更新中…":"重新整理"}</button><div style={s.updated}>最後更新：{fmtUpdated(feed?.updated_at)}</div></div>
    </section>

    {error&&<div style={s.error}>{error}</div>}

    <section style={s.summary}>
      <div style={s.stat}><span>目前資料</span><b>{feed?.items?.length||0}</b></div>
      <div style={s.stat}><span>今日新增</span><b>{todayCount}</b></div>
      <div style={s.stat}><span>新聞報導</span><b>{(feed?.items||[]).filter(x=>!SOCIAL.has(x.source)).length}</b></div>
      <div style={s.stat}><span>社群討論</span><b>{(feed?.items||[]).filter(x=>SOCIAL.has(x.source)).length}</b></div>
      <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜尋標題或來源" style={s.search}/>
    </section>

    <section style={s.columns}>
      <FeedColumn title="新聞報導" count={news.length} items={news}/>
      <FeedColumn title="社群討論" count={social.length} items={social} social/>
    </section>
  </main>
}

function FeedColumn({title,count,items,social=false}:{title:string;count:number;items:NewsItem[];social?:boolean}){
  return <section style={s.panel}><div style={s.panelHead}><h2 style={s.panelTitle}>{title}</h2><span style={s.count}>{count} 筆</span></div>{items.length===0?<div style={s.empty}>目前沒有符合條件的內容</div>:items.map((x,i)=><article key={`${x.url}-${i}`} style={s.row}><div style={social?s.socialPill:s.newsPill}>{x.source}</div><div style={{minWidth:0,flex:1}}><a href={x.url} target="_blank" rel="noreferrer" style={s.itemTitle}>{x.title}</a><div style={s.meta}>{x.publisher&&x.publisher!==x.source?`${x.publisher} · `:""}{fmtDate(x.publish_time)}</div></div></article>)}</section>
}

function fmtDate(v?:string|null){if(!v)return"日期未提供";const d=new Date(v);return Number.isNaN(d.getTime())?"日期未提供":d.toLocaleString("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}
function fmtUpdated(v?:string|null){if(!v)return"尚未更新";const d=new Date(v);return Number.isNaN(d.getTime())?"未知":d.toLocaleString("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}

const s:Record<string,React.CSSProperties>={
  page:{minHeight:"100vh",background:"#f3f6fa",color:"#14213d",padding:"28px",fontFamily:"Arial,'Noto Sans TC',sans-serif"},hero:{maxWidth:1480,margin:"0 auto 16px",background:"white",borderRadius:18,padding:"20px 24px",display:"flex",justifyContent:"space-between",alignItems:"center",gap:20,flexWrap:"wrap",borderTop:"5px solid #0d2147",boxShadow:"0 5px 20px rgba(20,45,80,.05)"},brand:{display:"flex",alignItems:"center",gap:15},logo:{width:72,height:68,objectFit:"contain"},school:{fontSize:19,fontWeight:900,color:"#0d2147"},en:{fontSize:12,fontFamily:"Georgia,serif",color:"#667085",marginTop:2},title:{fontSize:29,margin:"7px 0 0",color:"#102a56"},actions:{display:"flex",alignItems:"center",gap:9,flexWrap:"wrap",justifyContent:"flex-end"},primary:{background:"#0d2147",color:"white",textDecoration:"none",padding:"12px 17px",borderRadius:10,fontWeight:900},secondary:{background:"#e8eef7",color:"#0d2147",textDecoration:"none",padding:"12px 15px",borderRadius:10,fontWeight:800},secondaryBtn:{border:"1px solid #cbd5e1",background:"white",padding:"11px 14px",borderRadius:10,fontWeight:800,cursor:"pointer"},updated:{width:"100%",textAlign:"right",fontSize:12,color:"#6b7280"},error:{maxWidth:1480,margin:"0 auto 14px",background:"#fff0f0",color:"#a11919",padding:12,borderRadius:10},summary:{maxWidth:1480,margin:"0 auto 16px",display:"grid",gridTemplateColumns:"repeat(4,minmax(130px,1fr)) minmax(230px,2fr)",gap:10},stat:{background:"white",border:"1px solid #e5eaf1",borderRadius:13,padding:"14px 16px",display:"flex",justifyContent:"space-between",alignItems:"center",gap:10},stat:{background:"white",border:"1px solid #e5eaf1",borderRadius:13,padding:"14px 16px"},search:{width:"100%",padding:"12px 14px",border:"1px solid #d5dde8",borderRadius:11,fontSize:14,background:"white"},columns:{maxWidth:1480,margin:"0 auto",display:"grid",gridTemplateColumns:"repeat(2,minmax(0,1fr))",gap:16,alignItems:"start"},panel:{background:"white",borderRadius:16,padding:19,border:"1px solid #e5eaf1",minWidth:0},panelHead:{display:"flex",justifyContent:"space-between",alignItems:"center",borderBottom:"2px solid #0d2147",paddingBottom:10},panelTitle:{margin:0,fontSize:20,color:"#0d2147"},count:{fontSize:13,color:"#667085"},row:{display:"flex",gap:11,padding:"14px 0",borderBottom:"1px solid #edf0f4"},newsPill:{alignSelf:"flex-start",minWidth:72,textAlign:"center",fontSize:11.5,fontWeight:800,color:"#315caa",background:"#edf3ff",padding:"6px 8px",borderRadius:999},socialPill:{alignSelf:"flex-start",minWidth:72,textAlign:"center",fontSize:11.5,fontWeight:800,color:"#7a3e00",background:"#fff3e6",padding:"6px 8px",borderRadius:999},itemTitle:{color:"#14213d",textDecoration:"none",fontWeight:750,lineHeight:1.55,overflowWrap:"anywhere"},meta:{fontSize:11.5,color:"#8a94a7",marginTop:5},empty:{padding:30,color:"#8a94a7",textAlign:"center"}
};
