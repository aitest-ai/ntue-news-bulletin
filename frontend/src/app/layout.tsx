import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "國北教大新聞公佈欄",
  description: "密碼鎖定保護的新聞公佈欄 - 定時自動抓取最新新聞",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant-TW">
      <body>
        {children}
      </body>
    </html>
  );
}
