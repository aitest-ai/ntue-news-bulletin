"use client";

import { useEffect, useState } from "react";

type Profile={id:string;name:string;enabled:boolean;time:string;report_days:number;include_latest_items:number;recipients:string[];subject_prefix:string;sender_name:string;sender_email:string;channel:"email"};

const blankProfile=():Profile=>({id:`profile-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,name:"新的推送任務",enabled:true,time:"08:00",report_days:1,include_latest_items:20,recipients:[],subject_prefix:"【國北教大輿情快報】",sender_name:"",sender_email:"",channel:"email"});

export default function SettingsPage(){
  const [profiles,setProfiles]=useState<Profile[]>([]);
  const [saving,setSaving]=useState(false);
  const [message,setMessage]=useState("");

  useEffect(()=>{
    fetch(`/data/settings.json?t=${Date.now()}`,{cache:"no-store"}).then(r=>r.json()).then(s=>{
      if(Array.isArray(s.delivery_profiles)&&s.delivery_profiles.length){setProfiles(s.delivery_profiles);return;}
      const recipients=Array.isArray(s.recipients)?s.recipients:[];
      const schedules=Array.isArray(s.schedules)&&s.schedules.length?s.schedules:["08:00"];
      setProfiles(schedules.map((time:string,i:number)=>({id:`legacy-${time.replace(":","")}-${i}`,name:`${time} 電子報`,enabled:Boolean(s.email_enabled),time,report_days:Number(s.report_days||1),include_latest_items:Number(s.include_latest_items||20),recipients:[...recipients],subject_prefix:s.subject_prefix||"【國北教大輿情快報】",sender_name:"",sender_email:"",channel:"email" as const})));
    }).catch(()=>setMessage("無法讀取目前設定"));
  },[]);

  function patch(id:string,changes:Partial<Profile>){setProfiles(ps=>ps.map(p=>p.id===id?{...p,...changes}:p))}
  function addRecipient(id:string,value:string){const v=value.trim();if(!v)return;setProfiles(ps=>ps.map(p=>p.id===id?{...p,recipients:p.recipients.includes(v)?p.recipients:[...p.recipients,v]}:p))}
  function removeRecipient(id:string,value:string){setProfiles(ps=>ps.map(p=>p.id===id?{...p,recipients:p.recipients.filter(x=>x!==value)}:p))}

  async function save(){
    setSaving(true);setMessage("");
    try{
      const r=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({delivery_profiles:profiles})});
      const d=await r.json();if(!r.ok)throw new Error(d?.error||"儲存失敗");setMessage("設定已儲存");
    }catch(e:any){setMessage(e?.message||"儲存失敗")}finally{setSaving(false)}
  }

  return <main style={s.page}><section style={s.card}>
    <div style={s.header}><div><h1 style={s.title}>推送設定</h1><div style={s.sub}>每個時段都能設定自己的搜尋天數、收件人與寄件資訊</div></div><a href="/" style={s.back}>返回首頁</a></div>

    <div style={s.note}>網站仍只供你管理；收件者不需要登入系統，會直接收到 PDF 輿情報告。若某次 GitHub 排程延遲，系統會在當天下一次醒來時自動補寄，且每個推送任務各自記錄，不會互相干擾。</div>

    {profiles.map((p,index)=><ProfileCard key={p.id} profile={p} index={index} patch={patch} addRecipient={addRecipient} removeRecipient={removeRecipient} remove={()=>setProfiles(ps=>ps.filter(x=>x.id!==p.id))}/>)}

    <button onClick={()=>setProfiles(ps=>[...ps,blankProfile()])} style={s.add}>＋ 新增推送任務</button>
    <div style={s.footer}><div style={{color:message.includes("失敗")?"#a11919":"#287a52"}}>{message}</div><button onClick={save} disabled={saving} style={s.save}>{saving?"儲存中…":"儲存全部設定"}</button></div>
  </section></main>
}

function ProfileCard({profile:p,index,patch,addRecipient,removeRecipient,remove}:{profile:Profile;index:number;patch:(id:string,c:Partial<Profile>)=>void;addRecipient:(id:string,v:string)=>void;removeRecipient:(id:string,v:string)=>void;remove:()=>void}){
  const [newRecipient,setNewRecipient]=useState("");
  return <div style={s.profile}>
    <div style={s.profileHead}><div><div style={s.kicker}>推送任務 {index+1}</div><input value={p.name} onChange={e=>patch(p.id,{name:e.target.value})} style={s.nameInput}/></div><div style={s.actions}><label style={s.toggle}><input type="checkbox" checked={p.enabled} onChange={e=>patch(p.id,{enabled:e.target.checked})}/>啟用</label><button onClick={remove} style={s.delete}>刪除</button></div></div>

    <div style={s.grid3}>
      <Field label="發送時間"><input type="time" value={p.time} onChange={e=>patch(p.id,{time:e.target.value})} style={s.input}/></Field>
      <Field label="搜尋最近幾天"><select value={p.report_days} onChange={e=>patch(p.id,{report_days:Number(e.target.value)})} style={s.input}><option value={1}>1 天</option><option value={2}>2 天</option><option value={3}>3 天</option><option value={7}>7 天</option><option value={14}>14 天</option><option value={30}>30 天</option></select></Field>
      <Field label="最新訊息上限"><input type="number" min={5} max={100} value={p.include_latest_items} onChange={e=>patch(p.id,{include_latest_items:Number(e.target.value)})} style={s.input}/></Field>
    </div>

    <div style={s.section}><div style={s.label}>收件人</div><div style={s.row}><input value={newRecipient} onChange={e=>setNewRecipient(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();addRecipient(p.id,newRecipient);setNewRecipient("")}}} placeholder="name@example.com" style={s.input}/><button onClick={()=>{addRecipient(p.id,newRecipient);setNewRecipient("")}} style={s.smallBtn}>新增</button></div><div style={s.tags}>{p.recipients.map(x=><span key={x} style={s.tag}>{x}<button onClick={()=>removeRecipient(p.id,x)} style={s.x}>×</button></span>)}</div></div>

    <div style={s.grid2}>
      <Field label="郵件主旨前綴"><input value={p.subject_prefix} onChange={e=>patch(p.id,{subject_prefix:e.target.value})} style={s.input}/></Field>
      <Field label="寄件者顯示名稱（可留空）"><input value={p.sender_name||""} onChange={e=>patch(p.id,{sender_name:e.target.value})} placeholder="例：國北教大輿情監測" style={s.input}/></Field>
    </div>
    <Field label="寄件 Email（可留空；留空使用系統預設 Brevo 已驗證寄件者）"><input type="email" value={p.sender_email||""} onChange={e=>patch(p.id,{sender_email:e.target.value})} placeholder="verified-sender@example.com" style={s.input}/></Field>
  </div>
}

function Field({label,children}:{label:string;children:React.ReactNode}){return <div style={s.field}><div style={s.label}>{label}</div>{children}</div>}

const s:Record<string,React.CSSProperties>={
  page:{minHeight:"100vh",background:"#f3f6fa",padding:"30px 18px",fontFamily:"Arial,'Noto Sans TC',sans-serif",color:"#15213b"},card:{maxWidth:1040,margin:"0 auto",background:"white",borderRadius:18,padding:24,borderTop:"5px solid #0d2147",boxShadow:"0 8px 28px rgba(20,40,80,.08)"},header:{display:"flex",justifyContent:"space-between",gap:16,alignItems:"center",marginBottom:18},title:{margin:0,color:"#0d2147",fontSize:28},sub:{color:"#667085",fontSize:13,marginTop:5},back:{textDecoration:"none",color:"#0d2147",fontWeight:800},note:{background:"#f5f8fc",border:"1px solid #d9e4f0",borderRadius:12,padding:14,color:"#42526b",fontSize:13,lineHeight:1.7,marginBottom:18},profile:{border:"1px solid #dbe3ee",borderRadius:16,padding:18,marginBottom:16,boxShadow:"0 3px 12px rgba(20,40,80,.04)"},profileHead:{display:"flex",justifyContent:"space-between",gap:12,alignItems:"flex-start",marginBottom:16},kicker:{fontSize:11,fontWeight:900,color:"#6b7a90",letterSpacing:1,marginBottom:5},nameInput:{border:0,borderBottom:"1px solid #d6deea",fontSize:20,fontWeight:900,color:"#0d2147",padding:"3px 2px",minWidth:240,maxWidth:"100%"},actions:{display:"flex",gap:10,alignItems:"center"},toggle:{display:"flex",gap:6,alignItems:"center",fontWeight:800,fontSize:13},delete:{border:"1px solid #f0c9c9",background:"#fff7f7",color:"#a12a2a",borderRadius:9,padding:"8px 10px",cursor:"pointer"},grid3:{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:12},grid2:{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(260px,1fr))",gap:12},field:{marginBottom:12},section:{marginBottom:12},label:{fontSize:12,color:"#667085",fontWeight:700,marginBottom:6},row:{display:"flex",gap:8},input:{width:"100%",padding:"10px 12px",border:"1px solid #cfd7e5",borderRadius:9,fontSize:14,background:"white",boxSizing:"border-box"},smallBtn:{border:0,borderRadius:9,padding:"10px 14px",background:"#e8eef7",color:"#0d2147",fontWeight:800,cursor:"pointer"},tags:{display:"flex",gap:7,flexWrap:"wrap",marginTop:10},tag:{display:"inline-flex",alignItems:"center",gap:6,padding:"7px 9px",background:"#eef3f9",borderRadius:999,fontSize:13},x:{border:0,background:"transparent",cursor:"pointer",fontSize:17,color:"#667085",lineHeight:1},add:{width:"100%",border:"1px dashed #9fb0c8",borderRadius:12,padding:"13px",background:"#fbfcfe",color:"#0d2147",fontWeight:900,cursor:"pointer",marginBottom:16},footer:{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,marginTop:6},save:{border:0,borderRadius:10,padding:"12px 20px",background:"#0d2147",color:"white",fontWeight:900,cursor:"pointer"}
};
