"use client";

import { usePathname, useRouter } from "next/navigation";
import { NTUE_LOGO_DATA_URI } from "./branding";

export default function SiteNav(){
  const pathname=usePathname();
  const router=useRouter();
  if(pathname==="/login") return null;

  async function logout(){await fetch("/api/auth/logout",{method:"POST"});router.replace("/login");router.refresh()}

  return <nav className="no-print" style={{background:"#0d2147",color:"white",padding:"10px 24px",display:"flex",justifyContent:"space-between",gap:16,alignItems:"center",fontFamily:"Arial,'Noto Sans TC',sans-serif",boxShadow:"0 2px 12px rgba(0,0,0,.12)"}}>
    <a href="/" style={{display:"flex",alignItems:"center",gap:10,color:"white",textDecoration:"none"}}><img src={NTUE_LOGO_DATA_URI} alt="國立臺北教育大學校徽" style={{width:42,height:42,objectFit:"contain",background:"white",borderRadius:8,padding:3}}/><div><div style={{fontWeight:800,fontSize:15}}>國立臺北教育大學</div><div style={{fontSize:11,opacity:.78}}>輿情監測與決策支援系統</div></div></a>
    <button onClick={logout} style={{border:"1px solid rgba(255,255,255,.28)",background:"transparent",color:"white",padding:"8px 11px",borderRadius:8,cursor:"pointer",fontSize:13}}>登出</button>
  </nav>
}
