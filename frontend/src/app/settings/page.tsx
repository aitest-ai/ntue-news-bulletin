"use client";

import { useEffect, useState } from "react";

export default function SettingsPage(){
  const [enabled,setEnabled]=useState(false);
  const [recipients,setRecipients]=useState<string[]>([]);
  const [schedules,setSchedules]=useState<string[]>(["08:00"]);
  const [reportDays,setReportDays]=useState(1);
  const [latestCount,setLatestCount]=useState(20);
  const [subjectPrefix,setSubjectPrefix]=useState("【國北教大輿情快報】");
  const [newRecipient,setNewRecipient]=useState("");
  const [newTime,setNewTime]=useState("08:00");
  const [saving,setSaving]=useState(false);
  const [message,setMessage]=useState("");

  useEffect(()=>{
    fetch(`/data/settings.json?t=${Date.now()}`,{cache:"no-store"})
      .then(r=>r.json()).then(s=>{
        setEnabled(Boolean(s.email_enabled));
        setRecipients(Array.isArray(s.recipients)?s.recipients:[]);
        setSchedules(Array.isArray(s.schedules)&&s.schedules.length?s.schedules:["08:00"]);
        setReportDays(Number(s.report_days||1));
        setLatestCount(Number(s.include_latest_items||20));
        setSubjectPrefix(s.subject_prefix||"【國北教大輿情快報】");
      }).catch(()=>setMessage("無法讀取目前設定"));
  },[]);

  function addRecipient(){const v=newRecipient.trim();if(!v||recipients.includes(v))return;setRecipients([...recipients,v]);setNewRecipient("")}
  function addTime(){if(!/^([01]\d|2[0-3]):[0-5]\d$/.test(newTime)||schedules.includes(newTime))return;setSchedules([...schedules,newTime].sort())}

  async function save(){
    setSaving(true);setMessage("");
    try{
      const r=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email_enabled:enabled,recipients,schedules,report_days:reportDays,include_latest_items:latestCount,subject_prefix:subjectPrefix})});
      const d=await r.json();if(!r.ok)throw new Error(d?.error||"儲存失敗");
      setMessage("設定已儲存");
    }catch(e:any){setMessage(e?.message||"儲存失敗")}finally{setSaving(false)}
  }

  return <main style={s.page}>
    <section style={s.card}>
      <div style={s.header}><div><h1 style={s.title}>系統設定</h1><div style={s.sub}>電子報收件者與自動發送排程</div></div><a href="/" style={s.back}>返回首頁</a></div>

      <div style={s.section}>
        <label style={s.switchRow}><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/><span><b>啟用自動電子報</b><small style={s.help}>依下方時段自動發送輿情報告與最新訊息</small></span></label>
      </div>

      <div style={s.grid}>
        <div style={s.section}><h2 style={s.h2}>收件者</h2><div style={s.row}><input value={newRecipient} onChange={e=>setNewRecipient(e.target.value)} onKeyDown={e=>e.key==="Enter"&&addRecipient()} placeholder="name@example.com" style={s.input}/><button onClick={addRecipient} style={s.smallBtn}>新增</button></div><div style={s.tags}>{recipients.map(x=><span key={x} style={s.tag}>{x}<button onClick={()=>setRecipients(recipients.filter(r=>r!==x))} style={s.x}>×</button></span>)}</div></div>
        <div style={s.section}><h2 style={s.h2}>發送時段</h2><div style={s.row}><input type="time" step="600" value={newTime} onChange={e=>setNewTime(e.target.value)} style={s.input}/><button onClick={addTime} style={s.smallBtn}>新增</button></div><div style={s.tags}>{schedules.map(x=><span key={x} style={s.tag}>{x}<button onClick={()=>setSchedules(schedules.filter(t=>t!==x))} style={s.x}>×</button></span>)}</div></div>
      </div>

      <div style={s.grid}>
        <div style={s.section}><h2 style={s.h2}>報告範圍</h2><label style={s.label}>彙整最近幾天</label><select value={reportDays} onChange={e=>setReportDays(Number(e.target.value))} style={s.input}><option value={1}>1 天</option><option value={3}>3 天</option><option value={7}>7 天</option><option value={14}>14 天</option><option value={30}>30 天</option></select></div>
        <div style={s.section}><h2 style={s.h2}>最新訊息數量</h2><label style={s.label}>每封信列出幾筆最新內容</label><input type="number" min={5} max={100} value={latestCount} onChange={e=>setLatestCount(Number(e.target.value))} style={s.input}/></div>
      </div>

      <div style={s.section}><h2 style={s.h2}>郵件主旨前綴</h2><input value={subjectPrefix} onChange={e=>setSubjectPrefix(e.target.value)} style={{...s.input,width:"100%"}}/></div>

      <div style={s.footer}><div style={{color:message.includes("失敗")||message.includes("尚未")?"#a11919":"#287a52"}}>{message}</div><button onClick={save} disabled={saving} style={s.save}>{saving?"儲存中…":"儲存設定"}</button></div>
    </section>
  </main>
}

const s:Record<string,React.CSSProperties>={
  page:{minHeight:"100vh",background:"#f3f6fa",padding:"30px 18px",fontFamily:"Arial,'Noto Sans TC',sans-serif",color:"#15213b"},card:{maxWidth:980,margin:"0 auto",background:"white",borderRadius:18,padding:24,borderTop:"5px solid #0d2147",boxShadow:"0 8px 28px rgba(20,40,80,.08)"},header:{display:"flex",justifyContent:"space-between",gap:16,alignItems:"center",marginBottom:18},title:{margin:0,color:"#0d2147",fontSize:28},sub:{color:"#667085",fontSize:13,marginTop:5},back:{textDecoration:"none",color:"#0d2147",fontWeight:800},section:{border:"1px solid #e2e8f0",borderRadius:12,padding:16,marginBottom:14},grid:{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))",gap:14},h2:{fontSize:16,margin:"0 0 12px",color:"#0d2147"},switchRow:{display:"flex",gap:12,alignItems:"flex-start",cursor:"pointer"},help:{display:"block",fontWeight:400,color:"#667085",marginTop:4},row:{display:"flex",gap:8},input:{padding:"10px 12px",border:"1px solid #cfd7e5",borderRadius:9,fontSize:14,background:"white",minWidth:0,flex:1},smallBtn:{border:0,borderRadius:9,padding:"10px 14px",background:"#e8eef7",color:"#0d2147",fontWeight:800,cursor:"pointer"},tags:{display:"flex",gap:7,flexWrap:"wrap",marginTop:12},tag:{display:"inline-flex",alignItems:"center",gap:6,padding:"7px 9px",background:"#eef3f9",borderRadius:999,fontSize:13},x:{border:0,background:"transparent",cursor:"pointer",fontSize:17,color:"#667085",lineHeight:1},label:{display:"block",fontSize:12,color:"#667085",marginBottom:7},footer:{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,marginTop:6},save:{border:0,borderRadius:10,padding:"12px 20px",background:"#0d2147",color:"white",fontWeight:900,cursor:"pointer"}
};
