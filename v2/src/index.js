const QUERIES = [
  '國立臺北教育大學',
  '國北教大',
  '北教大'
];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/api/run' && request.method === 'POST') {
      return json(await runPipeline(env));
    }
    if (url.pathname === '/api/articles') return json(await listArticles(env));
    if (url.pathname === '/api/health') return json(await sourceHealth(env));
    if (url.pathname === '/api/tasks') return json(await taskRuns(env));
    if (url.pathname === '/api/status') return json({ ok: true, app: env.APP_NAME || '國北教大輿情系統 2.0', now: new Date().toISOString() });
    return new Response(renderDashboard(), { headers: { 'content-type': 'text/html; charset=utf-8' } });
  },

  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(runPipeline(env));
  }
};

async function runPipeline(env) {
  const started = new Date().toISOString();
  const report = { started_at: started, tasks: [] };
  for (const keyword of QUERIES) {
    const source = 'google-news-rss';
    try {
      const items = await taskFetchGoogleNews(keyword);
      report.tasks.push(await taskNormalizeValidateStore(env, source, keyword, items));
      await updateHealth(env, source, 'news', true, items.length, null);
    } catch (error) {
      await logTask(env, 'source_fetch', source, 'failed', 0, 0, String(error));
      await updateHealth(env, source, 'news', false, 0, String(error));
      report.tasks.push({ task: 'source_fetch', source, keyword, status: 'failed', error: String(error) });
    }
  }
  report.finished_at = new Date().toISOString();
  return report;
}

async function taskFetchGoogleNews(keyword) {
  const q = encodeURIComponent(keyword + ' when:7d');
  const url = `https://news.google.com/rss/search?q=${q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant`;
  const res = await fetch(url, { headers: { 'user-agent': 'NTUE-Opinion-Monitor/2.0' } });
  if (!res.ok) throw new Error(`Google News HTTP ${res.status}`);
  const xml = await res.text();
  return parseRss(xml);
}

async function taskNormalizeValidateStore(env, source, keyword, items) {
  const started = new Date().toISOString();
  let stored = 0;
  for (const item of items) {
    if (!item.title || !item.link) continue;
    const date = resolveDate(item.pubDate);
    const relevance = relevanceScore(item.title, keyword);
    if (relevance < 0.35) continue;
    try {
      await env.DB.prepare(`INSERT OR IGNORE INTO articles
        (source, source_type, url, title, content, author, published_at, published_at_raw, published_at_confidence, discovered_at, keyword, relevance_score, status)
        VALUES (?, 'news', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'valid')`)
        .bind(source, item.link, item.title, item.description || '', item.source || '', date.value, item.pubDate || null, date.confidence, new Date().toISOString(), keyword, relevance)
        .run();
      stored++;
    } catch (_) {}
  }
  await env.DB.prepare(`INSERT INTO task_runs (task_name, source, status, started_at, finished_at, items_in, items_out)
    VALUES ('normalize_validate_store', ?, 'success', ?, ?, ?, ?)`)
    .bind(source, started, new Date().toISOString(), items.length, stored).run();
  return { task: 'normalize_validate_store', source, keyword, status: 'success', items_in: items.length, items_out: stored };
}

function resolveDate(raw) {
  if (!raw) return { value: null, confidence: 0 };
  const d = new Date(raw);
  if (Number.isNaN(d.getTime()) || d.getTime() <= 0) return { value: null, confidence: 0 };
  return { value: d.toISOString(), confidence: 1 };
}

function relevanceScore(title, keyword) {
  const t = title.toLowerCase();
  if (t.includes(keyword.toLowerCase())) return 1;
  if (t.includes('國北教') || t.includes('北教大')) return 0.85;
  return 0.4;
}

function parseRss(xml) {
  const blocks = xml.match(/<item>[\s\S]*?<\/item>/g) || [];
  return blocks.map(block => ({
    title: decodeXml(tag(block, 'title')),
    link: decodeXml(tag(block, 'link')),
    pubDate: decodeXml(tag(block, 'pubDate')),
    description: decodeXml(stripTags(tag(block, 'description'))),
    source: decodeXml(tag(block, 'source'))
  }));
}

function tag(block, name) {
  const m = block.match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${name}>`, 'i'));
  return m ? m[1].replace(/^<!\[CDATA\[|\]\]>$/g, '') : '';
}

function stripTags(s) { return (s || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(); }
function decodeXml(s) { return (s || '').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>'); }

async function updateHealth(env, source, type, success, count, error) {
  const now = new Date().toISOString();
  await env.DB.prepare(`INSERT INTO source_health
    (source, source_type, status, last_attempt_at, last_success_at, success_count, failure_count, last_error, items_last_run)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(source) DO UPDATE SET
      status=excluded.status,
      last_attempt_at=excluded.last_attempt_at,
      last_success_at=CASE WHEN excluded.status='healthy' THEN excluded.last_success_at ELSE source_health.last_success_at END,
      success_count=source_health.success_count + CASE WHEN excluded.status='healthy' THEN 1 ELSE 0 END,
      failure_count=source_health.failure_count + CASE WHEN excluded.status='failed' THEN 1 ELSE 0 END,
      last_error=excluded.last_error,
      items_last_run=excluded.items_last_run`)
    .bind(source, type, success ? 'healthy' : 'failed', now, success ? now : null, success ? 1 : 0, success ? 0 : 1, error, count).run();
}

async function logTask(env, task, source, status, input, output, error) {
  const now = new Date().toISOString();
  await env.DB.prepare(`INSERT INTO task_runs (task_name, source, status, started_at, finished_at, items_in, items_out, error)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(task, source, status, now, now, input, output, error || null).run();
}

async function listArticles(env) {
  return await env.DB.prepare(`SELECT id, source, title, url, published_at, discovered_at, keyword, relevance_score, sentiment, risk_level
    FROM articles ORDER BY COALESCE(published_at, discovered_at) DESC LIMIT 100`).all();
}
async function sourceHealth(env) { return await env.DB.prepare('SELECT * FROM source_health ORDER BY source').all(); }
async function taskRuns(env) { return await env.DB.prepare('SELECT * FROM task_runs ORDER BY started_at DESC LIMIT 100').all(); }

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': '*' } });
}

function renderDashboard() {
  return `<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>國北教大輿情系統 2.0</title><style>
  body{font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif;margin:0;background:#f4f7fb;color:#172033}.wrap{max-width:1180px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center}.badge{background:#e9f7ef;color:#147a42;padding:7px 11px;border-radius:999px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}.card{background:white;border-radius:16px;padding:18px;box-shadow:0 6px 22px #14213d12}.big{font-size:30px;font-weight:800}.two{display:grid;grid-template-columns:2fr 1fr;gap:14px}.row{padding:13px 0;border-bottom:1px solid #edf0f5}.muted{color:#788397;font-size:13px}.healthy{color:#14804a}.failed{color:#c73737}button{border:0;border-radius:10px;background:#172f66;color:white;padding:10px 14px;cursor:pointer}@media(max-width:800px){.grid,.two{grid-template-columns:1fr}.top{align-items:flex-start;gap:10px;flex-direction:column}}
  </style></head><body><div class="wrap"><div class="top"><div><h1>國北教大輿情系統 2.0</h1><div class="muted">Task-to-Task Intelligence Pipeline · MVP</div></div><div><span class="badge">V2 獨立系統</span> <button onclick="runNow()">立即執行一次</button></div></div><div class="grid"><div class="card"><div class="muted">近 100 筆新聞</div><div class="big" id="count">—</div></div><div class="card"><div class="muted">來源健康</div><div class="big" id="healthy">—</div></div><div class="card"><div class="muted">失敗來源</div><div class="big" id="failed">—</div></div><div class="card"><div class="muted">最近 Task</div><div class="big" id="tasks">—</div></div></div><div class="two"><div class="card"><h2>最新輿情資料</h2><div id="articles">讀取中…</div></div><div class="card"><h2>來源健康度</h2><div id="health">讀取中…</div><h2>Task 執行紀錄</h2><div id="runs">讀取中…</div></div></div></div><script>
async function j(u,o){const r=await fetch(u,o);return r.json()}function esc(s){return String(s||'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]))}async function load(){const [a,h,t]=await Promise.all([j('/api/articles'),j('/api/health'),j('/api/tasks')]);const ar=a.results||[],hr=h.results||[],tr=t.results||[];count.textContent=ar.length;healthy.textContent=hr.filter(x=>x.status==='healthy').length;failed.textContent=hr.filter(x=>x.status==='failed').length;tasks.textContent=tr.length;articles.innerHTML=ar.slice(0,30).map(x=>'<div class="row"><b>'+esc(x.title)+'</b><div class="muted">'+esc(x.source)+' · '+esc((x.published_at||x.discovered_at||'').slice(0,16))+' · '+esc(x.keyword)+'</div><a target="_blank" href="'+esc(x.url)+'">查看來源</a></div>').join('')||'尚無資料';health.innerHTML=hr.map(x=>'<div class="row"><b class="'+esc(x.status)+'">'+esc(x.source)+'</b><div class="muted">'+esc(x.status)+' · 本次 '+x.items_last_run+' 筆</div></div>').join('')||'尚未執行';runs.innerHTML=tr.slice(0,12).map(x=>'<div class="row"><b>'+esc(x.task_name)+'</b><div class="muted">'+esc(x.status)+' · '+x.items_out+'/'+x.items_in+'</div></div>').join('')||'尚無紀錄'}async function runNow(){const b=event.target;b.disabled=true;b.textContent='執行中…';try{await j('/api/run',{method:'POST'});await load()}finally{b.disabled=false;b.textContent='立即執行一次'}}load();
</script></body></html>`;
}
