import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "國北教大輿情監測系統",
  description: "國立臺北教育大學新聞與公開社群輿情監測 — Task-to-Task resilient pipeline",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant-TW">
      <body>{children}</body>
    </html>
  );
}
