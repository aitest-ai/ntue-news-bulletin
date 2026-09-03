# 國北教大新聞公佈欄 (NTUE News Bulletin Board)

本系統是一套受密碼保護的定時新聞公佈欄，專門為國立臺北教育大學（NTUE）相關網路新聞設計。

> Deployment trigger: GitHub–Vercel connection refreshed on 2026-09-03.

## 🌟 系統特色
- **密碼安全保護**：首頁設有密碼鎖定（預設密碼：`ntue1234`），登入成功後才會取得 JWT 憑證，並載入新聞內容。後端所有 API 皆受憑證保護。
- **特定頻率採集**：每天早上 **7:30 - 10:00** 期間，每 30 分鐘（07:30, 08:00, 08:30, 09:00, 09:30, 10:00）會自動從 Google News RSS 抓取最新新聞。
- **無 LINE 推播**：本版本完全移除了 LINE 自動推播邏輯，轉為單純的網頁公佈欄形式。
- **輕量與快開**：預設採用 SQLite 本地資料庫，免去繁瑣的 PostgreSQL 資料庫建置，開箱即用。

## 📂 專案架構
詳細的系統架構圖與 API 說明，請參見 [系統產出的 Walkthrough](file:///C:/Users/User/.gemini/antigravity/brain/269e1ac6-37c6-4069-9cca-173a37183dd9/walkthrough.md)。

## 🚀 快速啟動 (Docker Compose)
1. 於本專案根目錄下執行啟動指令：
   ```bash
   docker compose up --build -d
   ```
2. 存取系統：
   - 前台佈告欄：[http://localhost:3002](http://localhost:3002)（預設登入密碼：`ntue1234`）
   - 後端 API 文件：[http://localhost:8001/docs](http://localhost:8001/docs)

## 🛠️ 本地手動執行 (免 Docker)
請依序啟動後端與前端：

### 1. 後端 (FastAPI)
1. 進入 `backend` 目錄：
   ```bash
   cd backend
   ```
2. 安裝套件並啟動伺服器：
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app.main:app --host 127.0.0.1 --port 8001
   ```

### 2. 前端 (Next.js)
1. 進入 `frontend` 目錄：
   ```bash
   cd ../frontend
   ```
2. 安裝套件並啟動開發伺服器：
   ```bash
   npm install
   $env:BACKEND_URL="http://127.0.0.1:8001"
   npm run dev
   ```
3. 造訪 [http://localhost:3002](http://localhost:3002) 並使用 `ntue1234` 登入。
