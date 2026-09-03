import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "國北教大輿情監測系統",
  description: "國立臺北教育大學新聞、公開社群與 AI 輿情報告系統",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant-TW">
      <body>
        <nav className="no-print" style={{background:"#0d2147",color:"white",padding:"10px 24px",display:"flex",gap:8,alignItems:"center",fontFamily:"Arial,'Noto Sans TC',sans-serif"}}>
          <strong style={{marginRight:12}}>NTUE 輿情系統</strong>
          <a href="/" style={{color:"white",textDecoration:"none",padding:"7px 11px",borderRadius:8,background:"rgba(255,255,255,.10)"}}>輿情監測</a>
          <a href="/reports" style={{color:"white",textDecoration:"none",padding:"7px 11px",borderRadius:8,background:"rgba(255,255,255,.10)"}}>AI 輿情報告</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
