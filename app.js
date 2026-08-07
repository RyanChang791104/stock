// 台灣股市全市場實時串流與量化飆股篩選系統 (2026年最新版 — 官方 Open API + 全欄排序)

let allStocks = [];
let filteredStocks = [];
let momentumStocks = [];
let currentPage = 1;
const pageSize = 50;
let autoRefreshTimer = null;
let isLiveStreaming = true;

// 目前排序狀態
let sortKey = 'score';
let sortDir = 'desc'; // 'asc' | 'desc'
let momentumFilter = 'all'; // 'all' | 'ultimate' | 'burst'

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initCharts();
  initAIAnalyst();
  initSortHeaders();
  initMomentumControls();
  loadFullStockDatabase();
  loadMomentumStocks();
  setInterval(loadMomentumStocks, 10000); // 10秒更新一次 AI 飆股
  setInterval(loadFullStockDatabase, 15000); // 定期更新大盤
});

/* ── 排序表頭初始化 ── */
function initSortHeaders() {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.style.cursor = 'pointer';
    th.style.userSelect = 'none';
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (sortKey === key) {
        sortDir = sortDir === 'desc' ? 'asc' : 'desc';
      } else {
        sortKey = key;
        sortDir = 'desc'; // 新欄位預設降序
      }
      // 更新所有 header 箭頭
      document.querySelectorAll('th.sortable').forEach(h => {
        const arrow = h.querySelector('.sort-arrow');
        if (!arrow) return;
        if (h.dataset.key === sortKey) {
          h.classList.add('active-sort');
          arrow.textContent = sortDir === 'desc' ? '▼' : '▲';
        } else {
          h.classList.remove('active-sort');
          arrow.textContent = '⇅';
        }
      });
      currentPage = 1;
      sortAndRender();
    });
  });
}

/* ── 排序 ── */
function sortAndRender() {
  filteredStocks.sort((a, b) => {
    let av, bv;
    if (sortKey === 'changePct') {
      av = parseChangePct(a.change);
      bv = parseChangePct(b.change);
    } else {
      av = a[sortKey] ?? 0;
      bv = b[sortKey] ?? 0;
    }
    // 字串排序 (symbol)
    if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortDir === 'asc' ? av - bv : bv - av;
  });
  renderScreenerTable(false);
}

function parseChangePct(str) {
  if (!str) return 0;
  return parseFloat(str.replace('%', '').replace('+', '')) || 0;
}
let techCache = {};

function generateSparklineSvg(history) {
  if (!history || history.length < 2) return '<span style="color:var(--text-dim);font-size:0.75rem;">N/A</span>';
  
  const min = Math.min(...history);
  const max = Math.max(...history);
  const range = max - min;
  
  const width = 80;
  const height = 20;
  const padding = 2;
  
  const points = [];
  for (let i = 0; i < history.length; i++) {
    const x = padding + (i * (width - 2 * padding)) / (history.length - 1);
    const y = height - padding - (range === 0 ? (height - 2 * padding) / 2 : ((history[i] - min) * (height - 2 * padding)) / range);
    points.push(`${x},${y}`);
  }
  
  const polylinePoints = points.join(' ');
  const color = history[history.length - 1] >= history[0] ? 'var(--accent-red)' : 'var(--accent-green)';
  
  return `
    <svg width="${width}" height="${height}" style="overflow:visible;">
      <polyline
        fill="none"
        stroke="${color}"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
        points="${polylinePoints}" />
    </svg>
  `;
}

/* ── 1. 載入全台股大數據庫 ── */
async function loadFullStockDatabase() {
  const countText = document.getElementById('results-count-text');
  if (countText) countText.textContent = '正在從 TWSE + TPEx 官方 API 載入全台股實時行情...';

  try {
    const [stocksRes, cacheRes] = await Promise.all([
      fetch('stocks-full-8000.json?t=' + Date.now()),
      fetch('tech_cache.json?t=' + Date.now())
    ]);
    if (!stocksRes.ok) throw new Error('Data fetch failed');
    allStocks = await stocksRes.json();
    if (cacheRes.ok) {
      const data = await cacheRes.json();
      techCache = data.data || {};
    }

    initScreenerControls();
    applyScreenerFilters();
    startLiveAutoRefresh();
    updateMarquee();
    const totalEl = document.getElementById('total-stocks');
    if (totalEl) totalEl.textContent = allStocks.length;
  } catch (e) {
    if (countText) countText.textContent = '⚠️ 資料庫連線例外: ' + e.message;
  }
}

/* ── 2. 30 秒實時串流更新 ── */
function startLiveAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(async () => {
    if (!isLiveStreaming) return;
    try {
      const res = await fetch('stocks-full-8000.json?t=' + Date.now());
      if (res.ok) {
        const latestStocks = await res.json();
        updateStockPricesInMemory(latestStocks);
        sortAndRender();
        renderMomentumTable();
        updateMarquee();
      }
    } catch (e) {}
  }, 5000);
}

function updateStockPricesInMemory(latestStocks) {
  const map = new Map(latestStocks.map(s => [s.symbol, s]));
  
  // Update main stock list
  allStocks.forEach(s => {
    const fresh = map.get(s.symbol);
    if (fresh) {
      s.price = fresh.price;
      s.change = fresh.change;
      s.volume = fresh.volume ?? s.volume ?? 0;
      s.last_update = fresh.last_update;
      s.trade_date = fresh.trade_date ?? s.trade_date ?? '';
      s.data_source = fresh.data_source ?? s.data_source ?? '';
    }
  });

  // Update momentum stock list
  momentumStocks.forEach(s => {
    const fresh = map.get(s.symbol);
    if (fresh) {
      s.price = fresh.price;
      s.change = fresh.change;
      s.volume = fresh.volume ?? fresh.volume ?? 0;
      s.last_update = fresh.last_update;
      s.trade_date = fresh.trade_date ?? s.trade_date ?? '';
      s.data_source = fresh.data_source ?? s.data_source ?? '';
    }
  });
}

function updateMarquee() {
  const watchList = ['2330', '2317', '2454', '2379', '2382', '3017', '3324', '0050', '0056'];
  const tickerTrack = document.querySelector('.ticker-track');
  if (!tickerTrack) return;
  
  // Detect data source and trade date from first stock
  let dataSource = '';
  let tradeDate = '';
  if (allStocks.length > 0) {
    const sample = allStocks.find(s => s.data_source) || allStocks[0];
    dataSource = sample.data_source || 'OpenAPI';
    tradeDate = sample.trade_date || '';
  }
  const srcBadge = dataSource === 'MIS即時'
    ? '<span style="background:#10b981;color:#fff;padding:1px 8px;border-radius:10px;font-size:0.78em;margin-left:6px;">MIS 即時</span>'
    : '<span style="background:#f59e0b;color:#fff;padding:1px 8px;border-radius:10px;font-size:0.78em;margin-left:6px;">OpenAPI</span>';
  const dateStr = tradeDate ? ` | 交易日: ${tradeDate}` : '';
  let html = `<div class="ticker-item"><span class="t-name">⚡ 台灣股市全市場即時連線</span> <span class="t-val">System Online${dateStr}</span>${srcBadge}</div>`;
  
  watchList.forEach(sym => {
    const s = allStocks.find(st => st.symbol.includes(sym));
    if (s) {
      let chgColor = 'var(--text-dim)';
      let chgArrow = '';
      if (s.change.includes('+')) { chgColor = 'var(--accent-red)'; chgArrow = '▲'; }
      else if (s.change.includes('-')) { chgColor = 'var(--accent-green)'; chgArrow = '▼'; }
      html += `<div class="ticker-item"><span class="t-name">${s.name} (${sym})</span> <span class="t-val">NT$ ${s.price}</span> <span style="color:${chgColor};font-weight:700;">${chgArrow} ${s.change}</span></div>`;
    }
  });
  
  tickerTrack.innerHTML = html;
}

/* ── 3. 控制台初始化 ── */
function initScreenerControls() {
  const searchInput = document.getElementById('screener-search');
  const filterSector = document.getElementById('screener-filter');
  const filterMarket = document.getElementById('screener-market');
  const sliderYoy = document.getElementById('filter-yoy');
  const yoyVal = document.getElementById('yoy-val');
  const sliderPe = document.getElementById('filter-pe');
  const peVal = document.getElementById('pe-val');
  const presetBtns = document.querySelectorAll('.preset-btn');
  const toggleLiveBtn = document.getElementById('toggle-live-btn');

  if (toggleLiveBtn) {
    toggleLiveBtn.addEventListener('click', () => {
      isLiveStreaming = !isLiveStreaming;
      toggleLiveBtn.className = isLiveStreaming ? 'live-badge live-on' : 'live-badge live-off';
      toggleLiveBtn.innerHTML = isLiveStreaming
        ? `<span class="dot-live"></span> 🔴 實時串流更新中 (5秒)`
        : `⏸️ 實時串流已暫停`;
    });
  }

  function debounce(fn, ms) {
    let timer;
    return function(...args) { clearTimeout(timer); timer = setTimeout(() => fn.apply(this, args), ms); };
  }

  const debouncedApply = debounce(() => { currentPage = 1; applyScreenerFilters(); }, 80);

  if (sliderYoy && yoyVal) sliderYoy.addEventListener('input', e => { yoyVal.textContent = `≥ ${e.target.value}%`; debouncedApply(); });
  if (sliderPe && peVal) sliderPe.addEventListener('input', e => { peVal.textContent = `≤ ${e.target.value}x`; debouncedApply(); });

  presetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      presetBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = btn.getAttribute('data-mode');
      if (mode === 'burst') { if (sliderYoy) { sliderYoy.value = 0; yoyVal.textContent = '≥ 0%'; } if (sliderPe) { sliderPe.value = 60; peVal.textContent = '≤ 60x'; } }
      else if (mode === 'ai-growth') { if (sliderYoy) { sliderYoy.value = 30; yoyVal.textContent = '≥ 30%'; } }
      else if (mode === 'undervalued') { if (sliderPe) { sliderPe.value = 20; peVal.textContent = '≤ 20x'; } }
      currentPage = 1;
      applyScreenerFilters();
    });
  });

  if (searchInput) searchInput.addEventListener('input', debouncedApply);
  if (filterSector) filterSector.addEventListener('change', debouncedApply);
  if (filterMarket) filterMarket.addEventListener('change', debouncedApply);
}

/* ── 4. 多因子篩選核心 ── */
function applyScreenerFilters() {
  const searchInput = document.getElementById('screener-search');
  const filterSector = document.getElementById('screener-filter');
  const filterMarket = document.getElementById('screener-market');
  const sliderYoy = document.getElementById('filter-yoy');
  const sliderPe = document.getElementById('filter-pe');
  const activePreset = document.querySelector('.preset-btn.active');
  const currentMode = activePreset ? activePreset.getAttribute('data-mode') : 'all';

  const q = searchInput ? searchInput.value.toLowerCase().trim() : '';
  const sector = filterSector ? filterSector.value : 'all';
  const market = filterMarket ? filterMarket.value : 'all';
  const minYoy = sliderYoy ? parseFloat(sliderYoy.value) : 0;
  const maxPe = sliderPe ? parseFloat(sliderPe.value) : 999;

  filteredStocks = allStocks.filter(s => {
    if (q) {
      const isMatch = s.symbol.toLowerCase().includes(q) ||
                      s.name.toLowerCase().includes(q) ||
                      (s.desc && s.desc.toLowerCase().includes(q));
      if (isMatch) return true;
      return false; // 搜尋模式下只顯示精準命中
    }
    if (sector !== 'all' && !s.sector.includes(sector)) return false;
    if (market !== 'all' && s.market !== market) return false;
    if (s.yoy < minYoy) return false;
    if (s.pe > maxPe) return false;
    if (currentMode === 'burst') return s.score >= 70;
    if (currentMode === 'ai-growth') return s.yoy >= 25;
    if (currentMode === 'undervalued') return s.pe <= 22;
    if (currentMode === 'institutional') return s.inst && (s.inst.includes('買') || s.inst.includes('鎖碼') || s.inst.includes('加碼'));
    return true;
  });

  // 依目前排序欄重新排序
  sortAndRender();
}

/* ── 5. 高效能表格渲染 ── */
function renderScreenerTable(resetPagination = false) {
  const body = document.getElementById('screener-body');
  const countText = document.getElementById('results-count-text');
  const paginationControls = document.getElementById('pagination-controls');

  if (!body) return;

  if (countText) {
    const sortLabel = getSortLabel();
    const sample = allStocks.find(s => s.data_source) || {};
    const src = sample.data_source || 'OpenAPI';
    const srcLabel = src === 'MIS即時' ? '🟢 MIS 即時行情' : '🟡 OpenAPI 日收盤';
    const dateLabel = sample.trade_date ? ` | 交易日: ${sample.trade_date}` : '';
    countText.textContent = `${srcLabel}${dateLabel} — 共 ${filteredStocks.length} 檔 | 排序: ${sortLabel} | 第 ${currentPage} 頁`;
  }

  if (filteredStocks.length === 0) {
    body.innerHTML = `<tr><td colspan="12" style="text-align:center; padding:30px; color:var(--text-muted);">無符合條件股票，請調整搜尋關鍵字或條件。</td></tr>`;
    if (paginationControls) paginationControls.innerHTML = '';
    return;
  }

  const totalPages = Math.ceil(filteredStocks.length / pageSize);
  if (currentPage > totalPages) currentPage = totalPages;
  if (currentPage < 1) currentPage = 1;

  const startIdx = (currentPage - 1) * pageSize;
  const pageItems = filteredStocks.slice(startIdx, startIdx + pageSize);

  const htmlRows = pageItems.map(s => {
    const chgPct = parseChangePct(s.change);
    const changeColor = chgPct > 0 ? 'var(--accent-red)' : (chgPct < 0 ? 'var(--accent-green)' : 'var(--text-main)');
    const chgArrow = chgPct > 0 ? '▲' : (chgPct < 0 ? '▼' : '');

    let scoreClass = 'score-normal';
    let scoreBadgeText = `${s.score} 分`;
    if (s.score >= 90) { scoreClass = 'score-high'; scoreBadgeText = `🔥 ${s.score}分 (超強飆股)`; }
    else if (s.score >= 80) { scoreClass = 'score-medium'; scoreBadgeText = `🚀 ${s.score}分 (強勢股)`; }

    const marketPill = s.market === '台股ETF' ? 'pill-purple' : (s.market === 'TWSE上市' ? 'pill-green' : 'pill-blue');

    const vol = s.volume ?? 0;
    const volDisplay = vol >= 10000
      ? `${(vol / 10000).toFixed(1)}萬張`
      : vol >= 1000
        ? `${(vol / 1000).toFixed(1)}千張`
        : `${vol}張`;

    const yoyColor = s.yoy > 30 ? '#10b981' : s.yoy > 0 ? '#6ee7b7' : s.yoy < 0 ? 'var(--accent-red)' : 'var(--text-muted)';
    const yoyDisplay = (typeof s.yoy === 'number' && s.yoy !== 0) ? `${s.yoy > 0 ? '+' : ''}${s.yoy.toFixed(1)}%` : '-';
    const peDisplay = s.pe > 0 ? `${s.pe}x` : '-';
    const peColor = s.pe > 0 && s.pe < 20 ? '#10b981' : s.pe > 50 ? '#f87171' : 'var(--text-main)';

    return `
      <tr class="stock-row-tick">
        <td><span class="score-badge ${scoreClass}">${scoreBadgeText}</span></td>
        <td class="symbol-code">${s.symbol}</td>
        <td><strong>${s.name}</strong><br><span style="font-size:0.75rem; color:var(--text-dim);">${s.desc || ''}</span></td>
        <td><span class="pill ${marketPill}">${s.market}</span></td>
        <td><span class="pill pill-blue">${s.sector}</span></td>
        <td style="font-family:var(--font-mono); font-weight:800; font-size:0.95rem;">NT$ ${s.price.toLocaleString('zh-TW', {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
        <td style="color: ${changeColor}; font-weight:700; font-family:var(--font-mono);">${chgArrow} ${s.change}</td>
        <td style="font-family:var(--font-mono); color:var(--text-main);">${volDisplay}</td>
        <td style="color:${yoyColor}; font-weight:700; font-family:var(--font-mono);">${yoyDisplay}</td>
        <td style="color:${peColor}; font-family:var(--font-mono);">${peDisplay}</td>
        <td><span class="pill pill-purple">${s.inst}</span></td>
        <td style="text-align:center;">${generateSparklineSvg(techCache[s.symbol.split('.')[0]]?.history5d)}</td>
        <td><button class="time-btn" style="background:var(--primary); color:#fff; font-weight:700;" onclick="analyzeStockTarget('${s.symbol}', '${s.name}', ${s.price})">AI 買點診斷</button></td>
      </tr>
    `;
  });

  body.innerHTML = htmlRows.join('');

  if (paginationControls) {
    let pagesHtml = `<button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="changePage(${currentPage - 1})">上一頁</button>`;
    // 顯示最多 7 個頁碼
    const startPage = Math.max(1, currentPage - 3);
    const endPage = Math.min(totalPages, startPage + 6);
    for (let p = startPage; p <= endPage; p++) {
      pagesHtml += `<button class="page-btn ${p === currentPage ? 'active-page' : ''}" onclick="changePage(${p})">${p}</button>`;
    }
    pagesHtml += `<button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="changePage(${currentPage + 1})">下一頁</button>`;
    pagesHtml += `<span class="page-info" style="margin-left:8px;">頁次 ${currentPage} / ${totalPages} (每頁 ${pageSize} 檔)</span>`;
    paginationControls.innerHTML = pagesHtml;
  }
}

/* ── 載入並渲染 AI 飆股漏斗 ── */
async function loadMomentumStocks() {
  try {
    const res = await fetch('momentum-stocks.json?t=' + Date.now());
    if (!res.ok) throw new Error('fetch failed');
    const data = await res.json();
    momentumStocks = data.top_momentum || [];
    renderMomentumTable();
  } catch (err) {
    console.error('Momentum error:', err);
  }
}

function renderMomentumTable() {
  const body = document.getElementById('momentum-body');
  const countText = document.getElementById('momentum-count-text');
  if (!body) return;
  
  if (momentumStocks.length === 0) {
    body.innerHTML = `<tr><td colspan="10" style="text-align:center;">目前無符合標準的飆股</td></tr>`;
    return;
  }

  // Apply filters based on score threshold
  let displayedStocks = momentumStocks;
  if (momentumFilter === 'ultimate') {
    displayedStocks = momentumStocks.filter(s => s.ai_score >= 80);
  } else if (momentumFilter === 'burst') {
    displayedStocks = momentumStocks.filter(s => s.ai_score >= 70 && s.ai_score < 80);
  }

  if (countText) {
    countText.textContent = `篩選後共 ${displayedStocks.length} 檔 / 全庫 50 檔`;
  }

  if (displayedStocks.length === 0) {
    body.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:30px; color:var(--text-dim);">無符合篩選條件的股票。</td></tr>`;
    return;
  }

  const html = displayedStocks.map(s => {
    const chgPct = parseChangePct(s.change);
    const chgColor = chgPct > 0 ? 'var(--accent-red)' : (chgPct < 0 ? 'var(--accent-green)' : 'var(--text-main)');
    const chgArrow = chgPct > 0 ? '▲' : (chgPct < 0 ? '▼' : '');
    const scores = s.scores || {};
    
    let badgeClass = 'score-normal';
    if (s.ai_score >= 90) badgeClass = 'score-high';
    else if (s.ai_score >= 80) badgeClass = 'score-medium';

    const getScore = (keyUtf8, keyGarbled) => scores[keyUtf8] ?? scores[keyGarbled] ?? 0;
    const details = `材:${getScore('題材', '憿峕')} 金:${getScore('資金', '鞈')} 線:${getScore('線型', '蝺𡁜')} 境:${getScore('大環境', '憭抒兛憓')} 勢:${getScore('趨勢', '頞典𨋍')}`;

    return `
      <tr class="stock-row-tick">
        <td><span class="score-badge ${badgeClass}">${s.ai_score.toFixed(1)}分</span></td>
        <td style="font-weight:700;">${s.signal}</td>
        <td class="symbol-code">${s.symbol}</td>
        <td><strong>${s.name}</strong></td>
        <td style="font-family:var(--font-mono); font-weight:800;">NT$ ${s.price.toLocaleString('zh-TW', {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
        <td style="color: ${chgColor}; font-weight:700; font-family:var(--font-mono);">${chgArrow} ${s.change}</td>
        <td><span class="pill pill-purple">${s.theme_tag}</span></td>
        <td><span class="pill pill-blue">${s.inst}</span></td>
        <td style="font-size:0.75rem; color:var(--text-dim); white-space:nowrap;">${details}</td>
        <td style="font-size:0.85rem; font-weight:600; color:var(--accent-orange);">${s.reason || "多方動能蓄積"}</td>
        <td style="text-align:center;">${generateSparklineSvg(s.history5d)}</td>
      </tr>
    `;
  }).join('');
  
  body.innerHTML = html;
}

function initMomentumControls() {
  const btnAll = document.getElementById('btn-all-momentum');
  const btnUltimate = document.getElementById('btn-ultimate-momentum');
  const btnBurst = document.getElementById('btn-burst-momentum');
  
  const buttons = [btnAll, btnUltimate, btnBurst];
  
  if (btnAll) btnAll.addEventListener('click', () => {
    buttons.forEach(b => b && b.classList.remove('active'));
    btnAll.classList.add('active');
    momentumFilter = 'all';
    renderMomentumTable();
  });
  
  if (btnUltimate) btnUltimate.addEventListener('click', () => {
    buttons.forEach(b => b && b.classList.remove('active'));
    btnUltimate.classList.add('active');
    momentumFilter = 'ultimate';
    renderMomentumTable();
  });
  
  if (btnBurst) btnBurst.addEventListener('click', () => {
    buttons.forEach(b => b && b.classList.remove('active'));
    btnBurst.classList.add('active');
    momentumFilter = 'burst';
    renderMomentumTable();
  });
}

function getSortLabel() {
  const map = {
    score: '飆股評分',
    symbol: '股票代號',
    price: '股價',
    changePct: '漲跌幅',
    volume: '成交量',
    yoy: '營收年增',
    pe: '本益比'
  };
  const dir = sortDir === 'desc' ? '↓高→低' : '↑低→高';
  return `${map[sortKey] || sortKey} ${dir}`;
}

function changePage(newPage) {
  currentPage = newPage;
  renderScreenerTable(false);
  window.scrollTo({ top: 300, behavior: 'smooth' });
}

/* ── Tab 切換 ── */
function initTabs() {
  const tabs = document.querySelectorAll('.nav-tab');
  const panes = document.querySelectorAll('.tab-pane');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-tab');
      tabs.forEach(t => t.classList.remove('active'));
      panes.forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const targetPane = document.getElementById(target);
      if (targetPane) targetPane.classList.add('active');
    });
  });
}

/* ── Charts ── */
function initCharts() {
  const ctxTaiex = document.getElementById('taiexChart');
  if (ctxTaiex) {
    taiexChart = new Chart(ctxTaiex, {
      type: 'line',
      data: {
        labels: ['2026 Q1', '2026/04', '2026/05', '2026/06', '2026/07/01', '2026/07/10', '2026/07/17'],
        datasets: [{
          label: '加權指數 (TAIEX)',
          data: [38200, 39800, 41500, 43200, 44800, 45625, 42671],
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99, 102, 241, 0.1)',
          fill: true,
          tension: 0.3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 200 },
        plugins: { legend: { labels: { color: '#9ca3af' } } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } }
        }
      }
    });
  }

  const ctxNode = document.getElementById('nodeRevenueChart');
  if (ctxNode) {
    nodeRevenueChart = new Chart(ctxNode, {
      type: 'doughnut',
      data: {
        labels: ['2奈米 (N2 - 3%)', '3奈米 (N3 - 30%)', '5奈米 (N5 - 33%)', '7奈米 (N7 - 11%)', '成熟製程 (23%)'],
        datasets: [{
          data: [3, 30, 33, 11, 23],
          backgroundColor: ['#ec4899', '#6366f1', '#10b981', '#38bdf8', '#6b7280'],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 200 },
        plugins: { legend: { position: 'right', labels: { color: '#9ca3af' } } }
      }
    });
  }
}

/* ── AI 分析師 ── */
function initAIAnalyst() {
  const form = document.getElementById('ai-form');
  const input = document.getElementById('ai-input');
  const promptBtns = document.querySelectorAll('.ai-prompt-btn');

  promptBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.getAttribute('data-query');
      if (input && q) { input.value = q; form.dispatchEvent(new Event('submit')); }
    });
  });

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const prompt = input.value.trim();
      if (!prompt) return;
      input.value = '';
      appendAIMessage('user', prompt);
      const aiContentDiv = appendAIMessage('ai', '正在連線至本地端 Qwen 2.5 進行分析...');
      const targetApi = window.location.protocol + '//' + window.location.hostname + ':11434/api/generate';
      try {
        const res = await fetch(targetApi, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: 'qwen2.5:7b',
            prompt: `你是一位頂尖的台股 6,000+ 全市場量化選股專家。請基於 2026 年最新台股行情(加權指數42,671點、台積電2,290元)，用繁體中文專業分析：「${prompt}」`,
            stream: true
          })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        aiContentDiv.innerHTML = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value);
          for (const line of chunk.split('\n').filter(l => l.trim())) {
            try { const parsed = JSON.parse(line); if (parsed.response) aiContentDiv.textContent += parsed.response; } catch (e) {}
          }
        }
      } catch (err) {
        aiContentDiv.innerHTML = `⚠️ 無法連線至 AI 伺服器: ${err.message}`;
      }
    });
  }
}

function appendAIMessage(role, text) {
  const container = document.getElementById('ai-messages');
  const msgDiv = document.createElement('div');
  msgDiv.className = `msg ${role === 'user' ? 'user-msg' : 'ai-msg'}`;
  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🤖';
  const content = document.createElement('div');
  content.className = 'msg-content';
  content.innerHTML = text;
  msgDiv.appendChild(avatar);
  msgDiv.appendChild(content);
  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
  return content;
}

function analyzeStockTarget(symbol, name, price) {
  const tabs = document.querySelectorAll('.nav-tab');
  if (tabs[4]) tabs[4].click();
  const input = document.getElementById('ai-input');
  const form = document.getElementById('ai-form');
  if (input && form) {
    input.value = `請針對台股 ${name} (${symbol}，最新股價 NT$ ${price}) 提供籌碼法人鎖碼狀態、短線支撐買點、目標價評價與爆發利多分析。`;
    form.dispatchEvent(new Event('submit'));
  }
}
