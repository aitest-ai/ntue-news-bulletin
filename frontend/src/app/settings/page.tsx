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

  return <main className="settings-page">
    <section className="settings-card">
      <div className="settings-header">
        <div className="header-copy"><h1>推送設定</h1><div className="header-sub">每個時段都能設定自己的搜尋天數、收件人與寄件資訊</div></div>
        <a href="/" className="back-link">返回首頁</a>
      </div>

      <div className="settings-note">網站仍只供你管理；收件者不需要登入系統，會直接收到 PDF 輿情報告。若某次 GitHub 排程延遲，系統會在當天下一次醒來時自動補寄，且每個推送任務各自記錄，不會互相干擾。</div>

      {profiles.map((p,index)=><ProfileCard key={p.id} profile={p} index={index} patch={patch} addRecipient={addRecipient} removeRecipient={removeRecipient} remove={()=>setProfiles(ps=>ps.filter(x=>x.id!==p.id))}/>)}

      <button onClick={()=>setProfiles(ps=>[...ps,blankProfile()])} className="add-task">＋ 新增推送任務</button>
      <div className="settings-footer"><div className={message.includes("失敗")?"save-message error":"save-message"}>{message}</div><button onClick={save} disabled={saving} className="save-button">{saving?"儲存中…":"儲存全部設定"}</button></div>
    </section>

    <style jsx global>{`
      *{box-sizing:border-box}
      html,body{max-width:100%;overflow-x:hidden}
      .settings-page{min-height:100vh;background:#f3f6fa;padding:30px 18px;font-family:Arial,'Noto Sans TC',sans-serif;color:#15213b}
      .settings-card{width:min(1040px,100%);margin:0 auto;background:#fff;border-radius:18px;padding:24px;border-top:5px solid #0d2147;box-shadow:0 8px 28px rgba(20,40,80,.08);overflow:hidden}
      .settings-header{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:18px;min-width:0}
      .header-copy{min-width:0;flex:1}
      .header-copy h1{margin:0;color:#0d2147;font-size:28px;line-height:1.2}
      .header-sub{color:#667085;font-size:13px;line-height:1.55;margin-top:6px}
      .back-link{flex:0 0 auto;text-decoration:none;color:#0d2147;font-weight:800;padding:8px 0;white-space:nowrap}
      .settings-note{background:#f5f8fc;border:1px solid #d9e4f0;border-radius:12px;padding:14px 16px;color:#42526b;font-size:13px;line-height:1.75;margin-bottom:18px;overflow-wrap:anywhere}

      .profile-card{border:1px solid #dbe3ee;border-radius:16px;padding:18px;margin-bottom:16px;box-shadow:0 3px 12px rgba(20,40,80,.04);min-width:0;overflow:hidden}
      .profile-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:16px;min-width:0}
      .profile-title-block{min-width:0;flex:1}
      .profile-kicker{font-size:11px;font-weight:900;color:#6b7a90;letter-spacing:1px;margin-bottom:5px}
      .profile-name{display:block;width:min(520px,100%);min-width:0;border:0;border-bottom:1px solid #d6deea;font-size:20px;font-weight:900;color:#0d2147;padding:4px 2px 7px;background:#fff;outline:none}
      .profile-name:focus{border-bottom-color:#0d2147}
      .profile-actions{display:flex;gap:8px;align-items:center;flex:0 0 auto}
      .profile-toggle{display:inline-flex;gap:7px;align-items:center;font-weight:800;font-size:13px;min-height:40px;padding:6px 8px;white-space:nowrap}
      .profile-toggle input{width:18px;height:18px;margin:0;accent-color:#0d6efd}
      .delete-button{border:1px solid #f0c9c9;background:#fff7f7;color:#a12a2a;border-radius:9px;padding:9px 12px;min-height:40px;font-weight:700;cursor:pointer;white-space:nowrap}

      .grid-three{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
      .grid-two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
      .form-field,.recipient-section{min-width:0;margin-bottom:12px}
      .field-label{font-size:12px;color:#667085;font-weight:700;margin-bottom:7px;line-height:1.45}
      .form-input{display:block;width:100%;min-width:0;padding:11px 12px;border:1px solid #cfd7e5;border-radius:9px;font-size:16px;background:#fff;color:#15213b;min-height:44px}
      .form-input:focus{outline:2px solid rgba(13,33,71,.12);border-color:#8fa2bd}
      .recipient-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:stretch}
      .recipient-add{border:0;border-radius:9px;padding:10px 16px;background:#e8eef7;color:#0d2147;font-weight:800;cursor:pointer;min-height:44px;white-space:nowrap}
      .recipient-tags{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px;min-width:0}
      .recipient-tag{display:inline-flex;align-items:center;gap:6px;max-width:100%;padding:7px 9px;background:#eef3f9;border-radius:999px;font-size:13px;overflow-wrap:anywhere;word-break:break-word}
      .recipient-tag .recipient-text{min-width:0;overflow-wrap:anywhere;word-break:break-word}
      .recipient-remove{flex:0 0 auto;border:0;background:transparent;cursor:pointer;font-size:17px;color:#667085;line-height:1;padding:0 2px}

      .add-task{width:100%;border:1px dashed #9fb0c8;border-radius:12px;padding:13px;background:#fbfcfe;color:#0d2147;font-weight:900;cursor:pointer;margin-bottom:16px;min-height:46px}
      .settings-footer{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:6px}
      .save-message{color:#287a52;font-size:13px;min-height:20px}
      .save-message.error{color:#a11919}
      .save-button{border:0;border-radius:10px;padding:12px 20px;background:#0d2147;color:#fff;font-weight:900;cursor:pointer;min-height:46px;white-space:nowrap}
      .save-button:disabled{opacity:.65;cursor:default}

      @media (max-width:820px){
        .grid-three{grid-template-columns:1fr 1fr}
        .grid-three>.form-field:last-child{grid-column:1/-1}
      }

      @media (max-width:640px){
        .settings-page{padding:18px 12px 28px}
        .settings-card{border-radius:15px;padding:18px 14px;border-top-width:5px}
        .settings-header{flex-direction:column;gap:10px;margin-bottom:14px}
        .header-copy h1{font-size:26px}
        .header-sub{font-size:13px}
        .back-link{align-self:flex-start;padding:7px 11px;border:1px solid #d4deea;border-radius:9px;background:#fff;line-height:1.2}
        .settings-note{padding:13px 14px;font-size:13px;margin-bottom:14px}

        .profile-card{padding:15px 13px;border-radius:14px;margin-bottom:14px}
        .profile-head{flex-direction:column;gap:12px}
        .profile-title-block{width:100%}
        .profile-name{width:100%;font-size:20px}
        .profile-actions{width:100%;display:grid;grid-template-columns:1fr auto;gap:8px;border-top:1px solid #edf1f6;padding-top:10px}
        .profile-toggle{justify-content:flex-start;padding-left:2px}
        .delete-button{min-width:72px}

        .grid-three,.grid-two{grid-template-columns:1fr}
        .grid-three>.form-field:last-child{grid-column:auto}
        .recipient-row{grid-template-columns:1fr}
        .recipient-add{width:100%}
        .recipient-tags{gap:6px}
        .recipient-tag{width:100%;justify-content:space-between;border-radius:10px;padding:9px 10px}

        .settings-footer{flex-direction:column;align-items:stretch;gap:8px}
        .save-message{text-align:center}
        .save-button{width:100%}
      }

      @media (max-width:390px){
        .settings-page{padding-left:8px;padding-right:8px}
        .settings-card{padding-left:11px;padding-right:11px}
        .profile-card{padding-left:11px;padding-right:11px}
        .header-copy h1{font-size:24px}
        .profile-name{font-size:19px}
      }
    `}</style>
  </main>
}

function ProfileCard({profile:p,index,patch,addRecipient,removeRecipient,remove}:{profile:Profile;index:number;patch:(id:string,c:Partial<Profile>)=>void;addRecipient:(id:string,v:string)=>void;removeRecipient:(id:string,v:string)=>void;remove:()=>void}){
  const [newRecipient,setNewRecipient]=useState("");
  return <div className="profile-card">
    <div className="profile-head">
      <div className="profile-title-block"><div className="profile-kicker">推送任務 {index+1}</div><input value={p.name} onChange={e=>patch(p.id,{name:e.target.value})} className="profile-name" aria-label={`推送任務 ${index+1} 名稱`}/></div>
      <div className="profile-actions"><label className="profile-toggle"><input type="checkbox" checked={p.enabled} onChange={e=>patch(p.id,{enabled:e.target.checked})}/>啟用</label><button onClick={remove} className="delete-button">刪除</button></div>
    </div>

    <div className="grid-three">
      <Field label="發送時間"><input type="time" value={p.time} onChange={e=>patch(p.id,{time:e.target.value})} className="form-input"/></Field>
      <Field label="搜尋最近幾天"><select value={p.report_days} onChange={e=>patch(p.id,{report_days:Number(e.target.value)})} className="form-input"><option value={1}>1 天</option><option value={2}>2 天</option><option value={3}>3 天</option><option value={7}>7 天</option><option value={14}>14 天</option><option value={30}>30 天</option></select></Field>
      <Field label="最新訊息上限"><input type="number" min={5} max={100} value={p.include_latest_items} onChange={e=>patch(p.id,{include_latest_items:Number(e.target.value)})} className="form-input"/></Field>
    </div>

    <div className="recipient-section"><div className="field-label">收件人</div><div className="recipient-row"><input value={newRecipient} onChange={e=>setNewRecipient(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();addRecipient(p.id,newRecipient);setNewRecipient("")}}} placeholder="name@example.com" inputMode="email" autoCapitalize="none" className="form-input"/><button onClick={()=>{addRecipient(p.id,newRecipient);setNewRecipient("")}} className="recipient-add">新增收件人</button></div><div className="recipient-tags">{p.recipients.map(x=><span key={x} className="recipient-tag"><span className="recipient-text">{x}</span><button onClick={()=>removeRecipient(p.id,x)} className="recipient-remove" aria-label={`移除 ${x}`}>×</button></span>)}</div></div>

    <div className="grid-two">
      <Field label="郵件主旨前綴"><input value={p.subject_prefix} onChange={e=>patch(p.id,{subject_prefix:e.target.value})} className="form-input"/></Field>
      <Field label="寄件者顯示名稱（可留空）"><input value={p.sender_name||""} onChange={e=>patch(p.id,{sender_name:e.target.value})} placeholder="例：國北教大輿情監測" className="form-input"/></Field>
    </div>
    <Field label="寄件 Email（可留空；留空使用系統預設 Brevo 已驗證寄件者）"><input type="email" value={p.sender_email||""} onChange={e=>patch(p.id,{sender_email:e.target.value})} placeholder="verified-sender@example.com" inputMode="email" autoCapitalize="none" className="form-input"/></Field>
  </div>
}

function Field({label,children}:{label:string;children:React.ReactNode}){return <div className="form-field"><div className="field-label">{label}</div>{children}</div>}
