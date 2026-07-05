"use client";

import { useState, useEffect } from "react";

// NTUE Emblem Component
const NTUEEmblem = ({ className = "", style = {} }: { className?: string; style?: React.CSSProperties }) => (
  <img 
    src="https://startup.sme.gov.tw/home/upload/rmap/201905/01629_05143dQRVEs.jpg" 
    alt="NTUE Logo" 
    className={className} 
    style={{ objectFit: "contain", display: "inline-block", ...style }}
  />
);

interface NewsItem {
  id: number;
  title: string;
  url: string;
  source: string;
  publish_time: string;
  keyword: string;
  created_at: string;
}

interface KeywordItem {
  id: number;
  word: string;
  created_at: string;
}

interface JobItem {
  id: string;
  name: string;
  trigger: string;
  next_run_time: string | null;
  paused: boolean;
}

interface ToastState {
  show: boolean;
  message: string;
  type: "success" | "error";
}

// Hardcoded production fallback URL
const RENDER_BACKEND_URL = "https://ntue-news-bulletin.onrender.com";

export default function BulletinBoard() {
  // Authentication State
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);

  // Silent automatic routing state (remembers if Vercel proxy has failed in current session)
  const [useDirectBackend, setUseDirectBackend] = useState(false);

  // Layout Tab State
  const [activeTab, setActiveTab] = useState<"bulletin" | "jobs">("bulletin");

  // Core News and Keywords State
  const [news, setNews] = useState<NewsItem[]>([]);
  const [totalNews, setTotalNews] = useState(0);
  const [keywords, setKeywords] = useState<KeywordItem[]>([]);
  const [selectedKeyword, setSelectedKeyword] = useState("");
  const [newKeyword, setNewKeyword] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 10;

  // Background Scheduler Jobs State
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [newJobHour, setNewJobHour] = useState(12);
  const [newJobMinute, setNewJobMinute] = useState(0);

  // System Settings State (Dynamic Recipient Email List)
  const [emailRecipients, setEmailRecipients] = useState<string[]>([]);
  const [newEmailRecipient, setNewEmailRecipient] = useState("");

  // Loaders & Actions State
  const [loadingNews, setLoadingNews] = useState(false);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [toast, setToast] = useState<ToastState>({ show: false, message: "", type: "success" });

  // Load auth state and check fallback routing status on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedToken = localStorage.getItem("bulletin_token");
      if (savedToken) {
        setToken(savedToken);
      }
      
      const savedFallback = sessionStorage.getItem("use_direct_backend") === "true";
      if (savedFallback) {
        setUseDirectBackend(true);
      }
    }
    setAuthChecked(true);
  }, []);

  // Fetch initial data when authenticated
  useEffect(() => {
    if (token) {
      fetchKeywords();
      fetchSettings();
      if (activeTab === "bulletin") {
        fetchNews();
      } else {
        fetchJobs();
      }
    }
  }, [token, page, selectedKeyword, activeTab]);

  // Toast Helper
  const showToast = (message: string, type: "success" | "error") => {
    setToast({ show: true, message, type });
    setTimeout(() => {
      setToast((prev) => ({ ...prev, show: false }));
    }, 4000);
  };

  // Silent safe fetch with automatic direct-to-Render fallback
  const safeFetch = async (path: string, options: RequestInit = {}) => {
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    const directUrl = `${RENDER_BACKEND_URL}${cleanPath}`;
    const proxyUrl = cleanPath;

    // Case 1: Already detected proxy failure in this session -> go direct
    if (useDirectBackend) {
      try {
        return await fetch(directUrl, options);
      } catch (err) {
        throw err;
      }
    }

    // Case 2: Try Vercel's proxy first
    try {
      const res = await fetch(proxyUrl, options);

      // If Vercel returns 502 Bad Gateway / 503 Tunnel Unavailable / 504 Timeout
      if (res.status === 502 || res.status === 503 || res.status === 504) {
        console.warn(`Vercel proxy returned ${res.status}. Silently falling back to Render directly...`);
        const fallbackRes = await fetch(directUrl, options);
        
        if (fallbackRes.ok || fallbackRes.status < 500) {
          setUseDirectBackend(true);
          sessionStorage.setItem("use_direct_backend", "true");
        }
        return fallbackRes;
      }

      return res;
    } catch (err) {
      // If network fails entirely (DNS or CORS on relative proxy path) -> retry directly
      console.warn("Proxy connection error. Silently falling back to Render directly...", err);
      try {
        const fallbackRes = await fetch(directUrl, options);
        setUseDirectBackend(true);
        sessionStorage.setItem("use_direct_backend", "true");
        return fallbackRes;
      } catch (fallbackErr) {
        // Both failed, throw original error
        throw err;
      }
    }
  };

  // Auth Helper: Headers builder
  const getHeaders = () => {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token || ""}`,
      "bypass-tunnel-reminder": "true",
    };
  };

  // Auth Helper: Validate response status
  const handleResponse = async (res: Response) => {
    if (res.status === 401) {
      localStorage.removeItem("bulletin_token");
      setToken(null);
      showToast("認證已過期，請重新登入", "error");
      return false;
    }
    return true;
  };

  // Login handler
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) return;
    setIsLoggingIn(true);

    try {
      const res = await safeFetch("/api/auth/login", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "bypass-tunnel-reminder": "true"
        },
        body: JSON.stringify({ password }),
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("bulletin_token", data.access_token);
        setToken(data.access_token);
        setPassword("");
        showToast("認證成功，歡迎瀏覽公佈欄！", "success");
      } else {
        const data = await res.json();
        showToast(data.detail || "密碼錯誤，拒絕連線", "error");
      }
    } catch (err) {
      showToast("連線至驗證伺服器失敗", "error");
    } finally {
      setIsLoggingIn(false);
    }
  };

  // Logout handler
  const handleLogout = () => {
    localStorage.removeItem("bulletin_token");
    setToken(null);
    setNews([]);
    setKeywords([]);
    setJobs([]);
    setSelectedKeyword("");
    setEmailRecipients([]);
    showToast("您已成功登出系統", "success");
  };

  // Fetch Settings
  const fetchSettings = async () => {
    try {
      const res = await safeFetch("/api/settings", { headers: getHeaders() });
      if (await handleResponse(res)) {
        const data = await res.json();
        setEmailRecipients(data.email_recipients || []);
      }
    } catch (err) {
      showToast("無法載入信箱設定清單", "error");
    }
  };

  // Add Email to list
  const handleAddEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    const email = newEmailRecipient.trim();
    if (!email) return;
    if (!email.includes("@")) {
      showToast("電子信箱格式不正確！", "error");
      return;
    }
    if (emailRecipients.includes(email)) {
      showToast("該電子信箱已在接收清單中！", "error");
      return;
    }

    const updatedList = [...emailRecipients, email];
    try {
      const res = await safeFetch("/api/settings", {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ email_recipients: updatedList }),
      });

      if (await handleResponse(res)) {
        if (res.ok) {
          showToast(`已成功將「${email}」加入日報發送名單！`, "success");
          setNewEmailRecipient("");
          fetchSettings();
        } else {
          const errData = await res.json();
          showToast(errData.detail || "新增收件信箱失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  // Delete Email from list
  const handleDeleteEmail = async (emailToDelete: string) => {
    if (!confirm(`確定要將「${emailToDelete}」從日報發送名單移出嗎？`)) return;

    const updatedList = emailRecipients.filter(email => email !== emailToDelete);
    try {
      const res = await safeFetch("/api/settings", {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ email_recipients: updatedList }),
      });

      if (await handleResponse(res)) {
        if (res.ok) {
          showToast(`已成功將「${emailToDelete}」從名單移出。`, "success");
          fetchSettings();
        } else {
          showToast("移除收件信箱失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  // Fetch Keywords
  const fetchKeywords = async () => {
    try {
      const res = await safeFetch("/api/keywords", { headers: getHeaders() });
      if (await handleResponse(res)) {
        const data = await res.json();
        setKeywords(data);
      }
    } catch (err) {
      showToast("無法載入關鍵字列表", "error");
    }
  };

  // Auto-fetch trigger state
  const [autoFetched, setAutoFetched] = useState(false);

  // Fetch News
  const fetchNews = async () => {
    setLoadingNews(true);
    try {
      const skip = (page - 1) * pageSize;
      let url = `/api/news?skip=${skip}&limit=${pageSize}`;
      if (selectedKeyword) {
        url += `&keyword=${encodeURIComponent(selectedKeyword)}`;
      }
      const res = await safeFetch(url, { headers: getHeaders() });
      if (await handleResponse(res)) {
        const data = await res.json();
        setNews(data.items);
        setTotalNews(data.total);

        // Auto trigger fetch if DB has no news and we haven't checked yet
        if (data.total === 0 && !selectedKeyword && !autoFetched && !isFetching) {
          setAutoFetched(true);
          triggerAutoFetch();
        }
      }
    } catch (err) {
      showToast("無法載入新聞列表", "error");
    } finally {
      setLoadingNews(false);
    }
  };

  // Trigger automatic initial fetch
  const triggerAutoFetch = async () => {
    setIsFetching(true);
    showToast("公佈欄內容目前為空，正在為您自動抓取最新新聞...", "success");
    try {
      const res = await safeFetch("/api/news/fetch", { method: "POST", headers: getHeaders() });
      if (await handleResponse(res)) {
        if (res.ok) {
          const data = await res.json();
          showToast(`自動初始化完成！已抓取並新增 ${data.new_articles_count} 則新聞`, "success");
          fetchNews();
        }
      }
    } catch (err) {
      // ignore
    } finally {
      setIsFetching(false);
    }
  };

  // Fetch Jobs
  const fetchJobs = async () => {
    setLoadingJobs(true);
    try {
      const res = await safeFetch("/api/scheduler/jobs", { headers: getHeaders() });
      if (await handleResponse(res)) {
        const data = await res.json();
        setJobs(data);
      }
    } catch (err) {
      showToast("無法載入排程任務清單", "error");
    } finally {
      setLoadingJobs(false);
    }
  };

  // Add Keyword
  const handleAddKeyword = async (e: React.FormEvent) => {
    e.preventDefault();
    const word = newKeyword.trim();
    if (!word) return;

    try {
      const res = await safeFetch("/api/keywords", {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ word }),
      });

      if (await handleResponse(res)) {
        if (res.ok) {
          showToast(`成功新增關鍵字「${word}」`, "success");
          setNewKeyword("");
          fetchKeywords();
          setPage(1);
          fetchNews();
        } else {
          const errData = await res.json();
          showToast(errData.detail || "新增關鍵字失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  // Delete Keyword
  const handleDeleteKeyword = async (id: number, word: string) => {
    if (!confirm(`確定要刪除關鍵字「${word}」嗎？`)) return;

    try {
      const res = await safeFetch(`/api/keywords/${id}`, {
        method: "DELETE",
        headers: getHeaders(),
      });

      if (await handleResponse(res)) {
        if (res.ok) {
          showToast(`已刪除關鍵字「${word}」`, "success");
          fetchKeywords();
          if (selectedKeyword === word) {
            setSelectedKeyword("");
          }
        } else {
          showToast("刪除關鍵字失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  // Force fetch
  const handleForceFetch = async () => {
    setIsFetching(true);
    showToast("正在抓取最新新聞...", "success");
    try {
      const res = await safeFetch("/api/news/fetch", { method: "POST", headers: getHeaders() });
      if (await handleResponse(res)) {
        if (res.ok) {
          const data = await res.json();
          showToast(`抓取完成！共新增 ${data.new_articles_count} 則新聞`, "success");
          setPage(1);
          fetchNews();
          if (activeTab === "jobs") {
            fetchJobs();
          }
        } else {
          showToast("手動抓取新聞失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    } finally {
      setIsFetching(false);
    }
  };

  // Create Job
  const handleCreateJob = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await safeFetch("/api/scheduler/jobs", {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ hour: newJobHour, minute: newJobMinute }),
      });

      if (await handleResponse(res)) {
        if (res.ok) {
          const data = await res.json();
          showToast(`成功新增定時抓取任務：${data.name}！`, "success");
          fetchJobs();
        } else {
          const errData = await res.json();
          showToast(errData.detail || "新增排程任務失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  // Job Action Handlers
  const handleRunJob = async (jobId: string) => {
    try {
      const res = await safeFetch(`/api/scheduler/jobs/${jobId}/run`, { method: "POST", headers: getHeaders() });
      if (await handleResponse(res)) {
        if (res.ok) {
          showToast(`排程「${jobId}」已立即觸發`, "success");
          setTimeout(fetchNews, 2000);
          setTimeout(fetchJobs, 1000);
        } else {
          showToast("啟動任務失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  const handleToggleJob = async (jobId: string) => {
    try {
      const res = await safeFetch(`/api/scheduler/jobs/${jobId}/toggle`, { method: "POST", headers: getHeaders() });
      if (await handleResponse(res)) {
        if (res.ok) {
          const data = await res.json();
          showToast(data.paused ? `已暫停任務「${jobId}」` : `已啟用任務「${jobId}」`, "success");
          fetchJobs();
        } else {
          showToast("修改狀態失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    if (!confirm(`確定要移除任務「${jobId}」嗎？`)) return;
    try {
      const res = await safeFetch(`/api/scheduler/jobs/${jobId}`, { method: "DELETE", headers: getHeaders() });
      if (await handleResponse(res)) {
        if (res.ok) {
          showToast(`已成功移除任務「${jobId}」`, "success");
          fetchJobs();
        } else {
          showToast("移除排程失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  const handleResetJobs = async () => {
    if (!confirm("確定要重設為系統預設排程嗎？（這將重新註冊 7:30 - 10:00 期間每30分鐘定時採集任務）")) return;
    try {
      const res = await safeFetch("/api/scheduler/jobs/reset", { method: "POST", headers: getHeaders() });
      if (await handleResponse(res)) {
        if (res.ok) {
          showToast("預設排程任務已成功恢復！", "success");
          fetchJobs();
        } else {
          showToast("重置排程任務失敗", "error");
        }
      }
    } catch (err) {
      showToast("連線至伺服器失敗", "error");
    }
  };

  // Date Formatter
  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString("zh-TW", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
    } catch (e) {
      return dateStr;
    }
  };

  const totalPages = Math.ceil(totalNews / pageSize);

  // If initial auth check has not finished, show empty load state
  if (!authChecked) {
    return null;
  }

  // 🔒 SCREEN 1: Render Password Lock Screen if not authenticated
  if (!token) {
    return (
      <div className="login-container">
        <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"} ${toast.show ? "show" : ""}`}>
          {toast.message}
        </div>
        <div className="login-card glass-panel">
          <div className="login-logo-container">
            <NTUEEmblem style={{ width: "96px", height: "96px", borderRadius: "50%" }} />
          </div>
          <h2>國北教大新聞公佈欄</h2>
          <p>此網頁受密碼保護，請輸入系統存取密碼以瀏覽內容</p>
          <form onSubmit={handleLogin} className="login-form">
            <input
              type="password"
              className="input-text"
              placeholder="請輸入瀏覽密碼..."
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              required
            />
            <button type="submit" className="btn btn-primary" disabled={isLoggingIn}>
              {isLoggingIn ? <span className="spinner"></span> : null}
              登入系統
            </button>
          </form>
        </div>
      </div>
    );
  }

  // 🔓 SCREEN 2: Render Bulletin Board Workspace if authenticated
  return (
    <div className="dashboard-container">
      {/* Toast Alert */}
      <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"} ${toast.show ? "show" : ""}`}>
        {toast.message}
      </div>

      {/* Header Panel */}
      <header className="dashboard-header glass-panel">
        <div className="header-title-section">
          <NTUEEmblem style={{ width: "56px", height: "56px", borderRadius: "50%" }} />
          <div className="header-title-text">
            <h1>國北教大新聞公佈欄</h1>
            <p>
              自動於每天 <strong>7:30 - 10:00</strong> 及 <strong>16:00 - 18:00</strong> 期間每 30 分鐘更新。
            </p>
          </div>
        </div>
        <div className="header-actions">
          <button className="btn btn-outline" onClick={handleLogout}>
            登出系統
          </button>
          <button className="btn btn-primary" onClick={handleForceFetch} disabled={isFetching}>
            {isFetching ? <span className="spinner"></span> : null}
            立即重新抓取
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <main className="dashboard-grid">
        {/* Left column: Stats + Keywords */}
        <section>
          {/* Stats Widgets */}
          <div className="stats-container">
            <div className="glass-panel stat-card">
              <div className="stat-val">{totalNews}</div>
              <div className="stat-lbl">佈告新聞總數</div>
            </div>
            <div className="glass-panel stat-card">
              <div className="stat-val">{keywords.length}</div>
              <div className="stat-lbl">監測關鍵字</div>
            </div>
          </div>

          {/* Keywords panel */}
          <div className="glass-panel keyword-panel">
            <h2 className="panel-title">關鍵字管理</h2>
            <form onSubmit={handleAddKeyword} className="keyword-form">
              <input
                type="text"
                className="input-text"
                placeholder="新增關鍵字..."
                value={newKeyword}
                onChange={(e) => setNewKeyword(e.target.value)}
              />
              <button type="submit" className="btn btn-primary">
                新增
              </button>
            </form>

            <div className="keyword-list">
              {keywords.map((kw) => (
                <div key={kw.id} className="keyword-item">
                  <span className="keyword-text" title={kw.word}>
                    {kw.word}
                  </span>
                  <button
                    className="btn-icon-only"
                    onClick={() => handleDeleteKeyword(kw.id, kw.word)}
                    title="刪除此關鍵字"
                  >
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                      <line x1="10" y1="11" x2="10" y2="17"></line>
                      <line x1="14" y1="11" x2="14" y2="17"></line>
                    </svg>
                  </button>
                </div>
              ))}
              {keywords.length === 0 && <div className="empty-state">目前無監測關鍵字</div>}
            </div>
          </div>
        </section>

        {/* Right column: Tabbed Bulletin board */}
        <section className="glass-panel news-panel">
          {/* Tab buttons */}
          <div className="tabs-header">
            <button className={`tab-btn ${activeTab === "bulletin" ? "active" : ""}`} onClick={() => setActiveTab("bulletin")}>
              新聞公佈欄
            </button>
            <button className={`tab-btn ${activeTab === "jobs" ? "active" : ""}`} onClick={() => setActiveTab("jobs")}>
              定期排程與信箱設定
            </button>
          </div>

          {/* TAB 1: News Bulletin list */}
          {activeTab === "bulletin" && (
            <>
              <div className="news-filters">
                <h2 className="panel-title" style={{ marginBottom: 0 }}>
                  佈告內容
                </h2>
                <select
                  className="select-filter"
                  value={selectedKeyword}
                  onChange={(e) => {
                    setSelectedKeyword(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">所有關鍵字篩選</option>
                  {keywords.map((kw) => (
                    <option key={kw.id} value={kw.word}>
                      {kw.word}
                    </option>
                  ))}
                </select>
              </div>

              <div className="news-table-wrapper">
                {loadingNews ? (
                  <div className="empty-state">
                    <span className="spinner" style={{ width: "30px", height: "30px", borderWidth: "4px" }}></span>
                    <p style={{ marginTop: "1rem" }}>讀取新聞公佈欄中...</p>
                  </div>
                ) : news.length > 0 ? (
                  <table className="news-table">
                    <thead>
                      <tr>
                        <th>新聞標題 / 原始連結</th>
                        <th style={{ width: "150px" }}>來源</th>
                        <th style={{ width: "180px" }}>發布時間</th>
                      </tr>
                    </thead>
                    <tbody>
                      {news.map((item) => (
                        <tr key={item.id} className="news-row">
                          <td>
                            <a href={item.url} target="_blank" rel="noopener noreferrer" className="news-title-link">
                              {item.title}
                            </a>
                            <span className="keyword-badge">{item.keyword}</span>
                          </td>
                          <td>
                            <span className="source-badge">{item.source}</span>
                          </td>
                          <td>
                            <span className="news-time">{formatDate(item.publish_time)}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="empty-state">沒有符合條件的新聞</div>
                )}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="pagination-container">
                  <span className="pagination-info">
                    顯示第 {(page - 1) * pageSize + 1} 至 {Math.min(page * pageSize, totalNews)} 則新聞，共 {totalNews} 則
                  </span>
                  <div className="pagination-controls">
                    <button className="btn btn-outline" onClick={() => setPage((p) => Math.max(p - 1, 1))} disabled={page === 1}>
                      上一頁
                    </button>
                    <button
                      className="btn btn-outline"
                      onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                      disabled={page === totalPages}
                    >
                      下一頁
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* TAB 2: Scheduled cron tasks & Email configurations */}
          {activeTab === "jobs" && (
            <div style={{ padding: "0.5rem 0" }}>
              <div className="news-filters" style={{ flexWrap: "wrap", gap: "1rem" }}>
                <h2 className="panel-title" style={{ marginBottom: 0 }}>
                  定時排程排程任務
                </h2>
                
                {/* Add Job Form */}
                <form onSubmit={handleCreateJob} style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                  <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                    新增抓取時段：
                  </span>
                  <select
                    className="select-filter"
                    value={newJobHour}
                    onChange={(e) => setNewJobHour(parseInt(e.target.value))}
                    style={{ width: "80px", minWidth: "auto", padding: "0.5rem", height: "38px" }}
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={i}>{String(i).padStart(2, "0")} 時</option>
                    ))}
                  </select>
                  <select
                    className="select-filter"
                    value={newJobMinute}
                    onChange={(e) => setNewJobMinute(parseInt(e.target.value))}
                    style={{ width: "80px", minWidth: "auto", padding: "0.5rem", height: "38px" }}
                  >
                    {Array.from({ length: 60 }, (_, i) => (
                      <option key={i} value={i}>{String(i).padStart(2, "0")} 分</option>
                    ))}
                  </select>
                  <button type="submit" className="btn btn-primary" style={{ padding: "0.5rem 1rem", fontSize: "0.85rem", height: "38px", display: "flex", alignItems: "center" }}>
                    新增排程
                  </button>
                </form>

                <button className="btn btn-danger-outline" onClick={handleResetJobs}>
                  還原預設任務
                </button>
              </div>

              <div className="news-table-wrapper" style={{ marginTop: "1rem" }}>
                {loadingJobs ? (
                  <div className="empty-state">
                    <span className="spinner"></span>
                    <p style={{ marginTop: "0.5rem" }}>讀取排程清單中...</p>
                  </div>
                ) : jobs.length > 0 ? (
                  <table className="news-table">
                    <thead>
                      <tr>
                        <th>任務 ID / 名稱</th>
                        <th>定時觸發時間</th>
                        <th>下次執行時間</th>
                        <th>狀態</th>
                        <th style={{ width: "220px", textAlign: "right" }}>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((job) => (
                        <tr key={job.id} className="news-row">
                          <td style={{ fontWeight: 600 }}>
                            <div>{job.name}</div>
                            <code style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{job.id}</code>
                          </td>
                          <td style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                            <code>{job.trigger}</code>
                          </td>
                          <td style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                            {job.next_run_time ? formatDate(job.next_run_time) : "無"}
                          </td>
                          <td>
                            <span className={`status-badge ${job.paused ? "status-paused" : "status-active"}`}>
                              {job.paused ? "已暫停" : "執行中"}
                            </span>
                          </td>
                          <td>
                            <div className="job-actions" style={{ justifyContent: "flex-end" }}>
                              <button className="btn btn-primary" onClick={() => handleRunJob(job.id)} title="立即抓取一次此任務">
                                執行
                              </button>
                              <button className="btn btn-outline" onClick={() => handleToggleJob(job.id)}>
                                {job.paused ? "啟用" : "暫停"}
                              </button>
                              <button className="btn btn-danger-outline" onClick={() => handleDeleteJob(job.id)}>
                                刪除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="empty-state">
                    <p>目前無排程任務。</p>
                    <p style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>您可以點擊上方「還原預設任務」重設預設排程。</p>
                  </div>
                )}
              </div>

              {/* Dynamic Recipient Email List Configuration */}
              <div className="glass-panel" style={{ padding: "1.5rem", marginTop: "2.5rem", border: "1px solid var(--border-color)" }}>
                <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--primary-color)", marginBottom: "0.5rem" }}>
                  輿情日報 Email 接收信箱清單管理
                </h3>
                <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "1rem", lineHeight: 1.4 }}>
                  設定排程任務執行完成後，自動將當日最新新聞摘要傳送至下方列出的信箱。如果今天沒有新新聞，亦會傳送「今日無新聞」之安全回報。
                </p>

                {/* Add Email Form */}
                <form onSubmit={handleAddEmail} style={{ display: "flex", gap: "0.5rem", maxWidth: "500px", marginBottom: "1.5rem" }}>
                  <input
                    type="email"
                    className="input-text"
                    placeholder="輸入要接收日報的新信箱..."
                    value={newEmailRecipient}
                    onChange={(e) => setNewEmailRecipient(e.target.value)}
                    required
                  />
                  <button type="submit" className="btn btn-primary" style={{ whiteSpace: "nowrap" }}>
                    新增信箱
                  </button>
                </form>

                {/* Email Recipients List */}
                <div className="keyword-list" style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxWidth: "500px" }}>
                  {emailRecipients.map((email) => (
                    <div key={email} className="keyword-item" style={{ width: "100%", justifyContent: "space-between" }}>
                      <span className="keyword-text" style={{ fontSize: "0.85rem", padding: "4px" }}>
                        {email}
                      </span>
                      <button
                        className="btn btn-danger-outline"
                        style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem", height: "auto" }}
                        onClick={() => handleDeleteEmail(email)}
                      >
                        移除
                      </button>
                    </div>
                  ))}
                  {emailRecipients.length === 0 && (
                    <div className="empty-state" style={{ padding: "1rem" }}>
                      目前無接收信箱，日報將無法發送。
                    </div>
                  )}
                </div>

                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "1rem", lineHeight: 1.4 }}>
                  ※ 變更後的新信箱於「第一次發信」時，會收到一封來自 FormSubmit 的確認啟動信（若尚未啟用過該信箱），點擊信中確認按鈕後即開始自動接收日報。如果您的伺服器配置了 SMTP 發信（如 Gmail 帳密），信件將會經由您的 Gmail 帳號發送，且不需要任何確認。
                </p>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
