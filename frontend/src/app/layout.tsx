import type { Metadata } from "next";
import SiteNav from "./SiteNav";
import "./globals.css";

export const metadata: Metadata = {
  title: "國北教大輿情監測系統",
  description: "國立臺北教育大學新聞、公開社群與 AI 輿情報告系統",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant-TW">
      <body>
        <SiteNav />
        {children}
      </body>
    </html>
  );
}
