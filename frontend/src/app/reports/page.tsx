"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { NTUE_LOGO_DATA_URI } from "../branding";

type FeedItem={title:string;url:string;source:string;publisher?:string;publish_time?:string|null;keyword?:string;task?:string};
type Feed={updated_at:string|null;items:FeedItem[]};
type Topic={topic:string;trend:string;sentiment:string;volume:number;explanation:string;sources:string[]};
type Risk={category:string;level:string;reason:string};
type Action={unit:string;action:string;priority:string};
type Notable={title:string;source:string;reason:string};
type Report={executive_title:string;signal:string;overall_risk:string;immediate_action:boolean;immediate_action_reason:string;confidence_note:string;top_points:string[];summary:string;topics:Topic[];sentiment_counts:{positive:number;neutral:number;negative:number;uncertain:number};risk_matrix:Risk[];recommended_actions:Action[];notable_items:Notable[];conclusion:string};

const SOCIAL=new Set(["Dcard","PTT","Threads","Instagram"]);

export default function ReportsPage(){
  const router=useRouter();
  const [feed,setFeed]=useState<Feed|null>(null);
  const [days,setDays]=useState(7);
  const [report,setReport]=useState<Report|null>(null);
  const [meta,setMeta]=useState<any>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");

  useEffect(()=>{fetch(`/data/news.json?t=${Date.now()}`,{cache:"no-store"}).then(r=>r.json()).then(setFeed).catch(()=>setError("無法讀取目前輿情資料"))},[]);
  const selectedItems=useMemo(()=>{const cutoff=Date.now()-days*86400000;return(feed?.items||[]).filter(x=>{if(!x.publish_time)return true;const t=new Date(x.publish_time).getTime();return Number.isNaN(t)||t>=cutoff})},[feed,days]);
  const sourceStats=useMemo(()=>{const m=new Map<string,number>();selectedItems.forEach(x=>m.set(x.source,(m.get(x.source)||0)+1));return Array.from(m.entries()).sort((a,b)=>b[1]-a[1])},[selectedItems]);

  async function generate(){
    setLoading(true);setError("");
    try{
      const r=await fetch("/api/ai-report",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({periodDays:days,items:selectedItems})});
      const d=await r.json();
      if(r.status===401){router.replace("/login?next=/reports");return}
      if(!r.ok)throw new Error(d?.error||"產生失敗");
      setReport(d.report);setMeta(d.meta);
    }catch(e:any){setError(e?.message||"產生報告失敗")}finally{setLoading(false)}
  }

  return <main className="report-shell">
    <style jsx global>{`
      *{box-sizing:border-box}body{margin:0;background:#eef2f7;color:#111827;font-family:Arial,"Noto Sans TC",sans-serif}.report-shell{padding:22px 16px 36px}.toolbar{max-width:1050px;margin:0 auto 16px;background:#fff;padding:15px;border-radius:14px;display:flex;gap:9px;align-items:center;flex-wrap:wrap;border:1px solid #dde4ee}.toolbar select{padding:10px 12px;border:1px solid #cfd7e5;border-radius:9px;min-width:150px}.btn{border:0;border-radius:9px;padding:10px 15px;font-weight:800;cursor:pointer;text-decoration:none}.primary{background:#0d2147;color:#fff}.secondary{background:#e8eef7;color:#102a56}.empty-card{width:min(700px,calc(100vw - 32px));margin:34px auto;background:#fff;border-radius:18px;padding:32px;text-align:center;border-top:5px solid #0d2147;box-shadow:0 8px 28px rgba(20,40,80,.08)}.empty-logo{width:92px;height:86px;object-fit:contain}.paper{width:210mm;max-width:calc(100vw - 32px);margin:0 auto;background:#fff;padding:11mm;box-shadow:0 8px 30px rgba(30,50,80,.12);overflow:hidden}.mast{display:flex;align-items:center;justify-content:center;gap:16px;border-bottom:2.5px solid #102a56;padding-bottom:10px}.mast-logo{width:70px;height:66px;object-fit:contain}.school{font-size:20px;font-weight:900;color:#0d2147}.mast h1{margin:3px 0;font-size:25px;color:#0d2147}.en{font-family:Georgia,serif;font-size:13px}.meta-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:2px solid #102a56;font-weight:700;font-size:12px}.meta-row span{padding:9px 6px;text-align:center;overflow-wrap:anywhere}.grid2{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,.85fr);gap:10px;margin-top:10px}.section{border:1px solid #9cabbd;min-width:0;overflow:hidden}.section h2{margin:0;background:#102a56;color:#fff;font-size:14px;padding:7px 10px}.section-body{padding:10px 11px;line-height:1.55;font-size:12.5px;overflow-wrap:anywhere}.section-body ol,.section-body ul{margin:0;padding-left:20px}.section-body li{margin-bottom:5px}.signal{font-size:18px;font-weight:900;text-align:center;padding:16px 10px}.signal small{display:block;font-size:12px;color:#667085;margin-top:8px;font-weight:500;line-height:1.5}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.stat{border:1px solid #d5dde8;padding:7px 4px;text-align:center;font-size:11px}.stat b{display:block;font-size:20px}.topic{border-bottom:1px solid #e5e7eb;padding:7px 0}.tag{display:inline-block;padding:1px 6px;border-radius:999px;background:#edf2f8;font-size:10.5px;margin-right:4px}.risk-table{width:100%;border-collapse:collapse;table-layout:fixed}.risk-table th,.risk-table td{border:1px solid #b9c3d1;padding:6px;font-size:11.5px;vertical-align:top;overflow-wrap:anywhere}.risk-table th{background:#edf2f8}.actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.action{border:1px solid #ccd5e1;padding:8px;overflow-wrap:anywhere}.muted{color:#667085;font-size:10.5px;line-height:1.45}.error{max-width:1050px;margin:0 auto 12px;background:#fff1f1;color:#a11919;padding:12px;border-radius:10px}.footer-note{text-align:center;margin-top:13px;font-size:10.5px;color:#5e6b80}@media(max-width:800px){.grid2,.actions{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.paper{width:100%;padding:18px}.meta-row{grid-template-columns:repeat(2,minmax(0,1fr))}}@media print{@page{size:A4;margin:7mm}body{background:#fff}.no-print{display:none!important}.report-shell{padding:0}.paper{width:196mm;max-width:196mm;box-shadow:none;padding:4mm;margin:0}.section,.grid2{break-inside:avoid}.section-body{font-size:10.8px;padding:7px 8px}.risk-table th,.risk-table td{font-size:9.8px;padding:4px}}
    `}</style>

    <div className="toolbar no-print">
      <a href="/" className="btn secondary">← 返回監測首頁</a>
      <select value={days} onChange={e=>setDays(Number(e.target.value))}><option value={1}>最近 24 小時</option><option value={3}>最近 3 天</option><option value={7}>最近 7 天</option><option value={14}>最近 14 天</option><option value={30}>最近 30 天</option></select>
      <button className="btn primary" onClick={generate} disabled={loading}>{loading?"AI 分析中…":"產生輿情報告"}</button>
      {report&&<button className="btn secondary" onClick={()=>window.print()}>列印／另存 PDF</button>}
      <span className="muted">可分析 {selectedItems.length} 筆</span>
    </div>
    {error&&<div className="error no-print">{error}</div>}

    {!report?<section className="empty-card no-print"><img src={NTUE_LOGO_DATA_URI} className="empty-logo" alt="國立臺北教育大學校徽"/><h1 style={{color:"#0d2147",marginBottom:6}}>AI 輿情報告</h1><div className="en">Media & Public Opinion Monitoring Report</div><p style={{color:"#667085"}}>選擇監測期間後即可直接產生報告，不需再次輸入密碼。</p></section>:
    <article className="paper">
      <header className="mast"><img src={NTUE_LOGO_DATA_URI} className="mast-logo" alt="國立臺北教育大學校徽"/><div><div className="school">國立臺北教育大學</div><div className="en">National Taipei University of Education</div><h1>媒體與公開輿情趨勢報告</h1><div className="en">Media & Public Opinion Monitoring Report</div></div></header>
      <div className="meta-row"><span>監測期間：最近 {days} 天</span><span>資料筆數：{meta?.analyzed_items??selectedItems.length}</span><span>分析模型：Gemini 2.5 Flash</span><span>燈號：{signalIcon(report.signal)} {report.signal}</span></div>
      <div className="grid2"><Section title="一、近期重點"><ol>{report.top_points.map((x,i)=><li key={i}>{x}</li>)}</ol></Section><Section title="二、是否需立即處理"><div className="signal">{report.immediate_action?"⚠️ 建議立即處理":"✅ 目前不需立即處理"}<small>{report.immediate_action_reason}</small></div></Section></div>
      <div className="grid2"><Section title="三、監測量與來源"><div className="stats"><div className="stat">總資料<b>{selectedItems.length}</b></div><div className="stat">新聞媒體<b>{selectedItems.filter(i=>!SOCIAL.has(i.source)).length}</b></div><div className="stat">社群／論壇<b>{selectedItems.filter(i=>SOCIAL.has(i.source)).length}</b></div><div className="stat">來源數<b>{sourceStats.length}</b></div></div><p className="muted">主要來源：{sourceStats.slice(0,8).map(([x,n])=>`${x} ${n}`).join("、")}</p></Section><Section title="四、輿情摘要">{report.summary}<p className="muted">可信度提示：{report.confidence_note}</p></Section></div>
      <Section title="五、近期討論話題與趨勢" top>{report.topics.map((t,i)=><div className="topic" key={i}><b>{t.topic}</b> <span className="tag">{t.trend}</span><span className="tag">{t.sentiment}</span><span className="tag">約 {t.volume} 筆</span><div>{t.explanation}</div><div className="muted">來源：{t.sources.join("、")}</div></div>)}</Section>
      <div className="grid2"><Section title="六、情緒訊號"><div className="stats"><div className="stat">負面<b>{report.sentiment_counts.negative}</b></div><div className="stat">中性<b>{report.sentiment_counts.neutral}</b></div><div className="stat">正面<b>{report.sentiment_counts.positive}</b></div><div className="stat">不確定<b>{report.sentiment_counts.uncertain}</b></div></div></Section><Section title="七、整體風險研判"><div className="signal">{signalIcon(report.signal)} {report.signal}<small>綜合風險：{report.overall_risk}</small></div></Section></div>
      <Section title="八、風險評估" top><table className="risk-table"><thead><tr><th>評估項目</th><th>等級</th><th>說明</th></tr></thead><tbody>{report.risk_matrix.map((r,i)=><tr key={i}><td>{r.category}</td><td>{r.level}</td><td>{r.reason}</td></tr>)}</tbody></table></Section>
      <Section title="九、建議處置分工" top><div className="actions">{report.recommended_actions.map((a,i)=><div className="action" key={i}><b>{a.unit}</b> <span className="tag">{a.priority}</span><p>{a.action}</p></div>)}</div></Section>
      {report.notable_items?.length>0&&<Section title="十、值得持續觀察的內容" top><ul>{report.notable_items.map((n,i)=><li key={i}><b>{n.title}</b>（{n.source}）－{n.reason}</li>)}</ul></Section>}
      <Section title="十一、結論" top>{report.conclusion}</Section>
      <div className="footer-note">本報告由系統彙整公開資料並以 AI 輔助研判，供校務管理參考。</div>
    </article>}
  </main>
}

function Section({title,children,top=false}:{title:string;children:React.ReactNode;top?:boolean}){return <section className="section" style={top?{marginTop:10}:undefined}><h2>{title}</h2><div className="section-body">{children}</div></section>}
function signalIcon(s:string){return s==="紅燈"?"🔴":s==="橙燈"?"🟠":s==="黃燈"?"🟡":"🟢"}
