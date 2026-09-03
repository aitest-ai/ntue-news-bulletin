"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { NTUE_LOGO_DATA_URI } from "../branding";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function login() {
    setLoading(true); setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || "登入失敗");
      const next = typeof window !== "undefined" ? (new URLSearchParams(window.location.search).get("next") || "/") : "/";
      router.replace(next);
      router.refresh();
    } catch (e: any) {
      setError(e?.message || "登入失敗");
    } finally { setLoading(false); }
  }

  return <main style={{minHeight:"100vh",display:"grid",placeItems:"center",background:"linear-gradient(180deg,#eef3fa,#f8fafc)",padding:24,fontFamily:"Arial,'Noto Sans TC',sans-serif"}}>
    <section style={{width:"min(440px,100%)",background:"white",borderRadius:20,padding:"34px 34px 30px",boxShadow:"0 16px 45px rgba(13,33,71,.12)",borderTop:"5px solid #0d2147",textAlign:"center"}}>
      <img src={NTUE_LOGO_DATA_URI} alt="國立臺北教育大學校徽" style={{width:104,height:96,objectFit:"contain",marginBottom:10}} />
      <h1 style={{margin:"0 0 4px",fontSize:27,color:"#0d2147"}}>國立臺北教育大學</h1>
      <div style={{fontFamily:"Georgia,serif",fontSize:14,color:"#556277",marginBottom:6}}>National Taipei University of Education</div>
      <div style={{fontWeight:800,fontSize:18,color:"#26344f",marginBottom:24}}>輿情監測與決策支援系統</div>
      <input autoFocus type="password" value={password} onChange={e=>setPassword(e.target.value)} onKeyDown={e=>{if(e.key==="Enter")login()}} placeholder="請輸入管理員密碼" style={{width:"100%",padding:"13px 14px",border:"1px solid #cbd5e1",borderRadius:10,fontSize:15,outline:"none",marginBottom:10}} />
      {error && <div style={{background:"#fff1f1",color:"#a11919",padding:"10px 12px",borderRadius:9,fontSize:13,marginBottom:10,textAlign:"left"}}>{error}</div>}
      <button onClick={login} disabled={loading || !password} style={{width:"100%",border:0,borderRadius:10,padding:"13px 16px",background:"#0d2147",color:"white",fontWeight:800,fontSize:15,cursor:"pointer",opacity:loading||!password?.65:1}}>{loading?"登入中…":"登入系統"}</button>
      <div style={{marginTop:18,fontSize:12,color:"#8a94a7"}}>僅供授權人員使用</div>
    </section>
  </main>;
}
