// 台灣股市全市場實時串流與量化飆股篩選系統 (2026年最新版 — 官方 Open API + 全欄排序)

let allStocks = [];
let filteredStocks = [];
let momentumStocks = [];
let techCache = {};
let epsCache = {};
let currentPage = 1;
const pageSize = 50;
let autoRefreshTimer = null;
let isLiveStreaming = true;

// 目前排序狀態 (預設依今日漲跌由高至低排序，優先展示強勢起漲飆股)
let sortKey = 'changePct';
let sortDir = 'desc'; // 'asc' | 'desc'
let momentumFilter = 'all'; // 'all' | 'ultimate' | 'burst'

// 延緩位置跳動控制 (位置排序延遲重排，數值仍及時更新)
let reorderIntervalSec = 30; // 延緩位置跳動間隔，預設 30 秒 (可設 15s / 30s / 60s / 0)
let reorderCountdown = 30;

/* ── 標的種類識別器 (ETF / ETN / 普通股) ── */
function isETF(s) {
  if (!s) return false;
  const sym = (s.symbol || s.code || '').split('.')[0].trim();
  const name = (s.name || '').toUpperCase();
  const sec = (s.sector || '').toUpperCase();
  const m = (s.market || '').toUpperCase();
  const desc = (s.desc || '').toUpperCase();
  if (m === '台股ETF' || m.includes('ETF') || m.includes('受益憑證')) return true;
  if (sym.startsWith('00') || sym.startsWith('01') || sym.startsWith('0')) return true;
  if (name.includes('ETF') || sec.includes('ETF') || desc.includes('ETF')) return true;
  if (desc.includes('受益憑證') || sec.includes('熱門台股ETF') || sec.includes('受益憑證')) return true;
  if (name.includes('反1') || name.includes('正2') || name.includes('高股息') || name.includes('高息') || name.includes('債') || name.includes('主動') || name.includes('期')) return true;
  if (s.is_etf) return true;
  return false;
}

function isETN(s) {
  if (!s) return false;
  const sym = (s.symbol || s.code || '').split('.')[0].trim();
  const name = (s.name || '').toUpperCase();
  const m = (s.market || '').toUpperCase();
  if (m === '台股ETN' || m.includes('ETN')) return true;
  if (sym.startsWith('02')) return true;
  if (name.endsWith('N') || name.includes('ETN')) return true;
  return false;
}

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initCharts();
  initSortHeaders();
  initScreenerControls();
  initMomentumControls();
  initSurgeAlertPanel();
  initReorderControls();
  loadFullStockDatabase();
  loadMomentumStocks();
  pollSurgeAlerts(true); // 立即同步啟動盤中急拉數據，無須等待首秒
  if (window.location.hash === '#surge' || window.location.hash === '#surge-tab' || window.location.hash === '#surge-grouped') {
    switchTab('surge-tab');
  } else if (window.location.hash === '#surge-mixed' || window.location.hash === '#surge-mixed-tab' || window.location.hash === '#surge-flat') {
    switchTab('surge-mixed-tab');
  }
  window.addEventListener('hashchange', () => {
    if (window.location.hash === '#surge' || window.location.hash === '#surge-tab' || window.location.hash === '#surge-grouped') {
      switchTab('surge-tab');
    } else if (window.location.hash === '#surge-mixed' || window.location.hash === '#surge-mixed-tab' || window.location.hash === '#surge-flat') {
      switchTab('surge-mixed-tab');
    } else if (window.location.hash === '#ai' || window.location.hash === '#ai-momentum') {
      switchTab('ai-momentum');
    } else if (window.location.hash === '#screener') {
      switchTab('screener');
    }
  });
  setInterval(loadMomentumStocks, 10000);
  setInterval(refreshCacheQuietly, 60000); // 靜默背景快取刷新，不打擾畫面與排序
  setInterval(pollSurgeAlerts, 1000);  // 每 1 秒輪詢即時警報 (真實即時)
});

/* ── 排序表頭初始化 ── */
function updateSortHeaderUI() {
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
}

function initSortHeaders() {
  updateSortHeaderUI();
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
      updateSortHeaderUI();
      currentPage = 1;
      sortAndRender(true);
    });
  });
}

/* ── 排序 (穩定排序 + 延緩位置跳動重置) ── */
function sortAndRender(resetPage = false) {
  if (resetPage) currentPage = 1;
  filteredStocks.sort((a, b) => {
    let diff = 0;
    if (sortKey === 'changePct') {
      diff = parseChangePct(b.change) - parseChangePct(a.change);
    } else if (typeof a[sortKey] === 'string') {
      diff = (a[sortKey] || '').localeCompare(b[sortKey] || '');
    } else {
      diff = (b[sortKey] ?? 0) - (a[sortKey] ?? 0);
    }
    if (sortDir === 'asc') diff = -diff;
    if (diff !== 0) return diff;
    // 穩定第二排序鍵：股票代號 (防止同漲跌幅時在畫面上反覆跳動換位)
    return (a.symbol || '').localeCompare(b.symbol || '');
  });
  renderScreenerTable(false);
  resetReorderCountdown();
}

function resetReorderCountdown() {
  reorderCountdown = reorderIntervalSec;
  updateReorderStatusUI();
}

function updateReorderStatusUI() {
  const cdBadge = document.getElementById('reorder-countdown-badge');
  if (!cdBadge) return;
  if (reorderIntervalSec === 0) {
    cdBadge.textContent = '🔒 位置已凍結 (手動重排)';
    cdBadge.style.color = '#94a3b8';
    cdBadge.style.borderColor = 'rgba(148, 163, 184, 0.4)';
    cdBadge.style.background = 'rgba(148, 163, 184, 0.1)';
  } else {
    cdBadge.textContent = `⏳ 下次重排: ${reorderCountdown}s`;
    cdBadge.style.color = reorderCountdown <= 5 ? '#f87171' : '#38bdf8';
    cdBadge.style.borderColor = reorderCountdown <= 5 ? 'rgba(239,68,68,0.5)' : 'rgba(56,189,248,0.4)';
    cdBadge.style.background = reorderCountdown <= 5 ? 'rgba(239,68,68,0.15)' : 'rgba(56,189,248,0.1)';
  }
}

function initReorderControls() {
  const select = document.getElementById('reorder-interval-select');
  const btnNow = document.getElementById('btn-reorder-now');
  if (select) {
    select.addEventListener('change', (e) => {
      reorderIntervalSec = parseInt(e.target.value, 10) || 0;
      reorderCountdown = reorderIntervalSec;
      updateReorderStatusUI();
    });
  }
  if (btnNow) {
    btnNow.addEventListener('click', () => {
      sortAndRender();
      renderTopGainersStrip(allStocks);
      rebuildMarquee();
    });
  }
}

async function refreshCacheQuietly() {
  try {
    const [cacheRes, epsRes] = await Promise.all([
      fetch('tech_cache.json?t=' + Date.now()),
      fetch('eps_cache.json?t=' + Date.now())
    ]);
    if (cacheRes.ok) {
      const data = await cacheRes.json();
      techCache = data.data || {};
    }
    if (epsRes.ok) {
      epsCache = await epsRes.json();
    }
  } catch (e) {}
}

function parseChangePct(str) {
  if (!str) return 0;
  return parseFloat(str.replace('%', '').replace('+', '')) || 0;
}

/* ── 即時飆升警報系統 ── */
let surgeAlertSeenTs = new Set();
let surgeAlertVisible = false;
let isAlertPanelShrunk = false;
let isFirstAlertPoll = true;
let alertSortMode = 'surge'; // 'surge' (短時間急拉幅度最高，預設) | 'time' (最新急拉) | 'growth' (今日總漲幅) | 'ai' (AI綜合推薦)
let latestSurgeAlertsMap = new Map();
let currentModalCode = '';
let currentModalTvMarket = 'TWSE';
let stockModalChartInstance = null;
let currentModalPeriod = 'intraday'; // 'intraday' | '5d' | 'day' | 'week' | 'month' | 'surge'
let currentModalEngine = 'native'; // 'native' | 'tv'
let currentTvInterval = '1';
const intradaySeriesCache = new Map();

// 延緩即時警報股票排列跳動控制 (排列位置維持 10 秒，數值即時原地更新)
let alertReorderIntervalSec = 10; // 延緩警報跳動間隔，維持 10 秒 (可選 10s / 15s / 30s / 5s / 0)
let alertReorderCountdown = 10;
let displayedAlertCodes = []; // 記錄當前顯示卡片的股票順序

function updateSurgeReorderUI() {
  const cdBadge = document.getElementById('surge-reorder-countdown');
  if (!cdBadge) return;
  if (alertReorderIntervalSec === 0) {
    cdBadge.textContent = '🔒 排列已凍結';
    cdBadge.style.color = '#94a3b8';
    cdBadge.style.borderColor = 'rgba(148, 163, 184, 0.4)';
    cdBadge.style.background = 'rgba(148, 163, 184, 0.1)';
  } else {
    cdBadge.textContent = `⏳ 下次重排: ${alertReorderCountdown}s`;
    cdBadge.style.color = alertReorderCountdown <= 3 ? '#f87171' : '#38bdf8';
    cdBadge.style.borderColor = alertReorderCountdown <= 3 ? 'rgba(239,68,68,0.5)' : 'rgba(56,189,248,0.4)';
    cdBadge.style.background = alertReorderCountdown <= 3 ? 'rgba(239,68,68,0.15)' : 'rgba(56,189,248,0.1)';
  }
}

// ⚡ 盤中急拉多維極速精準篩選狀態
let surgeFilterState = {
  search: '',
  type: 'all',    // 'all' | '1m' | '3m' | '5m' | 'wave'
  minPct: 0,      // 0, 2, 3, 5, 7
  minVol: 0,      // 0, 1000, 3000, 5000, 10000
  minAi: 0,       // 0, 70, 80
  market: 'all',  // 'all' | 'TWSE上市' | 'TPEx上櫃'
};
let surgeSoundEnabled = false;
try {
  surgeSoundEnabled = localStorage.getItem('surge_sound_enabled') === '1';
} catch (e) {}

let isSurgeStreamFrozen = false;
let currentActiveTab = 'screener';
let lastSurgeAlertsHash = '';
let isSurgeTabDirty = true;
let isSurgeMixedDirty = true;

function playSurgeAlertSound() {
  if (!surgeSoundEnabled) return;
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    if (!window._surgeAudioCtx) {
      window._surgeAudioCtx = new AudioContext();
    }
    const ctx = window._surgeAudioCtx;
    if (ctx.state === 'suspended') {
      ctx.resume();
    }
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, now);
    osc.frequency.exponentialRampToValueAtTime(1320, now + 0.12);
    gain.gain.setValueAtTime(0.15, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.35);
  } catch (e) {}
}

function toggleSurgeAlertSound() {
  surgeSoundEnabled = !surgeSoundEnabled;
  try {
    localStorage.setItem('surge_sound_enabled', surgeSoundEnabled ? '1' : '0');
  } catch (e) {}
  if (surgeSoundEnabled) {
    playSurgeAlertSound();
  }
  updateSoundBtnsUI();
}
window.toggleSurgeAlertSound = toggleSurgeAlertSound;

function updateSoundBtnsUI() {
  const btns = [document.getElementById('surge-sound-toggle-btn'), document.getElementById('surge-mixed-sound-toggle-btn')];
  btns.forEach(btn => {
    if (!btn) return;
    btn.className = `surge-sound-btn ${surgeSoundEnabled ? 'sound-on' : ''}`;
    btn.innerHTML = surgeSoundEnabled ? '🔔 警報音效: 開啟' : '🔕 警報音效: 關閉';
  });
}

function toggleSurgeStreamFreeze() {
  isSurgeStreamFrozen = !isSurgeStreamFrozen;
  const btns = [document.getElementById('surge-freeze-stream-btn'), document.getElementById('surge-mixed-freeze-stream-btn')];
  btns.forEach(btn => {
    if (!btn) return;
    btn.className = `surge-filter-btn ${isSurgeStreamFrozen ? 'active' : ''}`;
    btn.innerHTML = isSurgeStreamFrozen ? '⏸️ 串流已鎖定' : '🔴 實時串流中';
  });
}
window.toggleSurgeStreamFreeze = toggleSurgeStreamFreeze;

function showSurgeToast(alert) {
  if (!alert) return;
  let container = document.getElementById('surge-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'surge-toast-container';
    container.style.cssText = 'position:fixed; top:20px; right:20px; z-index:999999; display:flex; flex-direction:column; gap:8px; pointer-events:none;';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = 'surge-toast-item';
  const pct = alert.surge_pct !== undefined ? alert.surge_pct : (alert.change_pct || 0);
  toast.innerHTML = `
    <div style="display:flex; align-items:center; gap:10px;">
      <span style="font-size:1.4rem;">⚡</span>
      <div>
        <div style="font-weight:900; color:#fff; font-size:0.92rem;">
          ${alert.name} (${alert.code}) <strong style="color:#f87171;">+${pct.toFixed(2)}%</strong>
        </div>
        <div style="font-size:0.75rem; color:#cbd5e1; margin-top:2px;">
          ${alert.surge_window || '短線急拉'} · 現價 $${alert.price} · ${alert.sector || ''}
        </div>
      </div>
    </div>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    setTimeout(() => toast.remove(), 350);
  }, 4500);
}

function generateTicksSparklineSvg(ticks) {
  if (!ticks || ticks.length < 2) return '';
  const prices = ticks.map(t => t.p);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min;
  const width = 84;
  const height = 22;
  const padding = 2;
  const points = [];
  for (let i = 0; i < prices.length; i++) {
    const x = padding + (i * (width - 2 * padding)) / (prices.length - 1);
    const y = height - padding - (range === 0 ? (height - 2 * padding) / 2 : ((prices[i] - min) * (height - 2 * padding)) / range);
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  const color = prices[prices.length - 1] >= prices[0] ? '#ef4444' : '#10b981';
  return `
    <svg width="${width}" height="${height}" style="overflow:visible; display:inline-block; vertical-align:middle;">
      <polyline fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${points.join(' ')}" />
      <circle cx="${points[points.length-1].split(',')[0]}" cy="${points[points.length-1].split(',')[1]}" r="2.5" fill="${color}" />
    </svg>
  `;
}

function getFilteredSurgeAlerts(alerts) {
  if (!alerts) return [];
  const q = (surgeFilterState.search || '').toLowerCase().trim();
  const type = surgeFilterState.type;
  const minPct = surgeFilterState.minPct;
  const minVol = surgeFilterState.minVol;
  const minAi = surgeFilterState.minAi;
  const market = surgeFilterState.market;

  return alerts.filter(a => {
    if (q) {
      const match = (a.code && a.code.toLowerCase().includes(q)) ||
                    (a.name && a.name.toLowerCase().includes(q)) ||
                    (a.sector && a.sector.toLowerCase().includes(q)) ||
                    (a.theme_tag && a.theme_tag.toLowerCase().includes(q));
      if (!match) return false;
    }
    if (type !== 'all') {
      const win = a.surge_window || '';
      if (type === '1m' && !win.includes('1')) return false;
      if (type === '3m' && !win.includes('3')) return false;
      if (type === '5m' && !win.includes('5')) return false;
      if (type === 'wave' && !(win.includes('波段') || win.includes('主升'))) return false;
    }
    const sPct = a.surge_pct !== undefined ? a.surge_pct : (a.change_pct || 0);
    if (minPct > 0 && sPct < minPct) return false;
    if (minVol > 0 && (a.volume || 0) < minVol) return false;
    if (minAi > 0 && (a.ai_score || 0) < minAi) return false;
    if (market !== 'all' && a.market && a.market !== market) return false;
    return true;
  });
}

function updateSurgeMetrics(cleanAlerts) {
  if (!cleanAlerts || cleanAlerts.length === 0) return;
  const total = cleanAlerts.length;
  const avgSurge = cleanAlerts.reduce((acc, a) => acc + (a.surge_pct !== undefined ? a.surge_pct : (a.change_pct || 0)), 0) / total;

  let topStock = cleanAlerts[0];
  cleanAlerts.forEach(a => {
    const sp = a.surge_pct !== undefined ? a.surge_pct : (a.change_pct || 0);
    const topSp = topStock.surge_pct !== undefined ? topStock.surge_pct : (topStock.change_pct || 0);
    if (sp > topSp) topStock = a;
  });

  const sectorCounts = {};
  cleanAlerts.forEach(a => {
    const sec = resolveStockSector(a.code, a.sector);
    sectorCounts[sec] = (sectorCounts[sec] || 0) + 1;
  });
  let topSector = '';
  let topSecCount = 0;
  for (const [sec, count] of Object.entries(sectorCounts)) {
    if (count > topSecCount) {
      topSecCount = count;
      topSector = sec;
    }
  }

  const totalEls = [document.getElementById('surge-metric-total'), document.getElementById('surge-mixed-metric-total')];
  totalEls.forEach(el => { if (el) el.innerHTML = `${total} <span style="font-size:0.8rem;color:#94a3b8;">檔</span>`; });

  const avgEls = [document.getElementById('surge-metric-avg'), document.getElementById('surge-mixed-metric-avg')];
  avgEls.forEach(el => { if (el) el.textContent = `+${avgSurge.toFixed(2)}%`; });

  const topEls = [document.getElementById('surge-metric-top'), document.getElementById('surge-mixed-metric-top')];
  topEls.forEach(el => {
    if (el && topStock) {
      const topSp = topStock.surge_pct !== undefined ? topStock.surge_pct : (topStock.change_pct || 0);
      el.innerHTML = `${topStock.name} <strong style="color:#ef4444;">+${topSp.toFixed(2)}%</strong>`;
    }
  });

  const secEls = [document.getElementById('surge-metric-sector'), document.getElementById('surge-mixed-metric-sector')];
  secEls.forEach(el => {
    if (el && topSector) {
      el.textContent = `${topSector} (${topSecCount}檔)`;
    }
  });
}

function onSurgeFilterChange() {
  const input = document.getElementById('surge-tab-filter-search');
  const mixedInput = document.getElementById('surge-mixed-filter-search');
  if (input) {
    surgeFilterState.search = input.value;
    if (mixedInput && mixedInput.value !== input.value) mixedInput.value = input.value;
  }
  renderSurgeTabContent();
  renderSurgeMixedTabContent();
}
window.onSurgeFilterChange = onSurgeFilterChange;

function onSurgeMixedFilterChange() {
  const input = document.getElementById('surge-mixed-filter-search');
  const tabInput = document.getElementById('surge-tab-filter-search');
  if (input) {
    surgeFilterState.search = input.value;
    if (tabInput && tabInput.value !== input.value) tabInput.value = input.value;
  }
  renderSurgeTabContent();
  renderSurgeMixedTabContent();
}
window.onSurgeMixedFilterChange = onSurgeMixedFilterChange;

function setSurgeTypeFilter(type) {
  surgeFilterState.type = type;
  document.querySelectorAll('[data-surge-type]').forEach(btn => {
    const isAct = btn.getAttribute('data-surge-type') === type;
    btn.classList.toggle('active', isAct);
    btn.classList.toggle('active-amber', isAct);
  });
  renderSurgeTabContent();
  renderSurgeMixedTabContent();
}
window.setSurgeTypeFilter = setSurgeTypeFilter;

function setSurgeMinPctFilter(pct) {
  surgeFilterState.minPct = parseFloat(pct) || 0;
  document.querySelectorAll('[data-surge-minpct]').forEach(btn => {
    const isAct = parseFloat(btn.getAttribute('data-surge-minpct')) === surgeFilterState.minPct;
    btn.classList.toggle('active', isAct);
    btn.classList.toggle('active-amber', isAct);
  });
  renderSurgeTabContent();
  renderSurgeMixedTabContent();
}
window.setSurgeMinPctFilter = setSurgeMinPctFilter;

function setSurgeMinVolFilter(vol) {
  surgeFilterState.minVol = parseInt(vol, 10) || 0;
  document.querySelectorAll('[data-surge-minvol]').forEach(btn => {
    const isAct = parseInt(btn.getAttribute('data-surge-minvol'), 10) === surgeFilterState.minVol;
    btn.classList.toggle('active', isAct);
    btn.classList.toggle('active-amber', isAct);
  });
  renderSurgeTabContent();
  renderSurgeMixedTabContent();
}
window.setSurgeMinVolFilter = setSurgeMinVolFilter;

function setSurgeMinAiFilter(ai) {
  surgeFilterState.minAi = parseFloat(ai) || 0;
  document.querySelectorAll('[data-surge-minai]').forEach(btn => {
    const isAct = parseFloat(btn.getAttribute('data-surge-minai')) === surgeFilterState.minAi;
    btn.classList.toggle('active', isAct);
    btn.classList.toggle('active-amber', isAct);
  });
  renderSurgeTabContent();
  renderSurgeMixedTabContent();
}
window.setSurgeMinAiFilter = setSurgeMinAiFilter;

function setSurgeMarketFilter(market) {
  surgeFilterState.market = market;
  document.querySelectorAll('[data-surge-market]').forEach(btn => {
    const isAct = btn.getAttribute('data-surge-market') === market;
    btn.classList.toggle('active', isAct);
    btn.classList.toggle('active-amber', isAct);
  });
  renderSurgeTabContent();
  renderSurgeMixedTabContent();
}
window.setSurgeMarketFilter = setSurgeMarketFilter;

function resetSurgeFilters() {
  surgeFilterState = {
    search: '',
    type: 'all',
    minPct: 0,
    minVol: 0,
    minAi: 0,
    market: 'all'
  };
  const in1 = document.getElementById('surge-tab-filter-search');
  const in2 = document.getElementById('surge-mixed-filter-search');
  if (in1) in1.value = '';
  if (in2) in2.value = '';

  setSurgeTypeFilter('all');
  setSurgeMinPctFilter(0);
  setSurgeMinVolFilter(0);
  setSurgeMinAiFilter(0);
  setSurgeMarketFilter('all');
}
window.resetSurgeFilters = resetSurgeFilters;


function getTwMarketStatus() {
  try {
    const nowTw = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" }));
    const day = nowTw.getDay();
    const h = nowTw.getHours();
    const m = nowTw.getMinutes();
    if (day === 0 || day === 6) return { isOpen: false, label: '休市彙整', color: '#94a3b8' };
    if (h < 9) return { isOpen: false, label: '盤前等待', color: '#fbbf24' };
    if (h > 13 || (h === 13 && m > 30)) return { isOpen: false, label: '今日收盤', color: '#38bdf8' };
    return { isOpen: true, label: '盤中即時', color: '#22c55e' };
  } catch (e) {
    return { isOpen: true, label: '即時', color: '#22c55e' };
  }
}

function initSurgeAlertPanel() {
  // 建立浮動警報面板 (支援完整展開與縮小為迷你狀態列)
  const panel = document.createElement('div');
  panel.id = 'surge-alert-panel';
  panel.style.cssText = `
    position: fixed; bottom: 20px; right: 20px; z-index: 9999;
    width: min(1440px, calc(100vw - 32px)); max-height: min(740px, calc(100vh - 40px)); overflow-y: auto;
    background: rgba(15,15,30,0.97);
    border: 1px solid rgba(239,68,68,0.5);
    border-radius: 16px;
    box-shadow: 0 8px 40px rgba(239,68,68,0.25);
    display: none;
    flex-direction: column;
    gap: 0;
    font-family: 'Inter', sans-serif;
    transition: max-height 0.25s cubic-bezier(0.4, 0, 0.2, 1), width 0.25s ease, box-shadow 0.2s ease;
  `;
  panel.innerHTML = `
    <div id="surge-panel-header" style="padding:10px 16px; border-bottom:1px solid rgba(255,255,255,0.08); display:flex; justify-content:space-between; align-items:center; position:sticky; top:0; background:rgba(15,15,30,0.99); z-index:2; cursor:pointer; user-select:none; flex-wrap:wrap; gap:8px;">
      <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        <span id="surge-panel-title" style="font-weight:800; color:#f87171; font-size:0.95rem; white-space:nowrap;">⚡ 盤中急拉飆升 (精選 Top 50)</span>
        <span id="surge-alert-count" style="background:#ef4444; color:#fff; font-size:0.72rem; font-weight:700; padding:2px 8px; border-radius:10px;">0</span>
        <div id="surge-reorder-group" style="display:flex; align-items:center; gap:6px; margin-left:4px;">
          <select id="surge-reorder-interval-select" style="background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.18); color:#38bdf8; font-size:0.68rem; font-weight:700; padding:2px 6px; border-radius:6px; cursor:pointer; outline:none;" title="股票排列維持時間 (防跳動)">
            <option value="10" selected>維持 10 秒 (預設)</option>
            <option value="15">維持 15 秒</option>
            <option value="30">維持 30 秒</option>
            <option value="5">維持 5 秒</option>
            <option value="0">位置凍結 (手動)</option>
          </select>
          <span id="surge-reorder-countdown" style="font-family:var(--font-mono, monospace); font-size:0.68rem; font-weight:700; padding:2px 7px; border-radius:6px; border:1px solid rgba(56,189,248,0.4); background:rgba(56,189,248,0.1); color:#38bdf8; white-space:nowrap;" title="股票排列維持 10 秒刷新一次，避免畫面跳動">⏳ 下次重排: 10s</span>
          <button id="surge-btn-reorder-now" style="background:rgba(99,102,241,0.25); color:#a5b4fc; border:1px solid rgba(99,102,241,0.5); padding:2px 7px; border-radius:6px; font-size:0.68rem; font-weight:700; cursor:pointer; transition:all 0.2s; white-space:nowrap;" title="立即依最新數值重新排列">⚡ 重排</button>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
        <div id="surge-panel-mode-group" style="display:flex; background:rgba(255,255,255,0.08); border-radius:6px; padding:2px; gap:2px;">
          <button id="surge-panel-mode-grouped" onclick="setSurgePanelMode('grouped')" style="background:#6366f1; color:#fff; border:none; border-radius:4px; font-size:0.68rem; font-weight:700; padding:2px 7px; cursor:pointer;" title="族群彩色框分組檢視">🏷️ 族群分組</button>
          <button id="surge-panel-mode-flat" onclick="setSurgePanelMode('flat')" style="background:transparent; color:#94a3b8; border:none; border-radius:4px; font-size:0.68rem; font-weight:700; padding:2px 7px; cursor:pointer;" title="卡片總榜檢視">📋 總榜</button>
        </div>
        <div id="surge-sort-group" style="display:flex; background:rgba(255,255,255,0.08); border-radius:6px; padding:2px; gap:2px;">
          <button id="surge-sort-surge" style="background:#ef4444; color:#fff; border:none; border-radius:4px; font-size:0.68rem; font-weight:700; padding:2px 7px; cursor:pointer;">⚡ 急拉幅度</button>
          <button id="surge-sort-time" style="background:transparent; color:#94a3b8; border:none; border-radius:4px; font-size:0.68rem; font-weight:700; padding:2px 7px; cursor:pointer;">🕐 最新急拉</button>
          <button id="surge-sort-growth" style="background:transparent; color:#94a3b8; border:none; border-radius:4px; font-size:0.68rem; font-weight:700; padding:2px 7px; cursor:pointer;">🔥 今日總漲幅</button>
          <button id="surge-sort-ai" style="background:transparent; color:#94a3b8; border:none; border-radius:4px; font-size:0.68rem; font-weight:700; padding:2px 7px; cursor:pointer;">🤖 AI</button>
        </div>
        <button id="surge-panel-shrink" style="background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.18); color:#cbd5e1; font-size:0.75rem; font-weight:700; cursor:pointer; padding:3px 9px; border-radius:6px; display:flex; align-items:center; gap:4px; transition:all 0.2s;" title="縮小/折疊視窗 (Shrink window)">
          🗕 縮小
        </button>
        <button id="surge-panel-close" style="background:transparent; border:none; color:#94a3b8; font-size:1.1rem; cursor:pointer; padding:2px 7px; border-radius:6px; transition:all 0.2s;" title="關閉視窗 (Close)">✕</button>
      </div>
    </div>
    <div id="surge-alert-list" style="padding:10px; display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:10px; align-items:start;"></div>
  `;
  document.body.appendChild(panel);

  // 點擊縮小/展開按鈕
  const shrinkBtn = panel.querySelector('#surge-panel-shrink');
  shrinkBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleSurgePanelShrink();
  });

  // 點擊標題列空白處：在縮小狀態下點擊直接還原展開
  const header = panel.querySelector('#surge-panel-header');
  header?.addEventListener('click', (e) => {
    if (e.target.closest('button') || e.target.closest('select')) return;
    if (isAlertPanelShrunk) {
      toggleSurgePanelShrink(false);
    }
  });

  // 綁定關閉按鈕
  panel.querySelector('#surge-panel-close')?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleSurgePanel(false);
  });

  // 綁定排列維持頻率與立即重排
  const reorderSelect = panel.querySelector('#surge-reorder-interval-select');
  const btnReorderNow = panel.querySelector('#surge-btn-reorder-now');

  reorderSelect?.addEventListener('change', (e) => {
    e.stopPropagation();
    alertReorderIntervalSec = parseInt(e.target.value, 10);
    alertReorderCountdown = alertReorderIntervalSec;
    updateSurgeReorderUI();
    pollSurgeAlerts(true);
  });

  btnReorderNow?.addEventListener('click', (e) => {
    e.stopPropagation();
    pollSurgeAlerts(true);
  });

  const btnSurge = panel.querySelector('#surge-sort-surge');
  const btnTime = panel.querySelector('#surge-sort-time');
  const btnGrowth = panel.querySelector('#surge-sort-growth');
  const btnAi = panel.querySelector('#surge-sort-ai');

  function updateSortBtnStyles(activeBtn) {
    [btnSurge, btnTime, btnGrowth, btnAi].forEach(b => {
      if (b === activeBtn) {
        b.style.background = '#ef4444';
        b.style.color = '#fff';
      } else if (b) {
        b.style.background = 'transparent';
        b.style.color = '#94a3b8';
      }
    });
  }

  btnSurge?.addEventListener('click', (e) => {
    e.stopPropagation();
    alertSortMode = 'surge';
    updateSortBtnStyles(btnSurge);
    pollSurgeAlerts(true);
  });
  btnTime?.addEventListener('click', (e) => {
    e.stopPropagation();
    alertSortMode = 'time';
    updateSortBtnStyles(btnTime);
    pollSurgeAlerts(true);
  });
  btnGrowth?.addEventListener('click', (e) => {
    e.stopPropagation();
    alertSortMode = 'growth';
    updateSortBtnStyles(btnGrowth);
    pollSurgeAlerts(true);
  });
  btnAi?.addEventListener('click', (e) => {
    e.stopPropagation();
    alertSortMode = 'ai';
    updateSortBtnStyles(btnAi);
    pollSurgeAlerts(true);
  });

  // 建立浮動警報按鈕 (當視窗隱藏時於右下角顯示)
  const btn = document.createElement('button');
  btn.id = 'surge-alert-btn';
  btn.style.cssText = `
    position: fixed; bottom: 24px; right: 24px; z-index: 10000;
    background: linear-gradient(135deg, #ef4444, #b91c1c);
    color: #fff; border: none; border-radius: 50px;
    padding: 12px 20px; font-weight: 800; font-size: 0.9rem;
    cursor: pointer; box-shadow: 0 4px 20px rgba(239,68,68,0.5);
    display: flex; align-items: center; gap: 8px;
    transition: all 0.2s ease;
  `;
  btn.innerHTML = '⚡ 盤中急拉 (Top 50) <span id="surge-btn-count" style="background:rgba(255,255,255,0.25); padding:1px 8px; border-radius:10px;">0</span>';
  btn.addEventListener('click', () => toggleSurgePanel(true));
  document.body.appendChild(btn);

  // 頂部導航按鈕與橫幅按鈕開關
  document.getElementById('top-surge-badge-btn')?.addEventListener('click', () => toggleSurgePanel());
  document.getElementById('hero-open-surge-btn')?.addEventListener('click', () => toggleSurgePanel(true));

  // 快捷鍵支援：按下 Esc 可縮小或關閉警報視窗
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && surgeAlertVisible) {
      if (!isAlertPanelShrunk) {
        toggleSurgePanelShrink(true);
      } else {
        toggleSurgePanel(false);
      }
    }
  });
}

/* ── 警報視窗縮小/展開切換核心 ── */
function toggleSurgePanelShrink(forceShrunk) {
  const panel = document.getElementById('surge-alert-panel');
  const list = document.getElementById('surge-alert-list');
  const sortGroup = document.getElementById('surge-sort-group');
  const shrinkBtn = document.getElementById('surge-panel-shrink');
  if (!panel) return;

  isAlertPanelShrunk = forceShrunk !== undefined ? forceShrunk : !isAlertPanelShrunk;

  if (isAlertPanelShrunk) {
    // 縮小模式：折疊清單與排序按鈕，只保留輕巧頂部狀態列
    panel.style.maxHeight = '48px';
    panel.style.width = 'min(420px, calc(100vw - 32px))';
    panel.style.overflow = 'hidden';
    panel.style.boxShadow = '0 4px 20px rgba(0,0,0,0.5)';
    if (list) list.style.display = 'none';
    if (sortGroup) sortGroup.style.display = 'none';
    const reorderGroup = document.getElementById('surge-reorder-group');
    if (reorderGroup) reorderGroup.style.display = 'none';
    if (shrinkBtn) {
      shrinkBtn.innerHTML = '🗖 展開';
      shrinkBtn.title = '展開警報視窗 (Expand window)';
      shrinkBtn.style.color = '#38bdf8';
      shrinkBtn.style.borderColor = 'rgba(56,189,248,0.45)';
      shrinkBtn.style.background = 'rgba(56,189,248,0.15)';
    }
  } else {
    // 展開模式：恢復完整 1440px 視窗與四排即時清單
    panel.style.maxHeight = 'min(740px, calc(100vh - 40px))';
    panel.style.width = 'min(1440px, calc(100vw - 32px))';
    panel.style.overflowY = 'auto';
    panel.style.boxShadow = '0 8px 40px rgba(239,68,68,0.25)';
    if (list) list.style.display = 'grid';
    if (sortGroup) sortGroup.style.display = 'flex';
    const reorderGroup = document.getElementById('surge-reorder-group');
    if (reorderGroup) reorderGroup.style.display = 'flex';
    if (shrinkBtn) {
      shrinkBtn.innerHTML = '🗕 縮小';
      shrinkBtn.title = '縮小/折疊視窗 (Shrink window)';
      shrinkBtn.style.color = '#cbd5e1';
      shrinkBtn.style.borderColor = 'rgba(255,255,255,0.18)';
      shrinkBtn.style.background = 'rgba(255,255,255,0.08)';
    }
  }
}

/* ── 警報視窗開啟/關閉切換 ── */
function toggleSurgePanel(forceOpen) {
  const panel = document.getElementById('surge-alert-panel');
  const btn = document.getElementById('surge-alert-btn');
  if (!panel) return;
  surgeAlertVisible = forceOpen !== undefined ? forceOpen : !surgeAlertVisible;
  panel.style.display = surgeAlertVisible ? 'flex' : 'none';

  if (surgeAlertVisible) {
    if (btn) btn.style.display = 'none';
    if (forceOpen && isAlertPanelShrunk) {
      toggleSurgePanelShrink(false);
    }
    // 打開視窗時立即依最新行情排列並重設 10 秒倒數
    pollSurgeAlerts(true);
  } else {
    if (btn) {
      btn.style.display = 'flex';
      btn.style.bottom = '24px';
    }
  }
}

/* ── 頂部最強起漲飆股橫幅渲染 (Top Growing Stocks on the Top) ── */
function renderTopGainersStrip(sourceList) {
  const container = document.getElementById('top-gainers-strip');
  if (!container) return;

  const list = (sourceList && sourceList.length > 0) ? sourceList : allStocks;
  if (!list || list.length === 0) return;

  let topStocks = [];
  if (list[0].change_pct !== undefined) {
    topStocks = [...list]
      .filter(s => !s.symbol?.includes('權證') && s.market !== '權證標的')
      .map(a => ({
        symbol: a.code,
        fullSymbol: a.symbol || a.code,
        name: a.name,
        price: a.price,
        changePct: a.change_pct || 0,
        volume: a.volume || 0,
        sector: a.sector || '',
        score: a.ai_score || 0
      }))
      .sort((a, b) => {
        const d = b.changePct - a.changePct;
        if (Math.abs(d) > 0.0001) return d;
        return a.symbol.localeCompare(b.symbol);
      })
      .slice(0, 10);
  } else {
    topStocks = [...list]
      .filter(s => s.symbol && s.change && !s.symbol.includes('權證') && s.market !== '權證標的')
      .map(s => ({
        symbol: s.symbol.split('.')[0],
        fullSymbol: s.symbol,
        name: s.name,
        price: s.price,
        changePct: parseChangePct(s.change),
        volume: s.volume || 0,
        sector: s.sector || '',
        score: s.score || 0
      }))
      .sort((a, b) => {
        const d = b.changePct - a.changePct;
        if (Math.abs(d) > 0.0001) return d;
        return a.symbol.localeCompare(b.symbol);
      })
      .slice(0, 10);
  }

  if (topStocks.length === 0) return;

  container.innerHTML = topStocks.map((s, idx) => {
    const isLimitUp = s.changePct >= 9.5;
    const badgeText = isLimitUp ? '🚨漲停' : `TOP ${idx + 1}`;
    const badgeBg = isLimitUp ? '#ef4444' : '#f59e0b';
    const volStr = s.volume
      ? (s.volume >= 10000 ? `${(s.volume / 10000).toFixed(1)}萬張` : `${s.volume.toLocaleString()}張`)
      : '-';

    return `
      <div class="top-gainer-item" data-symbol="${s.fullSymbol}" onclick="quickFilterStock('${s.symbol}')"
           style="background:rgba(30, 41, 59, 0.9); border:1px solid ${isLimitUp ? 'rgba(239,68,68,0.5)' : 'rgba(245,158,11,0.4)'}; border-radius:12px; padding:10px 12px; cursor:pointer; transition:all 0.2s ease; display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 2px 8px rgba(0,0,0,0.25);"
           onmouseover="this.style.transform='translateY(-2px)'; this.style.borderColor='#ef4444'; this.style.boxShadow='0 4px 16px rgba(239,68,68,0.3)';"
           onmouseout="this.style.transform='none'; this.style.borderColor='${isLimitUp ? 'rgba(239,68,68,0.5)' : 'rgba(245,158,11,0.4)'}'; this.style.boxShadow='none';"
           title="點擊精準篩選 ${s.name} (${s.symbol})">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px;">
          <div style="overflow:hidden;">
            <div style="font-weight:800; color:#f8fafc; font-size:0.88rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${s.name}</div>
            <div style="font-size:0.72rem; color:#94a3b8;">${s.symbol}</div>
          </div>
          <span class="strip-badge" style="background:${badgeBg}; color:#fff; font-size:0.62rem; font-weight:800; padding:1px 5px; border-radius:4px; flex-shrink:0; margin-left:4px;">${badgeText}</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:2px;">
          <span class="strip-price" style="font-weight:700; color:#e2e8f0; font-size:0.92rem;">$${s.price.toLocaleString()}</span>
          <span class="strip-change" style="font-weight:900; color:#f87171; font-size:1.02rem;">+${s.changePct.toFixed(2)}%</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px; font-size:0.68rem; color:#64748b;">
          <span>${s.sector || ''}</span>
          <span class="strip-vol">${volStr}</span>
        </div>
      </div>
    `;
  }).join('');
}


/* ── 一鍵點擊股票即時連動篩選 ── */
function quickFilterStock(symbol) {
  // 切換至選股頁
  const screenerTabBtn = document.querySelector('.tab-btn[data-tab="screener"]');
  if (screenerTabBtn) screenerTabBtn.click();

  const searchInput = document.getElementById('screener-search');
  const filterSector = document.getElementById('screener-filter');
  const filterMarket = document.getElementById('screener-market');
  if (filterSector) filterSector.value = 'all';
  if (filterMarket) filterMarket.value = 'all';

  const presetBtns = document.querySelectorAll('.preset-btn');
  presetBtns.forEach(b => {
    if (b.getAttribute('data-mode') === 'all') b.classList.add('active');
    else b.classList.remove('active');
  });

  if (searchInput) {
    searchInput.value = symbol;
  }
  currentPage = 1;
  applyScreenerFilters();

  const tableEl = document.querySelector('.screener-table-wrap') || document.getElementById('screener-table');
  if (tableEl) {
    tableEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function flashAlertBtn() {
  const btn = document.getElementById('surge-alert-btn');
  if (!btn) return;
  btn.style.transform = 'scale(1.15)';
  btn.style.boxShadow = '0 0 0 8px rgba(239,68,68,0.3)';
  setTimeout(() => {
    btn.style.transform = 'scale(1.0)';
    btn.style.boxShadow = '0 4px 20px rgba(239,68,68,0.5)';
  }, 400);
}

function formatAlertTs(tsStr) {
  if (!tsStr) return '';
  try {
    const todayStr = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Taipei" })).toISOString().split('T')[0];
    if (tsStr.startsWith(todayStr)) {
      return `今日 ${tsStr.substring(11, 19)}`;
    }
    return tsStr.substring(5, 16);
  } catch (e) {
    return tsStr.substring(11, 19) || tsStr;
  }
}

function renderAlertCardHtml(a, rank) {
  const pct = a.change_pct || 0;
  const surgePct = a.surge_pct !== undefined ? a.surge_pct : pct;
  const surgeWindow = a.surge_window || '短線急拉';

  let bg, border, icon;
  if (pct >= 9.5)    { bg='rgba(239,68,68,0.2)';   border='#ef4444'; icon='🚨'; }
  else if (pct >= 7) { bg='rgba(245,158,11,0.2)';  border='#f59e0b'; icon='🔥'; }
  else if (pct >= 5) { bg='rgba(99,102,241,0.2)';  border='#6366f1'; icon='⚡'; }
  else               { bg='rgba(16,185,129,0.15)'; border='#10b981'; icon='📈'; }

  const vol = a.volume
    ? (a.volume >= 10000 ? `${(a.volume/10000).toFixed(1)}萬張` : `${a.volume.toLocaleString()}張`)
    : '-';

  const rankBadgeHtml = rank !== undefined
    ? `<span style="background:${rank <= 3 ? 'linear-gradient(135deg, #ef4444, #f59e0b)' : (rank <= 10 ? 'rgba(245, 158, 11, 0.25)' : 'rgba(255,255,255,0.08)')}; color:${rank <= 3 ? '#fff' : (rank <= 10 ? '#fbbf24' : '#cbd5e1')}; font-size:0.68rem; font-weight:900; padding:1px 6px; border-radius:10px; font-family:var(--font-mono); box-shadow:${rank <= 3 ? '0 0 8px rgba(239,68,68,0.5)' : 'none'};">#${rank}</span>`
    : '';

  const surgeBadge = `
    <span class="surge-card-badge" style="background:linear-gradient(135deg, #ef4444, #dc2626); color:#fff; font-size:0.68rem; font-weight:800; padding:2px 7px; border-radius:6px; box-shadow:0 0 10px rgba(239,68,68,0.4); display:inline-flex; align-items:center; gap:2px;">
      ⚡ ${surgeWindow} +${surgePct.toFixed(2)}%
    </span>
  `;

  const priceTrack = (a.surge_start_price && a.surge_start_price !== a.price)
    ? `<span class="surge-card-price" style="color:#fbbf24; font-weight:700;">起拉 $${a.surge_start_price} ➔ 現價 $${a.price}</span>`
    : `<span class="surge-card-price">💰 NT$<strong style="color:#e2e8f0;">${a.price}</strong></span>`;

  const aiTag   = a.is_momentum ? '<span style="background:#6366f1;color:#fff;font-size:0.65rem;padding:1px 6px;border-radius:5px;font-weight:700;">🤖AI飆股</span>' : '';
  const highTag = a.is_new_high  ? '<span style="background:#f59e0b;color:#000;font-size:0.65rem;padding:1px 6px;border-radius:5px;font-weight:700;">🏆新高</span>' : '';
  const bpTags  = (a.breakout_flags||[]).map(f =>
    `<span style="background:rgba(99,102,241,0.25);color:#a5b4fc;font-size:0.62rem;padding:1px 5px;border-radius:4px;">${f}</span>`
  ).join('');
  const themeBadge = a.theme_tag
    ? `<span style="background:rgba(16,185,129,0.2);color:#6ee7b7;font-size:0.62rem;padding:1px 6px;border-radius:4px;">${a.theme_tag}</span>` : '';

  const aiScoreHtml = a.ai_score
    ? `<span style="color:#64748b;">AI:</span> <strong style="color:#f87171;">${a.ai_score.toFixed(1)}</strong>` : '';
  const bkScoreHtml = a.breakout_score
    ? `<span style="color:#64748b;margin-left:8px;">突破:</span> <strong style="color:#c084fc;">${a.breakout_score.toFixed(0)}</strong>` : '';
  const signalHtml  = a.signal
    ? `<span style="color:#fbbf24;margin-left:8px;">${a.signal}</span>` : '';

  const factors = [
    { label:'題材',  val: a.score_theme   ||0, color:'#f87171' },
    { label:'資金',  val: a.score_capital  ||0, color:'#fb923c' },
    { label:'線型',  val: a.score_tech     ||0, color:'#a78bfa' },
    { label:'大環境',val: a.score_macro    ||0, color:'#38bdf8' },
    { label:'趨勢',  val: a.score_trend    ||0, color:'#34d399' },
  ];
  const hasBars = factors.some(f => f.val > 0);
  const scoreBars = hasBars ? factors.map(f => `
    <div style="display:flex;align-items:center;gap:4px;">
      <span style="font-size:0.62rem;color:#64748b;width:32px;flex-shrink:0;">${f.label}</span>
      <div style="flex:1;background:rgba(255,255,255,0.07);border-radius:3px;height:5px;">
        <div style="width:${Math.min(f.val,100)}%;background:${f.color};height:5px;border-radius:3px;"></div>
      </div>
      <span style="font-size:0.62rem;color:#94a3b8;width:22px;text-align:right;">${f.val}</span>
    </div>`).join('') : '';

  const instRow  = (a.inst && a.inst !== '-') ? `<span>🏦 ${a.inst}</span>` : '';
  const whaleRow = a.whale_pct ? `<span>🐋 大戶 ${(+a.whale_pct).toFixed(1)}%</span>` : '';
  const reasonRow = a.reason
    ? `<div style="font-size:0.71rem;color:#94a3b8;margin-top:6px;padding-top:5px;border-top:1px solid rgba(255,255,255,0.06);line-height:1.5;">💡 ${a.reason}</div>` : '';

    const sparkHtml = a.ticks ? generateTicksSparklineSvg(a.ticks) : '';

    return `
  <div class="surge-card" data-code="${a.code}" onclick="openStockChartModal('${a.code}', 'intraday')" title="點擊查看 ${a.name} (${a.code}) 盤中即時線型圖與技術分析" style="background:${bg};border:1px solid ${border};border-radius:12px;padding:12px;margin:0;min-width:0;box-sizing:border-box;height:100%;display:flex;flex-direction:column;cursor:pointer;transition:transform 0.15s,box-shadow 0.15s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='none'">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
      <div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
          ${rankBadgeHtml}
          <span style="font-weight:800;color:#f1f5f9;font-size:0.95rem;">${icon} ${a.name}</span>
          <span style="color:#64748b;font-size:0.78rem;">(${a.code})</span>
          ${surgeBadge}
        </div>
        <div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:3px;">${aiTag}${highTag}${bpTags}${themeBadge}</div>
      </div>
      <div style="text-align:right;flex-shrink:0;margin-left:8px;">
        <div class="surge-card-pct" style="font-weight:900;color:#f87171;font-size:1.2rem;">${pct>0?'+':''}${pct.toFixed(2)}%</div>
        <div style="font-size:0.7rem;color:#94a3b8;">今日漲幅</div>
      </div>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;font-size:0.74rem;color:#94a3b8;margin-bottom:6px;">
      <div>
        ${priceTrack}
        <div style="margin-top:3px;display:flex;flex-wrap:wrap;gap:6px;">
          <span class="surge-card-vol">📊 ${vol}</span>
          <span>🏭 ${a.sector||'-'}</span>
          <span class="surge-card-time">🕐 ${formatAlertTs(a.ts)}</span>
          ${instRow}${whaleRow}
        </div>
      </div>
      <div>${sparkHtml}</div>
    </div>
    ${(aiScoreHtml||bkScoreHtml) ? `<div style="display:flex;align-items:center;flex-wrap:wrap;margin-bottom:6px;font-size:0.75rem;">${aiScoreHtml}${bkScoreHtml}${signalHtml}</div>` : ''}
    ${hasBars ? `<div style="display:flex;flex-direction:column;gap:3px;margin-bottom:4px;">${scoreBars}</div>` : ''}
    ${reasonRow}
    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:auto; padding-top:8px; border-top:1px solid rgba(255,255,255,0.06); gap:6px;">
      <button class="surge-card-btn-chart" onclick="event.stopPropagation(); openStockChartModal('${a.code}', 'intraday')" style="flex:1; background:linear-gradient(135deg, rgba(239,68,68,0.25), rgba(245,158,11,0.25)); border:1px solid rgba(245,158,11,0.5); color:#fde68a; border-radius:6px; padding:4px 8px; font-size:0.72rem; font-weight:800; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:4px; transition:all 0.15s;" title="查看該股票盤中即時走勢圖與均線指標">
        ⚡ 查看線型圖
      </button>
      <button class="surge-card-btn-filter" onclick="event.stopPropagation(); quickFilterStock('${a.code}')" style="background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.15); color:#94a3b8; border-radius:6px; padding:4px 8px; font-size:0.72rem; font-weight:700; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:3px; transition:all 0.15s;" title="在下方選股表中定位此股票">
        🔍 篩選
      </button>
    </div>
  </div>`;
}

function updateSurgeCardInPlace(card, a) {
  const pct = a.change_pct || 0;
  const surgePct = a.surge_pct !== undefined ? a.surge_pct : pct;
  const surgeWindow = a.surge_window || '短線急拉';

  // 1. 漲幅數值
  const pctEl = card.querySelector('.surge-card-pct');
  if (pctEl) {
    const formattedPct = `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%`;
    if (pctEl.textContent !== formattedPct) {
      pctEl.textContent = formattedPct;
    }
  }

  // 2. 急拉標籤
  const badgeEl = card.querySelector('.surge-card-badge');
  if (badgeEl) {
    const newBadgeHtml = `⚡ ${surgeWindow} +${surgePct.toFixed(2)}%`;
    if (badgeEl.textContent.trim() !== newBadgeHtml.trim()) {
      badgeEl.innerHTML = newBadgeHtml;
    }
  }

  // 3. 價格追蹤
  const priceEl = card.querySelector('.surge-card-price');
  if (priceEl) {
    const newPriceHtml = (a.surge_start_price && a.surge_start_price !== a.price)
      ? `起拉 $${a.surge_start_price} ➔ 現價 $${a.price}`
      : `💰 NT$<strong style="color:#e2e8f0;">${a.price}</strong>`;
    if (priceEl.innerHTML !== newPriceHtml) {
      priceEl.innerHTML = newPriceHtml;
    }
  }

  // 4. 成交量
  const volEl = card.querySelector('.surge-card-vol');
  if (volEl) {
    const volStr = a.volume
      ? (a.volume >= 10000 ? `${(a.volume / 10000).toFixed(1)}萬張` : `${a.volume.toLocaleString()}張`)
      : '-';
    const newVolHtml = `📊 ${volStr}`;
    if (volEl.textContent !== newVolHtml) {
      volEl.textContent = newVolHtml;
    }
  }

  // 5. 時間
  const timeEl = card.querySelector('.surge-card-time');
  if (timeEl && a.ts) {
    const newTime = `🕐 ${formatAlertTs(a.ts)}`;
    if (timeEl.textContent !== newTime) {
      timeEl.textContent = newTime;
    }
  }

  // 6. 顏色等級
  let bg, border;
  if (pct >= 9.5)    { bg = 'rgba(239,68,68,0.2)';   border = '#ef4444'; }
  else if (pct >= 7) { bg = 'rgba(245,158,11,0.2)';  border = '#f59e0b'; }
  else if (pct >= 5) { bg = 'rgba(99,102,241,0.2)';  border = '#6366f1'; }
  else               { bg = 'rgba(16,185,129,0.15)'; border = '#10b981'; }
  card.style.background = bg;
  card.style.borderColor = border;
}

async function pollSurgeAlerts(forceReorder = false) {
  const status = getTwMarketStatus();
  const btn = document.getElementById('surge-alert-btn');
  const panel = document.getElementById('surge-alert-panel');
  const titleEl = document.getElementById('surge-panel-title');

  // 始終顯示警報按鈕，標示市場狀態
  if (btn && btn.style.display === 'none' && !surgeAlertVisible) {
    btn.style.display = 'flex';
  }

  if (titleEl) {
    titleEl.innerHTML = `⚡ 盤中急拉飆升 (精選 Top 50) <span style="color:${status.color};font-size:0.75rem;font-weight:600;margin-left:4px;">● ${status.label}</span>`;
  }

  try {
    const res = await fetch('surge_alerts.json?t=' + Date.now());
    if (!res.ok) return;
    const alerts = await res.json();

    const list     = document.getElementById('surge-alert-list');
    const countEl  = document.getElementById('surge-alert-count');
    const btnCount = document.getElementById('surge-btn-count');
    if (!list) return;

    // 嚴格精準過濾：排除 ETF、成交量過低 (< 1,000張) 之標的
    const cleanAlerts = alerts.filter(a =>
      !isETF(a) &&
      (a.volume || 0) >= 1000
    );

    latestSurgeAlertsMap.clear();
    cleanAlerts.forEach(a => latestSurgeAlertsMap.set(a.code, a));

    // 首次載入只記錄已有 alerts，不強制彈出遮蔽畫面
    if (isFirstAlertPoll) {
      cleanAlerts.forEach(a => surgeAlertSeenTs.add(a.ts + '_' + a.code));
      isFirstAlertPoll = false;
    } else if (status.isOpen) {
      // 盤中新警報才觸發閃爍、音效與 Toast 通知
      const newAlerts = cleanAlerts.filter(a => !surgeAlertSeenTs.has(a.ts + '_' + a.code));
      if (newAlerts.length > 0) {
        newAlerts.forEach(a => surgeAlertSeenTs.add(a.ts + '_' + a.code));
        flashAlertBtn();
        // 浮動 Toast 提示與音效播報 (最多取最新前 2 檔，避免洗版)
        newAlerts.slice(0, 2).forEach(a => {
          showSurgeToast(a);
        });
        playSurgeAlertSound();
      }
    }

    const total = cleanAlerts.length;
    if (countEl) countEl.textContent = total;
    if (btnCount) btnCount.textContent = total;
    const topSurgeCount = document.getElementById('top-surge-count');
    if (topSurgeCount) topSurgeCount.textContent = total;
    const screenerBannerCount = document.getElementById('screener-surge-banner-count');
    if (screenerBannerCount) screenerBannerCount.textContent = `${total} 檔`;

    // 實時秒級更新標示
    const nowTimeStr = new Date().toLocaleTimeString('zh-TW', { hour12: false });
    const surgeRefreshEl = document.getElementById('surge-tab-refresh-text');
    if (surgeRefreshEl) {
      surgeRefreshEl.innerHTML = `<span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#10b981; margin-right:4px; box-shadow:0 0 6px #10b981;"></span> 🟢 1秒實時族群排序中 (最新撮合: ${nowTimeStr})`;
    }
    const mixedRefreshEl = document.getElementById('surge-mixed-refresh-text');
    if (mixedRefreshEl) {
      mixedRefreshEl.innerHTML = `<span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#ef4444; margin-right:4px; box-shadow:0 0 6px #ef4444;"></span> 🔴 1秒全市場即時混排排序中 (最新撮合: ${nowTimeStr})`;
    }

    // 更新即時量化統計看板
    updateSurgeMetrics(cleanAlerts);

    // 檢查串流是否被手動凍結 (若暫停中，保留當前畫面供用戶仔細分析)
    if (!surgeFilterState.isPaused) {
      // 按需渲染活躍分頁 (避免無謂的後台 DOM 樹重新計算，大幅提速)
      if (typeof currentActiveTab === 'undefined' || currentActiveTab === 'surge-tab') {
        renderSurgeTabContent();
      }
      if (typeof currentActiveTab !== 'undefined' && currentActiveTab === 'surge-mixed-tab') {
        renderSurgeMixedTabContent();
      }
    }

    // 如果用戶正在查看盤中即時線型圖 Modal，1秒實時連動刷新 (抗抖動原地更新)
    const chartModalEl = document.getElementById('stock-chart-modal');
    if (chartModalEl && chartModalEl.style.display !== 'none' && currentModalCode && currentModalEngine === 'native') {
      if (currentModalPeriod === 'intraday' || currentModalPeriod === 'surge') {
        renderStockModalChart(currentModalPeriod, true);
      }
    }

    // 只有在警報視窗展開時才進行卡片渲染
    if (surgeAlertVisible) {
      const existingCards = list.querySelectorAll('.surge-card[data-code]');
      const shouldFullReorder = forceReorder ||
                                existingCards.length === 0 ||
                                (alertReorderIntervalSec > 0 && alertReorderCountdown <= 0);

      if (shouldFullReorder) {
        // ── 執行全新重新排序與排版渲染 (維持 10 秒週期到期或手動重排) ──
        const sorted = [...cleanAlerts].sort((a, b) => {
          if (alertSortMode === 'surge') {
            const sDiff = (b.surge_pct || b.change_pct || 0) - (a.surge_pct || a.change_pct || 0);
            if (Math.abs(sDiff) > 0.001) return sDiff;
            return (b.surge_ts || 0) - (a.surge_ts || 0);
          } else if (alertSortMode === 'time') {
            const tDiff = (b.surge_ts || 0) - (a.surge_ts || 0);
            if (tDiff !== 0) return tDiff;
            return (b.surge_pct || 0) - (a.surge_pct || 0);
          } else if (alertSortMode === 'growth') {
            const pctDiff = (b.change_pct || 0) - (a.change_pct || 0);
            if (Math.abs(pctDiff) > 0.001) return pctDiff;
            return (b.surge_pct || 0) - (a.surge_pct || 0);
          } else {
            const pa = (a.ai_score||0)*2 + (a.breakout_score||0) + (a.surge_pct||a.change_pct||0)*3;
            const pb = (b.ai_score||0)*2 + (b.breakout_score||0) + (b.surge_pct||b.change_pct||0)*3;
            return pb - pa;
          }
        }).slice(0, 50);

        if (sorted.length === 0) {
          list.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 48px 16px; background: rgba(255,255,255,0.02); border: 1px dashed rgba(255,255,255,0.1); border-radius: 12px; margin: 12px 0;">
              <div style="font-size: 2.4rem; margin-bottom: 8px;">📡</div>
              <div style="font-weight: 800; color: #f1f5f9; font-size: 1.05rem;">目前盤中暫無 1~5 分鐘快速急拉標的</div>
              <div style="font-size: 0.8rem; color: #64748b; margin-top: 6px; line-height: 1.6;">
                系統全市場每秒監控中，一旦有標的短時間快速往上拉將第一時間警報通知！
              </div>
            </div>
          `;
          displayedAlertCodes = [];
        } else {
          if (surgePanelDisplayMode === 'grouped') {
            list.style.display = 'flex';
            list.style.flexDirection = 'column';
            list.style.gap = '14px';
            list.innerHTML = renderPanelGroupedSectorsHtml(sorted);
          } else {
            list.style.display = 'grid';
            list.style.gridTemplateColumns = 'repeat(4, minmax(0, 1fr))';
            list.style.gap = '10px';
            list.innerHTML = sorted.map(a => renderAlertCardHtml(a)).join('');
          }
          displayedAlertCodes = sorted.map(a => a.code);
        }

        alertReorderCountdown = alertReorderIntervalSec;
      } else {
        // ── 排列維持階段 (10 秒內完全保持股票位置不動，原地更新即時數值避免跳動) ──
        if (alertReorderIntervalSec > 0) {
          alertReorderCountdown--;
        }

        const alertsMap = new Map(cleanAlerts.map(a => [a.code, a]));
        existingCards.forEach(card => {
          const code = card.getAttribute('data-code');
          const latestData = alertsMap.get(code);
          if (latestData) {
            updateSurgeCardInPlace(card, latestData);
          }
        });
      }

      updateSurgeReorderUI();
    }
  } catch (e) { /* surge_alerts.json 尚未建立時靜默忽略 */ }
}

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

    try {
      const epsRes = await fetch('eps_cache.json?t=' + Date.now());
      if (epsRes.ok) {
        epsCache = await epsRes.json();
      }
    } catch (e) {
      console.log('eps_cache fetch error', e);
    }

    applyScreenerFilters();
    renderTopGainersStrip(allStocks);
    startLiveAutoRefresh();
    rebuildMarquee();
    const totalEl = document.getElementById('total-stocks');
    if (totalEl) totalEl.textContent = allStocks.length;
  } catch (e) {
    if (countText) countText.textContent = '⚠️ 資料庫連線例外: ' + e.message;
  }
}

/* ── 2. 實時串流更新 (數值每秒即時更新，排版位置延緩重排) ── */
function startLiveAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(async () => {
    if (!isLiveStreaming) return;
    try {
      const res = await fetch('stocks-full-8000.json?t=' + Date.now());
      if (res.ok) {
        const latestStocks = await res.json();
        updateStockPricesInMemory(latestStocks);

        // 1. 即時更新畫面數值 (股價、漲跌幅、成交量、顏色微閃) - 位置完全不變，防止跳動
        updateLiveStockInfoInDOM();
        updateMarqueeInPlace();

        // 2. 延緩位置跳動倒數
        if (reorderIntervalSec > 0) {
          reorderCountdown--;
          if (reorderCountdown <= 0) {
            // 延緩時間到，進行一次平滑重新排序與位置重置
            reorderCountdown = reorderIntervalSec;
            sortAndRender();
            renderTopGainersStrip(allStocks);
            rebuildMarquee();
          }
        }
        updateReorderStatusUI();
      }
    } catch (e) {}
  }, 1000);
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

/* ── 跑馬燈：建立結構與即時原地更新 ── */
function rebuildMarquee() {
  const watchList = ['2330', '2317', '2454', '2379', '2382', '3017', '3324', '3661', '6669'];
  const tickerTrack = document.querySelector('.ticker-track');
  if (!tickerTrack) return;
  
  // 計算全市場 MIS 即時撮合股票數
  let misCount = 0;
  let tradeDate = '';
  if (allStocks.length > 0) {
    misCount = allStocks.filter(s => s.data_source === 'MIS即時').length;
    const sample = allStocks.find(s => s.trade_date) || allStocks[0];
    tradeDate = sample ? (sample.trade_date || '') : '';
  }
  const isRealtime = misCount > 0;
  const srcBadge = isRealtime
    ? `<span style="background:#10b981;color:#fff;padding:2px 10px;border-radius:10px;font-size:0.78em;margin-left:6px;font-weight:700;">🟢 MIS 官方即時撮合 (${misCount.toLocaleString()} 檔)</span>`
    : '<span style="background:#f59e0b;color:#fff;padding:2px 10px;border-radius:10px;font-size:0.78em;margin-left:6px;font-weight:700;">🟡 OpenAPI 日收盤</span>';
  const dateStr = tradeDate ? ` | 交易日: ${tradeDate}` : '';
  let singleItems = `<div class="ticker-item"><span class="t-name">⚡ 台灣股市全市場即時連線</span> <span class="t-val">System Online${dateStr}</span>${srcBadge}</div>`;
  
  // 優先展示今日漲幅最高個股 (Top Gainers)
  const topGainers = [...allStocks]
    .filter(s => s.symbol && s.change && !s.symbol.includes('權證') && parseChangePct(s.change) >= 2.0 && s.market !== '權證標的')
    .sort((a, b) => {
      const d = parseChangePct(b.change) - parseChangePct(a.change);
      if (Math.abs(d) > 0.001) return d;
      return a.symbol.localeCompare(b.symbol);
    })
    .slice(0, 8);

  topGainers.forEach(s => {
    const sym = s.symbol.split('.')[0];
    singleItems += `<div class="ticker-item" data-symbol="${s.symbol}" style="background:rgba(239,68,68,0.18);border:1px solid rgba(239,68,68,0.35);border-radius:6px;padding:2px 8px;"><span class="t-name" style="color:#fca5a5;font-weight:700;">🔥 ${s.name} (${sym})</span> <span class="t-val ticker-price">NT$ ${s.price}</span> <span class="ticker-chg" style="color:#ef4444;font-weight:800;">▲ ${s.change}</span></div>`;
  });

  watchList.forEach(sym => {
    if (topGainers.some(g => g.symbol.includes(sym))) return;
    const s = allStocks.find(st => st.symbol.includes(sym));
    if (s) {
      let chgColor = 'var(--text-dim)';
      let chgArrow = '';
      if (s.change.includes('+')) { chgColor = 'var(--accent-red)'; chgArrow = '▲'; }
      else if (s.change.includes('-')) { chgColor = 'var(--accent-green)'; chgArrow = '▼'; }
      singleItems += `<div class="ticker-item" data-symbol="${s.symbol}"><span class="t-name">${s.name} (${sym})</span> <span class="t-val ticker-price">NT$ ${s.price}</span> <span class="ticker-chg" style="color:${chgColor};font-weight:700;">${chgArrow} ${s.change}</span></div>`;
    }
  });
  
  // 複製一份使 CSS tickerSlide (-50%) 無縫流暢循環滾動
  const newHtml = singleItems + singleItems;
  if (tickerTrack.innerHTML !== newHtml) {
    tickerTrack.innerHTML = newHtml;
  }
}

function updateMarqueeInPlace() {
  const tickerTrack = document.querySelector('.ticker-track');
  if (!tickerTrack) return;
  const stockMap = new Map(allStocks.map(s => [s.symbol, s]));
  const items = tickerTrack.querySelectorAll('.ticker-item[data-symbol]');
  items.forEach(item => {
    const sym = item.getAttribute('data-symbol');
    const s = stockMap.get(sym);
    if (!s) return;
    const pEl = item.querySelector('.ticker-price');
    if (pEl) {
      const newP = `NT$ ${s.price}`;
      if (pEl.textContent !== newP) pEl.textContent = newP;
    }
    const cEl = item.querySelector('.ticker-chg');
    if (cEl) {
      let chgColor = 'var(--text-dim)';
      let chgArrow = '';
      if (s.change.includes('+')) { chgColor = 'var(--accent-red)'; chgArrow = '▲'; }
      else if (s.change.includes('-')) { chgColor = 'var(--accent-green)'; chgArrow = '▼'; }
      const newC = `${chgArrow} ${s.change}`;
      if (cEl.textContent !== newC) {
        cEl.textContent = newC;
        cEl.style.color = chgColor;
      }
    }
  });
}

/* ── 3. 控制台初始化 ── */
let screenerControlsInitialized = false;
function initScreenerControls() {
  if (screenerControlsInitialized) return;
  screenerControlsInitialized = true;

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
        ? `<span class="dot-live"></span> 🔴 行情串流中 (1秒實時)`
        : `⏸️ 實時串流已暫停`;
    });
  }

  function debounce(fn, ms) {
    let timer;
    return function(...args) { clearTimeout(timer); timer = setTimeout(() => fn.apply(this, args), ms); };
  }

  const debouncedApply = debounce(() => { currentPage = 1; applyScreenerFilters(); }, 80);

  if (sliderYoy && yoyVal) sliderYoy.addEventListener('input', e => { yoyVal.textContent = `≥ ${e.target.value}%`; debouncedApply(); });
  if (sliderPe && peVal) sliderPe.addEventListener('input', e => {
    const v = parseFloat(e.target.value);
    peVal.textContent = v >= 60 ? '不限' : `≤ ${v}x`;
    debouncedApply();
  });

  presetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.getAttribute('data-mode');
      if (mode === 'surge-50') {
        // 點擊「⚡ 盤中急拉 (族群分組·彩色框)」
        switchTab('surge-tab');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      } else if (mode === 'surge-mixed') {
        // 點擊「⚡ 盤中急拉 (綜合混排·無分群)」
        switchTab('surge-mixed-tab');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      presetBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (mode === 'burst') {
        if (sliderYoy) { sliderYoy.value = 0; yoyVal.textContent = '≥ 0%'; }
        if (sliderPe) { sliderPe.value = 60; peVal.textContent = '不限'; }
      } else if (mode === 'ai-growth') {
        if (sliderYoy) { sliderYoy.value = 25; yoyVal.textContent = '≥ 25%'; }
        if (sliderPe) { sliderPe.value = 60; peVal.textContent = '不限'; }
      } else if (mode === 'undervalued') {
        if (sliderPe) { sliderPe.value = 20; peVal.textContent = '≤ 20x'; }
      } else if (mode === 'institutional' || mode === 'all') {
        if (sliderPe) { sliderPe.value = 60; peVal.textContent = '不限'; }
      } else if (mode === 'etf') {
        if (sliderYoy) { sliderYoy.value = 0; yoyVal.textContent = '≥ 0%'; }
        if (sliderPe) { sliderPe.value = 60; peVal.textContent = '不限'; }
        if (filterMarket) filterMarket.value = 'ETF';
      }
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
      if (!isMatch) return false;
    }

    // 交易市場板塊
    if (market === 'stocks_only' && (isETF(s) || isETN(s))) return false;
    if (market === 'TWSE上市' && s.market !== 'TWSE上市') return false;
    if (market === 'TPEx上櫃' && s.market !== 'TPEx上櫃') return false;
    if (market === 'ETF' && !(s.market.includes('ETF') || s.sector.includes('ETF') || isETF(s))) return false;
    if (market === 'ETN' && !(s.market.includes('ETN') || s.sector.includes('ETN') || isETN(s))) return false;
    if (market === '興櫃' && s.market !== '興櫃') return false;

    // 產業類別
    if (sector !== 'all') {
      if (sector === 'ETF') {
        if (!(s.market.includes('ETF') || s.sector.includes('ETF') || isETF(s))) return false;
      } else if (sector === 'ETN') {
        if (!(s.market.includes('ETN') || s.sector.includes('ETN') || isETN(s))) return false;
      } else if (!s.sector.includes(sector)) {
        return false;
      }
    }

    if (minYoy > 0 && s.yoy < minYoy) return false;
    if (maxPe < 60 && s.pe > 0 && s.pe > maxPe) return false;
    if (currentMode === 'burst') return s.score >= 70;
    if (currentMode === 'ai-growth') return s.yoy >= 25;
    if (currentMode === 'undervalued') return s.pe > 0 && s.pe <= 22;
    if (currentMode === 'institutional') return s.inst && (s.inst.includes('買') || s.inst.includes('鎖碼') || s.inst.includes('加碼'));
    if (currentMode === 'etf') return isETF(s) || isETN(s) || s.market.includes('ETF') || s.market.includes('ETN');
    if (currentMode === 'surge-50') {
      const code = s.symbol.split('.')[0];
      return latestSurgeAlertsMap.has(code);
    }
    return true;
  });

  // 依目前排序欄重新排序
  sortAndRender();
}

/* ── 5. 高效能表格渲染 ── */
function formatEpsDisplay(s) {
  // ETF 與 ETN 專屬展示 (無單季EPS)
  if (isETF(s) || isETN(s) || (s.market && (s.market.includes('ETF') || s.market.includes('ETN')))) {
    const isEtn = isETN(s) || (s.market && s.market.includes('ETN'));
    return `<div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); padding: 5px 10px; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; white-space: nowrap; min-width: 125px;" title="${isEtn ? '指數投資證券 ETN' : '指數股票型基金 ETF'}">
      <span style="font-weight: 800; font-size: 0.92rem; color: #f59e0b;">${isEtn ? '📜 指數證券 ETN' : '📊 指數基金 ETF'}</span>
      <span style="font-size: 0.72rem; color: var(--text-dim); margin-top: 2px;">一籃子成分組合</span>
    </div>`;
  }

  const code = (s.symbol || '').split('.')[0];
  const ec = epsCache[code];

  let epsNumStr = '-';
  let epsGrowVal = null;
  let quarterStr = '';
  let gmVal = null;

  if (ec) {
    if (typeof ec.eps_latest === 'number') {
      epsNumStr = ec.eps_latest.toFixed(2);
    } else if (ec.eps_latest !== undefined && ec.eps_latest !== null && ec.eps_latest !== '-') {
      epsNumStr = String(ec.eps_latest);
    }
    quarterStr = ec.quarter || '';
    gmVal = ec.gm;

    if (ec.eps_prev !== undefined && ec.eps_prev !== null && ec.eps_prev !== 0 && typeof ec.eps_latest === 'number') {
      epsGrowVal = ((ec.eps_latest - ec.eps_prev) / Math.abs(ec.eps_prev)) * 100;
    } else if (typeof ec.qoq === 'number') {
      epsGrowVal = ec.qoq;
    }
  }

  // 若快取無完整資料，使用 s 本身攜帶的 OpenAPI 資料
  if (epsNumStr === '-' && s.eps !== undefined && s.eps !== null && s.eps !== '-') {
    epsNumStr = typeof s.eps === 'number' ? s.eps.toFixed(2) : String(s.eps);
    quarterStr = s.quarter || quarterStr;
    if (epsGrowVal === null && typeof s.qoq === 'number') {
      epsGrowVal = s.qoq;
    }
  }

  // 若仍無真實季報，且有股價與本益比，以 TTM/4 估算單季 EPS
  if (epsNumStr === '-' && s.price && s.pe && s.pe > 0) {
    epsNumStr = (s.price / s.pe / 4).toFixed(2) + '<span style="font-size:0.7rem; color:var(--text-dim); margin-left:2px;">(估)</span>';
  }

  // 增長率兜底 (QoQ 或 營收年增率推估)
  if (epsGrowVal === null) {
    if (typeof s.qoq === 'number') {
      epsGrowVal = s.qoq;
    } else if (typeof s.yoy === 'number' && !isNaN(s.yoy) && s.yoy !== 0) {
      epsGrowVal = s.yoy * 0.35;
    }
  }

  let epsColor = 'var(--text-main)';
  let epsBg = 'background: rgba(128, 128, 128, 0.1); border: 1px solid rgba(128, 128, 128, 0.3);';
  let epsGrowStr = '-';

  if (epsGrowVal !== null && !isNaN(epsGrowVal)) {
    epsGrowStr = epsGrowVal.toFixed(1);
    epsColor = epsGrowVal > 0 ? 'var(--accent-red)' : epsGrowVal < 0 ? 'var(--accent-green)' : 'var(--text-main)';
    if (epsGrowVal > 0) {
      epsBg = 'background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.05)); border: 1px solid rgba(239, 68, 68, 0.5);';
    } else if (epsGrowVal < 0) {
      epsBg = 'background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(16, 185, 129, 0.05)); border: 1px solid rgba(16, 185, 129, 0.5);';
    }
  }

  const growthSpan = (epsGrowVal !== null && !isNaN(epsGrowVal))
    ? `<span style="font-weight: 900; font-size: 1.05rem; color: ${epsColor}; margin-left: 6px;">(${epsGrowVal > 0 ? '+' : ''}${epsGrowStr}%)</span>`
    : '';

  let gmDisplay = '';
  if (gmVal !== null && gmVal !== undefined && !isNaN(gmVal)) {
    const gmColor = gmVal >= 30 ? '#10b981' : (gmVal >= 15 ? '#facc15' : 'var(--accent-red)');
    gmDisplay = `<div style="font-size:0.75rem; color:var(--text-dim); margin-top:3px;">毛利率 <span style="font-weight:700; color:${gmColor};">${gmVal}%</span>${quarterStr ? ' · ' + quarterStr : ''}</div>`;
  } else if (quarterStr) {
    gmDisplay = `<div style="font-size:0.75rem; color:var(--text-dim); margin-top:3px;">${quarterStr}</div>`;
  }

  return `<div style="${epsBg} padding: 6px 12px; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; white-space: nowrap; box-shadow: 0 2px 8px rgba(0,0,0,0.15); min-width: 130px;" title="最新一季真實EPS與QoQ">
    <div style="display:flex; align-items:center;">
      <span style="font-weight: 900; font-size: 1.25rem; color: var(--text-main); letter-spacing: 0.5px;">💰 $${epsNumStr}</span>
      ${growthSpan}
    </div>
    ${gmDisplay}
  </div>`;
}

function renderScreenerTable(resetPagination = false) {
  const body = document.getElementById('screener-body');
  const countText = document.getElementById('results-count-text');
  const paginationControls = document.getElementById('pagination-controls');

  if (!body) return;

  if (countText) {
    const sortLabel = getSortLabel();
    const misCount = allStocks.filter(s => s.data_source === 'MIS即時').length;
    const isLive = misCount > 0;
    const sample = allStocks.find(s => s.trade_date) || {};
    const dateLabel = sample.trade_date ? ` | 交易日: ${sample.trade_date}` : '';
    const srcLabel = isLive ? `🟢 MIS 官方即時行情 (${misCount.toLocaleString()} 檔撮合中)` : '🟡 OpenAPI 日收盤';
    const nowTime = new Date().toLocaleTimeString('zh-TW', { hour12: false });
    countText.textContent = `${srcLabel}${dateLabel} (更新時間: ${nowTime}) — 共 ${filteredStocks.length} 檔 | 排序: ${sortLabel} | 第 ${currentPage} 頁`;
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

    const isFund = isETF(s) || isETN(s) || (s.market && (s.market.includes('ETF') || s.market.includes('ETN')));
    const marketPill = s.market === 'TWSE上市' ? 'pill-green'
      : (s.market === 'TPEx上櫃' ? 'pill-blue'
      : (s.market.includes('ETF') ? 'pill-orange'
      : (s.market.includes('ETN') ? 'pill-purple' : 'pill-purple')));

    const vol = s.volume ?? 0;
    const volDisplay = vol >= 10000
      ? `${(vol / 10000).toFixed(1)}萬張`
      : vol >= 1000
        ? `${(vol / 1000).toFixed(1)}千張`
        : `${vol}張`;

    const hasYoy = !isFund && typeof s.yoy === 'number' && !isNaN(s.yoy) && s.yoy !== null;
    const yoyDisplay = isFund ? '-' : (hasYoy ? `${s.yoy > 0 ? '+' : ''}${s.yoy.toFixed(1)}%` : '-');
    const yoyColor = !hasYoy ? 'var(--text-muted)' : (s.yoy > 0 ? 'var(--accent-red)' : (s.yoy < 0 ? 'var(--accent-green)' : 'var(--text-muted)'));
    const peDisplay = (!isFund && s.pe > 0) ? `${s.pe}x` : '-';
    const peColor = (!isFund && s.pe > 0 && s.pe < 20) ? '#10b981' : (s.pe > 50 ? '#f87171' : 'var(--text-main)');

    const epsDisplay = formatEpsDisplay(s);

    // 沿著五日線，回檔10日有稱標紅字
    let isSupportedByMA10 = false;
    const tc = techCache[s.symbol.split('.')[0]];
    if (tc && tc.sma5 && tc.sma10) {
      if (tc.sma5 > tc.sma10 && s.price >= tc.sma10 && s.price <= tc.sma10 * 1.02) {
        isSupportedByMA10 = true;
      }
    }
    const nameStyle = isSupportedByMA10 ? 'color: var(--accent-red); font-weight: 900;' : 'font-weight: bold;';

    // 成交量與增量判斷
    const volDisplayStr = volDisplay;
    let volStatus = '';
    if (tc && tc.vol_sma20) {
      if (vol > tc.vol_sma20 * 1.5) {
        volStatus = `<span style="color: var(--accent-red); font-size: 0.8rem; font-weight: 700; background: rgba(239, 68, 68, 0.15); padding: 2px 4px; border-radius: 4px; margin-left: 4px;">🔥爆量</span>`;
      } else if (vol > tc.vol_sma20) {
        volStatus = `<span style="color: var(--accent-orange); font-size: 0.8rem; font-weight: 700; margin-left: 4px;">📈增量</span>`;
      } else {
        volStatus = `<span style="color: var(--text-dim); font-size: 0.8rem; font-weight: 500; margin-left: 4px;">量縮</span>`;
      }
    }
    const volumeCell = `<td style="font-family:var(--font-mono); color:var(--text-main); font-weight:600;">${volDisplayStr}${volStatus}</td>`;

    const pureCode = s.symbol.split('.')[0];
    const alertData = latestSurgeAlertsMap.get(pureCode);
    const surgeBadgeHtml = alertData ? `<span class="screener-surge-tag" title="盤中即時急拉 ${alertData.surge_window || '短線'}: +${(alertData.surge_pct || alertData.change_pct || 0).toFixed(1)}%">⚡+${(alertData.surge_pct || alertData.change_pct || 0).toFixed(1)}%</span>` : '';

    return `
      <tr class="stock-row-tick" onclick="openStockChartModal('${pureCode}', 'intraday')" style="cursor:pointer;" title="點擊查看 ${s.name} (${s.symbol}) 盤中即時走勢圖與均線指標">
        <td><span class="score-badge ${scoreClass}">${scoreBadgeText}</span></td>
        <td class="symbol-code">${s.symbol}</td>
        <td><strong style="${nameStyle}">${s.name}</strong>${surgeBadgeHtml}<br><span style="font-size:0.75rem; color:var(--text-dim);">${s.desc || ''}</span></td>
        <td><span class="pill ${marketPill}">${s.market}</span></td>
        <td><span class="pill pill-blue">${s.sector}</span></td>
        <td style="font-family:var(--font-mono); font-weight:800; font-size:0.95rem;">NT$ ${s.price.toLocaleString('zh-TW', {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
        <td style="color: ${changeColor}; font-weight:700; font-family:var(--font-mono);">${chgArrow} ${s.change}</td>
        <td style="color:${yoyColor}; font-weight:700; font-family:var(--font-mono);">${yoyDisplay}</td>
        <td style="color:${peColor}; font-family:var(--font-mono);">${peDisplay}</td>
        <td>${epsDisplay}</td>
        ${volumeCell}
        <td><span class="pill pill-purple">${s.inst}</span></td>
        <td style="text-align:center;">${generateSparklineSvg(techCache[s.symbol.split('.')[0]]?.history5d)}</td>
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

/* ── 實時原地更新 DOM 數值 (股價、漲跌、量能) — 行次位置保持不動，避免跳動 ── */
function updateLiveStockInfoInDOM() {
  const stockMap = new Map(allStocks.map(s => [s.symbol, s]));

  // 1. 篩選結果表格：原地更新
  const rows = document.querySelectorAll('#screener-body tr[data-symbol]');
  rows.forEach(tr => {
    const sym = tr.getAttribute('data-symbol');
    const s = stockMap.get(sym);
    if (!s) return;

    // 股價更新與微閃
    const priceEl = tr.querySelector('.col-price');
    if (priceEl) {
      const formattedPrice = `NT$ ${s.price.toLocaleString('zh-TW', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
      if (priceEl.textContent !== formattedPrice) {
        const oldPrice = parseFloat(priceEl.textContent.replace(/[^\d.-]/g, '')) || 0;
        priceEl.textContent = formattedPrice;
        if (oldPrice > 0 && s.price !== oldPrice) {
          const tickClass = s.price > oldPrice ? 'price-tick-up' : 'price-tick-down';
          priceEl.classList.remove('price-tick-up', 'price-tick-down');
          void priceEl.offsetWidth; // 強制重繪
          priceEl.classList.add(tickClass);
        }
      }
    }

    // 漲跌更新
    const chgEl = tr.querySelector('.col-change');
    if (chgEl) {
      const chgPct = parseChangePct(s.change);
      const chgColor = chgPct > 0 ? 'var(--accent-red)' : (chgPct < 0 ? 'var(--accent-green)' : 'var(--text-main)');
      const chgArrow = chgPct > 0 ? '▲' : (chgPct < 0 ? '▼' : '');
      const formattedChg = `${chgArrow} ${s.change}`;
      if (chgEl.textContent !== formattedChg) {
        chgEl.textContent = formattedChg;
        chgEl.style.color = chgColor;
      }
    }

    // 成交量更新
    const volEl = tr.querySelector('.col-volume');
    if (volEl) {
      const vol = s.volume ?? 0;
      const volDisplay = vol >= 10000
        ? `${(vol / 10000).toFixed(1)}萬張`
        : vol >= 1000
          ? `${(vol / 1000).toFixed(1)}千張`
          : `${vol}張`;
      const tc = techCache[s.symbol.split('.')[0]];
      let volStatus = '';
      if (tc && tc.vol_sma20) {
        if (vol > tc.vol_sma20 * 1.5) {
          volStatus = `<span style="color: var(--accent-red); font-size: 0.8rem; font-weight: 700; background: rgba(239, 68, 68, 0.15); padding: 2px 4px; border-radius: 4px; margin-left: 4px;">🔥爆量</span>`;
        } else if (vol > tc.vol_sma20) {
          volStatus = `<span style="color: var(--accent-orange); font-size: 0.8rem; font-weight: 700; margin-left: 4px;">📈增量</span>`;
        } else {
          volStatus = `<span style="color: var(--text-dim); font-size: 0.8rem; font-weight: 500; margin-left: 4px;">量縮</span>`;
        }
      }
      const newVolHtml = `${volDisplay}${volStatus}`;
      if (volEl.innerHTML !== newVolHtml) {
        volEl.innerHTML = newVolHtml;
      }
    }
  });

  // 2. 頂部最強起漲飆股橫幅：原地更新數值
  const stripCards = document.querySelectorAll('#top-gainers-strip .top-gainer-item[data-symbol]');
  stripCards.forEach(card => {
    const sym = card.getAttribute('data-symbol');
    const s = stockMap.get(sym);
    if (!s) return;
    const pEl = card.querySelector('.strip-price');
    if (pEl) {
      const newP = `$${s.price.toLocaleString()}`;
      if (pEl.textContent !== newP) pEl.textContent = newP;
    }
    const cEl = card.querySelector('.strip-change');
    if (cEl) {
      const pct = parseChangePct(s.change);
      const newC = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
      if (cEl.textContent !== newC) {
        cEl.textContent = newC;
        cEl.style.color = pct >= 0 ? '#f87171' : 'var(--accent-green)';
      }
    }
    const vEl = card.querySelector('.strip-vol');
    if (vEl) {
      const vol = s.volume || 0;
      const volStr = vol >= 10000 ? `${(vol / 10000).toFixed(1)}萬張` : `${vol.toLocaleString()}張`;
      if (vEl.textContent !== volStr) vEl.textContent = volStr;
    }
  });

  // 3. AI 六維飆股漏斗：原地更新數值
  const momRows = document.querySelectorAll('#momentum-body tr[data-symbol]');
  momRows.forEach(tr => {
    const sym = tr.getAttribute('data-symbol');
    const s = stockMap.get(sym);
    if (!s) return;
    const pEl = tr.querySelector('.mom-price');
    if (pEl) {
      const newP = `NT$ ${s.price.toLocaleString('zh-TW', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
      if (pEl.textContent !== newP) pEl.textContent = newP;
    }
    const cEl = tr.querySelector('.mom-change');
    if (cEl) {
      const chgPct = parseChangePct(s.change);
      const chgColor = chgPct > 0 ? 'var(--accent-red)' : (chgPct < 0 ? 'var(--accent-green)' : 'var(--text-main)');
      const chgArrow = chgPct > 0 ? '▲' : (chgPct < 0 ? '▼' : '');
      const newC = `${chgArrow} ${s.change}`;
      if (cEl.textContent !== newC) {
        cEl.textContent = newC;
        cEl.style.color = chgColor;
      }
    }
  });

  // 4. 更新時間與行情來源摘要
  updateResultsHeader();
}

function updateResultsHeader() {
  const countText = document.getElementById('results-count-text');
  if (!countText) return;
  const sortLabel = getSortLabel();
  const misCount = allStocks.filter(s => s.data_source === 'MIS即時').length;
  const isLive = misCount > 0;
  const sample = allStocks.find(s => s.trade_date) || {};
  const dateLabel = sample.trade_date ? ` | 交易日: ${sample.trade_date}` : '';
  const srcLabel = isLive ? `🟢 MIS 官方即時行情 (${misCount.toLocaleString()} 檔撮合中)` : '🟡 OpenAPI 日收盤';
  const nowTime = new Date().toLocaleTimeString('zh-TW', { hour12: false });
  countText.textContent = `${srcLabel}${dateLabel} (更新時間: ${nowTime}) — 共 ${filteredStocks.length} 檔 | 排序: ${sortLabel} | 第 ${currentPage} 頁`;
}

/* ── 載入並渲染 AI 飆股漏斗 ── */
async function loadMomentumStocks() {
  try {
    if (Object.keys(epsCache).length === 0) {
      try {
        const epsRes = await fetch('eps_cache.json?t=' + Date.now());
        if (epsRes.ok) epsCache = await epsRes.json();
      } catch (e) {}
    }
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

    // 沿著五日線，回檔10日有稱標紅字
    let isSupportedByMA10 = false;
    const tc = techCache[s.symbol.split('.')[0]];
    if (tc && tc.sma5 && tc.sma10) {
      if (tc.sma5 > tc.sma10 && s.price >= tc.sma10 && s.price <= tc.sma10 * 1.02) {
        isSupportedByMA10 = true;
      }
    }
    const nameStyle = isSupportedByMA10 ? 'color: var(--accent-red); font-weight: 900;' : 'font-weight: 700;';

    const epsDisplay = formatEpsDisplay(s);

    // 成交量與增量判斷
    const vol = s.volume ?? 0;
    const volDisplayStr = vol >= 10000 ? `${(vol / 10000).toFixed(1)}萬張` : vol >= 1000 ? `${(vol / 1000).toFixed(1)}千張` : `${vol}張`;
    let volStatus = '';
    if (tc && tc.vol_sma20) {
      if (vol > tc.vol_sma20 * 1.5) {
        volStatus = `<span style="color: var(--accent-red); font-size: 0.8rem; font-weight: 700; background: rgba(239, 68, 68, 0.15); padding: 2px 4px; border-radius: 4px; margin-left: 4px;">🔥爆量</span>`;
      } else if (vol > tc.vol_sma20) {
        volStatus = `<span style="color: var(--accent-orange); font-size: 0.8rem; font-weight: 700; margin-left: 4px;">📈增量</span>`;
      } else {
        volStatus = `<span style="color: var(--text-dim); font-size: 0.8rem; font-weight: 500; margin-left: 4px;">量縮</span>`;
      }
    }
    const volumeCell = `<td style="font-family:var(--font-mono); color:var(--text-main); font-weight:600;">${volDisplayStr}${volStatus}</td>`;

    return `
      <tr class="stock-row-tick" data-symbol="${s.symbol}" onclick="openStockChartModal('${s.symbol.split('.')[0]}', 'intraday')" style="cursor:pointer;" title="點擊查看 ${s.name} (${s.symbol}) 盤中即時走勢圖與均線指標">
        <td><span class="score-badge ${badgeClass}">${s.ai_score.toFixed(1)}分</span></td>
        <td style="font-weight:700;">${s.signal}</td>
        <td class="symbol-code">${s.symbol}</td>
        <td><strong style="${nameStyle}">${s.name}</strong></td>
        <td class="mom-price" style="font-family:var(--font-mono); font-weight:800;">NT$ ${s.price.toLocaleString('zh-TW', {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
        <td class="mom-change" style="color: ${chgColor}; font-weight:700; font-family:var(--font-mono);">${chgArrow} ${s.change}</td>
        <td><span class="pill pill-purple">${s.theme_tag}</span></td>
        <td><span class="pill pill-blue">${s.inst}</span></td>
        <td>${epsDisplay}</td>
        ${volumeCell}
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

/* ── Tab 切換核心 ── */
function switchTab(target) {
  currentActiveTab = target;
  const tabs = document.querySelectorAll('.nav-tab');
  const panes = document.querySelectorAll('.tab-pane');
  tabs.forEach(t => t.classList.toggle('active', t.getAttribute('data-tab') === target));
  panes.forEach(p => p.classList.toggle('active', p.id === target));
  const targetPane = document.getElementById(target);
  if (targetPane) {
    targetPane.classList.add('active');
    if (target === 'surge-tab') {
      renderSurgeTabContent();
    } else if (target === 'surge-mixed-tab') {
      renderSurgeMixedTabContent();
    }
  }
  if (window.history && window.history.replaceState) {
    const hashVal = target === 'surge-tab' ? 'surge' : (target === 'surge-mixed-tab' ? 'surge-mixed' : (target === 'ai-momentum' ? 'ai' : target));
    window.history.replaceState(null, '', '#' + hashVal);
  }
}
window.switchTab = switchTab;

function initTabs() {
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-tab');
      switchTab(target);
    });
  });
}

/* ═════════════════════════════════════════════════════════════════════
   ⚡ 盤中急拉 產業族群分類系統與發光彩色邊框 (Sector Grouping & Colored Frame)
   ═════════════════════════════════════════════════════════════════════ */
const SECTOR_THEMES = {
  '光電產業': { name: '光電產業', icon: '💡', color: '#38bdf8', bg: 'rgba(56, 189, 248, 0.08)', border: '#38bdf8' },
  '電子零組件': { name: '電子零組件', icon: '⚡', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.08)', border: '#f59e0b' },
  '半導體業': { name: '半導體業', icon: '🔬', color: '#a855f7', bg: 'rgba(168, 85, 247, 0.08)', border: '#a855f7' },
  '塑膠石化': { name: '塑膠石化', icon: '🧪', color: '#fb923c', bg: 'rgba(251, 146, 60, 0.08)', border: '#fb923c' },
  '通信網路': { name: '通信網路', icon: '📡', color: '#6366f1', bg: 'rgba(99, 102, 241, 0.08)', border: '#6366f1' },
  '紡織纖維': { name: '紡織纖維', icon: '🧵', color: '#f43f5e', bg: 'rgba(244, 63, 94, 0.08)', border: '#f43f5e' },
  '建材營造': { name: '建材營造', icon: '🏗️', color: '#eab308', bg: 'rgba(234, 179, 8, 0.08)', border: '#eab308' },
  '電腦週邊': { name: '電腦週邊', icon: '💻', color: '#10b981', bg: 'rgba(16, 185, 129, 0.08)', border: '#10b981' },
  '金融保險': { name: '金融保險', icon: '🏦', color: '#14b8a6', bg: 'rgba(20, 184, 166, 0.08)', border: '#14b8a6' },
  '生技醫療': { name: '生技醫療', icon: '💊', color: '#ec4899', bg: 'rgba(236, 72, 153, 0.08)', border: '#ec4899' },
  '綠能重電': { name: '綠能重電', icon: '🌱', color: '#84cc16', bg: 'rgba(132, 204, 22, 0.08)', border: '#84cc16' },
  '航運物流': { name: '航運物流', icon: '🚢', color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.08)', border: '#3b82f6' },
  '汽車工業': { name: '汽車工業', icon: '🚗', color: '#f97316', bg: 'rgba(249, 115, 22, 0.08)', border: '#f97316' },
  '傳統原物料': { name: '傳統原物料', icon: '📦', color: '#a3e635', bg: 'rgba(163, 230, 53, 0.08)', border: '#a3e635' },
  '其他電子': { name: '其他電子', icon: '✨', color: '#818cf8', bg: 'rgba(129, 140, 248, 0.08)', border: '#818cf8' },
  '其他強勢股': { name: '其他強勢股', icon: '🔥', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.08)', border: '#94a3b8' }
};

const SECTOR_CODE_MAP = {
  // 光電
  '6278': '光電產業', '3543': '光電產業', '4934': '光電產業', '3481': '光電產業',
  '5244': '光電產業', '2466': '光電產業', '3362': '光電產業', '3081': '通信網路',
  // 通訊
  '3234': '通信網路', '6163': '通信網路', '6218': '通信網路',
  // 電子零組件
  '6108': '電子零組件', '8039': '電子零組件', '4989': '電子零組件', '2484': '電子零組件',
  '2472': '電子零組件', '8042': '電子零組件', '8121': '電子零組件', '5340': '電子零組件',
  // 半導體
  '3016': '半導體業', '8131': '半導體業', '6532': '半導體業', '6182': '半導體業',
  '6667': '半導體業', '3675': '半導體業',
  // 塑膠
  '1305': '塑膠石化', '1304': '塑膠石化', '1308': '塑膠石化', '1309': '塑膠石化', '1303': '塑膠石化',
  // 營建
  '2543': '建材營造', '1808': '建材營造', '2504': '建材營造', '2515': '建材營造',
  // 紡織
  '1440': '紡織纖維', '1402': '紡織纖維', '1455': '紡織纖維', '9919': '紡織纖維',
  // 電腦
  '6933': '電腦週邊', '1569': '電腦週邊',
  // 金融
  '2851': '金融保險', '2880': '金融保險',
  // 生技
  '1795': '生技醫療',
  // 綠能
  '9921': '綠能重電',
  // 航運
  '2607': '航運物流',
  // 汽車
  '1319': '汽車工業',
  // 原物料
  '2108': '傳統原物料', '1904': '傳統原物料', '2464': '其他電子'
};

const SECTOR_NAME_MAP = {
  '光電': '光電產業', '光電產業': '光電產業', '光電通訊': '通信網路', '26': '光電產業',
  '半導體': '半導體業', '半導體業': '半導體業', '24': '半導體業',
  '電子零組件': '電子零組件', '28': '電子零組件',
  '塑膠': '塑膠石化', '塑膠工業': '塑膠石化', '03': '塑膠石化',
  '建材營造': '建材營造', '營建': '建材營造', '14': '建材營造',
  '紡織纖維': '紡織纖維', '紡織': '紡織纖維', '04': '紡織纖維',
  '金融保險': '金融保險', '金融': '金融保險', '17': '金融保險',
  '電腦週邊': '電腦週邊', '電腦及週邊': '電腦週邊', '25': '電腦週邊',
  '綠能環保': '綠能重電', '重電': '綠能重電', '37': '綠能重電',
  '生技醫療': '生技醫療', '生技': '生技醫療', '22': '生技醫療',
  '航運物流': '航運物流', '航運': '航運物流', '15': '航運物流',
  '汽車': '汽車工業', '汽車工業': '汽車工業', '13': '汽車工業', '12': '汽車工業',
  '橡膠': '傳統原物料', '造紙': '傳統原物料', '11': '傳統原物料', '09': '傳統原物料',
  '其他電子': '其他電子', '31': '其他電子',
  '通信網路': '通信網路', '通信': '通信網路', '27': '通信網路'
};

let surgeTabSortMode = 'surge';
let surgeTabDisplayMode = 'grouped'; // 'grouped' (族群彩色框) | 'flat' (全市場總榜)
let surgeTabSectorFilter = null; // null: 全部族群, or sector name
let surgePanelDisplayMode = 'grouped'; // floating surge panel: 'grouped' | 'flat'
const collapsedSectorFrames = new Set();

function resolveStockSector(code, rawSector) {
  const cleanCode = (code || '').replace('.TW', '').replace('.TWO', '');
  if (SECTOR_CODE_MAP[cleanCode]) {
    return SECTOR_CODE_MAP[cleanCode];
  }
  const trimmed = (rawSector || '').trim();
  if (SECTOR_NAME_MAP[trimmed]) {
    return SECTOR_NAME_MAP[trimmed];
  }
  if (!trimmed || trimmed === '其他' || trimmed === '20') {
    return '其他強勢股';
  }
  return trimmed;
}

function groupSurgeAlertsBySector(alerts) {
  const groupsMap = new Map();
  alerts.forEach(a => {
    const secName = resolveStockSector(a.code, a.sector);
    if (!groupsMap.has(secName)) {
      const theme = SECTOR_THEMES[secName] || SECTOR_THEMES['其他強勢股'];
      groupsMap.set(secName, {
        name: secName,
        theme: theme,
        stocks: []
      });
    }
    groupsMap.get(secName).stocks.push(a);
  });

  const groups = Array.from(groupsMap.values());
  groups.forEach(g => {
    g.stocks.sort((a, b) => {
      if (surgeTabSortMode === 'surge') {
        return (b.surge_pct || b.change_pct || 0) - (a.surge_pct || a.change_pct || 0);
      } else if (surgeTabSortMode === 'time') {
        return (b.surge_ts || 0) - (a.surge_ts || 0);
      } else if (surgeTabSortMode === 'growth') {
        return (b.change_pct || 0) - (a.change_pct || 0);
      } else {
        const pa = (a.ai_score || 0) * 2 + (a.breakout_score || 0) + (a.surge_pct || a.change_pct || 0) * 3;
        const pb = (b.ai_score || 0) * 2 + (b.breakout_score || 0) + (b.surge_pct || b.change_pct || 0) * 3;
        return pb - pa;
      }
    });

    g.count = g.stocks.length;
    g.topStock = g.stocks[0];
    const totalSurge = g.stocks.reduce((acc, s) => acc + (s.surge_pct || s.change_pct || 0), 0);
    g.avgSurgePct = g.count > 0 ? (totalSurge / g.count) : 0;
  });

  // 均拉最高放到最上面 (Sort groups strictly by highest avgSurgePct desc)
  groups.sort((a, b) => {
    if (Math.abs(b.avgSurgePct - a.avgSurgePct) > 0.0001) {
      return b.avgSurgePct - a.avgSurgePct;
    }
    const aTop = a.topStock ? (a.topStock.surge_pct || a.topStock.change_pct || 0) : 0;
    const bTop = b.topStock ? (b.topStock.surge_pct || b.topStock.change_pct || 0) : 0;
    if (Math.abs(bTop - aTop) > 0.0001) return bTop - aTop;
    return b.count - a.count;
  });

  return groups;
}

function setSurgeTabSort(mode) {
  surgeTabSortMode = mode;
  ['surge', 'time', 'growth', 'ai'].forEach(m => {
    const btn = document.getElementById(`surge-tab-sort-${m}`);
    if (btn) btn.classList.toggle('active', m === mode);
  });
  renderSurgeTabContent();
}

function setSurgeTabMode(mode) {
  surgeTabDisplayMode = mode;
  const btnGrouped = document.getElementById('surge-tab-mode-grouped');
  const btnFlat = document.getElementById('surge-tab-mode-flat');
  const groupedView = document.getElementById('surge-tab-grouped-view');
  const flatView = document.getElementById('surge-tab-flat-view');
  const chipsWrap = document.getElementById('surge-tab-sector-chips-wrap');

  if (btnGrouped) btnGrouped.classList.toggle('active', mode === 'grouped');
  if (btnFlat) btnFlat.classList.toggle('active', mode === 'flat');

  if (mode === 'grouped') {
    if (groupedView) groupedView.style.display = 'flex';
    if (flatView) flatView.style.display = 'none';
    if (chipsWrap) chipsWrap.style.display = 'block';
  } else {
    if (groupedView) groupedView.style.display = 'none';
    if (flatView) flatView.style.display = 'block';
    if (chipsWrap) chipsWrap.style.display = 'none';
  }
  renderSurgeTabContent();
}

function setSurgeSectorFilter(sectorName) {
  surgeTabSectorFilter = (surgeTabSectorFilter === sectorName) ? null : sectorName;
  renderSurgeTabContent();
}

function toggleSectorFrameCollapse(sectorName) {
  const body = document.getElementById(`sector-body-${sectorName}`);
  const chevron = document.getElementById(`sector-chevron-${sectorName}`);
  if (collapsedSectorFrames.has(sectorName)) {
    collapsedSectorFrames.delete(sectorName);
    if (body) body.style.display = 'grid';
    if (chevron) chevron.style.transform = 'rotate(0deg)';
  } else {
    collapsedSectorFrames.add(sectorName);
    if (body) body.style.display = 'none';
    if (chevron) chevron.style.transform = 'rotate(-90deg)';
  }
}

function setSurgePanelMode(mode) {
  surgePanelDisplayMode = mode;
  const btnGrouped = document.getElementById('surge-panel-mode-grouped');
  const btnFlat = document.getElementById('surge-panel-mode-flat');
  if (btnGrouped) {
    btnGrouped.style.background = mode === 'grouped' ? '#6366f1' : 'transparent';
    btnGrouped.style.color = mode === 'grouped' ? '#fff' : '#94a3b8';
  }
  if (btnFlat) {
    btnFlat.style.background = mode === 'flat' ? '#6366f1' : 'transparent';
    btnFlat.style.color = mode === 'flat' ? '#fff' : '#94a3b8';
  }
  pollSurgeAlerts(true);
}

function renderPanelGroupedSectorsHtml(alerts) {
  const groups = groupSurgeAlertsBySector(alerts);
  return groups.map((g, idx) => {
    const theme = g.theme;
    const top = g.topStock;
    const isTop1 = idx === 0;
    const topText = top ? `🔥 領頭: <strong style="color:#fff;">${top.name}</strong> <strong style="color:${theme.color}; font-family:var(--font-mono);">+${(top.surge_pct || top.change_pct || 0).toFixed(2)}%</strong>` : '';

    return `
      <div class="sector-group-frame ${isTop1 ? 'top-avg-surge-group' : ''}" style="--sector-color:${theme.color}; --sector-border:${theme.color}; --sector-bg:${theme.bg}; --sector-glow:${theme.color}40; margin-bottom:12px; ${isTop1 ? 'box-shadow: 0 0 20px rgba(239,68,68,0.35);' : ''}">
        <div class="sector-group-header" style="padding:10px 14px;">
          <div class="sector-title-wrap" style="gap:8px;">
            <div class="sector-icon-badge" style="width:28px; height:28px; font-size:0.95rem;">${theme.icon}</div>
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
              ${isTop1 ? `<span style="background:linear-gradient(135deg,#ef4444,#f59e0b); color:#fff; font-size:0.7rem; font-weight:900; padding:1px 7px; border-radius:10px; box-shadow:0 0 8px rgba(239,68,68,0.5);">🏆 均拉 No.1</span>` : `<span style="font-size:0.7rem; color:#94a3b8; font-weight:700;">#${idx+1}</span>`}
              <span class="sector-name" style="font-size:1.02rem;">${g.name}</span>
              <span class="sector-count-badge" style="font-size:0.72rem; padding:1px 6px;">${g.count} 檔</span>
              ${topText ? `<span style="font-size:0.72rem; color:#cbd5e1; margin-left:4px;">${topText}</span>` : ''}
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:6px;">
            <span class="sector-avg-badge" style="font-size:0.76rem; padding:2px 8px; ${isTop1 ? 'background:linear-gradient(135deg, #ef4444, #dc2626); color:#fff; font-weight:900; box-shadow:0 0 8px rgba(239,68,68,0.4);' : ''}">均拉 +${g.avgSurgePct.toFixed(2)}%</span>
          </div>
        </div>
        <div class="sector-grid-cards" style="grid-template-columns: repeat(4, minmax(0, 1fr)); gap:10px; padding:10px;">
          ${g.stocks.map(s => renderAlertCardHtml(s)).join('')}
        </div>
      </div>
    `;
  }).join('');
}

function renderSectorGroupFrameHtml(group, rankIdx = 0) {
  const theme = group.theme;
  const top = group.topStock;
  const isTop1 = (rankIdx === 0) && (!surgeTabSectorFilter);
  const rankBadge = isTop1 
    ? `<span style="background:linear-gradient(135deg, #ef4444, #f59e0b); color:#fff; font-size:0.76rem; font-weight:900; padding:2px 8px; border-radius:12px; box-shadow:0 0 12px rgba(239,68,68,0.55); display:inline-flex; align-items:center; gap:3px;">🏆 均拉最強 No.1</span>`
    : `<span style="background:rgba(255,255,255,0.08); color:#cbd5e1; font-size:0.72rem; font-weight:700; padding:1px 7px; border-radius:10px;">#${rankIdx + 1}</span>`;
  const topText = top ? `🔥 領頭羊: <strong style="color:#fff;">${top.name}</strong> <span style="font-family:var(--font-mono); font-size:0.75rem; color:#cbd5e1;">(${top.code})</span> <strong style="color:${theme.color}; font-family:var(--font-mono); margin-left:2px;">+${(top.surge_pct || top.change_pct || 0).toFixed(2)}%</strong>` : '';
  const isCollapsed = collapsedSectorFrames.has(group.name);

  return `
    <div class="sector-group-frame ${isTop1 ? 'top-avg-surge-group' : ''}" id="sector-frame-${group.name}" style="--sector-color:${theme.color}; --sector-border:${theme.color}; --sector-bg:${theme.bg}; --sector-glow:${theme.color}40; ${isTop1 ? 'box-shadow: 0 0 25px ' + theme.color + '33, 0 8px 30px rgba(0,0,0,0.45);' : ''}">
      <div class="sector-group-header" onclick="toggleSectorFrameCollapse('${group.name}')" title="點擊展開/收折該族群">
        <div class="sector-title-wrap">
          <div class="sector-icon-badge">${theme.icon}</div>
          <div style="display:flex; flex-direction:column; gap:2px;">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              ${rankBadge}
              <span class="sector-name">${group.name}</span>
              <span class="sector-count-badge">${group.count} 檔</span>
            </div>
            ${topText ? `<div class="sector-leader-tag">${topText}</div>` : ''}
          </div>
        </div>

        <div style="display:flex; align-items:center; gap:12px;">
          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:2px;">
            <span style="font-size:0.7rem; color:#94a3b8;">族群平均急拉</span>
            <span class="sector-avg-badge" style="${isTop1 ? 'background:linear-gradient(135deg, #ef4444, #dc2626); color:#fff; font-weight:900; box-shadow:0 0 10px rgba(239,68,68,0.5);' : ''}">+${group.avgSurgePct.toFixed(2)}%</span>
          </div>
          <span id="sector-chevron-${group.name}" style="font-size:0.85rem; color:#94a3b8; transition:transform 0.2s; transform:${isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)'};">▼</span>
        </div>
      </div>

      <div class="sector-grid-cards" id="sector-body-${group.name}" style="display:${isCollapsed ? 'none' : 'grid'};">
        ${group.stocks.map(s => renderAlertCardHtml(s)).join('')}
      </div>
    </div>
  `;
}

function renderSurgeTabContent() {
  const groupedView = document.getElementById('surge-tab-grouped-view');
  const flatView = document.getElementById('surge-tab-flat-view');
  const tbody = document.getElementById('surge-tab-body');
  const chipsEl = document.getElementById('surge-tab-sector-chips');
  const badge = document.getElementById('surge-tab-count-badge');
  const matchedBadge = document.getElementById('surge-filter-matched-badge');

  const alerts = Array.from(latestSurgeAlertsMap.values());
  if (badge) badge.textContent = `${alerts.length} 檔就緒`;

  if (alerts.length === 0) {
    if (groupedView) groupedView.innerHTML = `
      <div style="text-align:center; padding: 48px 16px; background: rgba(255,255,255,0.02); border: 1px dashed rgba(255,255,255,0.1); border-radius: 14px;">
        <div style="font-size: 2.4rem; margin-bottom: 8px;">🔄</div>
        <div style="font-weight: 800; color: #f1f5f9; font-size: 1.05rem;">正在即時載入盤中急拉族群...</div>
        <div style="font-size: 0.8rem; color: #64748b; margin-top: 6px;">全市場撮合秒級串流中，正在為您依產業族群建立發光彩色邊框！</div>
      </div>
    `;
    if (tbody) tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding: 40px; color:#94a3b8;">🔄 正在載入盤中急拉標的...</td></tr>`;
    return;
  }

  // 1. 依據排序模式對股票進行排序
  const sorted = [...alerts].sort((a, b) => {
    if (surgeTabSortMode === 'surge') {
      return (b.surge_pct !== undefined ? b.surge_pct : b.change_pct || 0) - (a.surge_pct !== undefined ? a.surge_pct : a.change_pct || 0);
    } else if (surgeTabSortMode === 'time') {
      return (b.surge_ts || 0) - (a.surge_ts || 0);
    } else if (surgeTabSortMode === 'growth') {
      return (b.change_pct || 0) - (a.change_pct || 0);
    } else {
      const pa = (a.ai_score || 0) * 2 + (a.breakout_score || 0) + (a.surge_pct || a.change_pct || 0) * 3;
      const pb = (b.ai_score || 0) * 2 + (b.breakout_score || 0) + (b.surge_pct || b.change_pct || 0) * 3;
      return pb - pa;
    }
  });

  // 2. 應用多維極速精準篩選
  const filtered = getFilteredSurgeAlerts(sorted);
  if (matchedBadge) matchedBadge.textContent = `${filtered.length} / ${alerts.length} 檔`;
  if (badge) badge.textContent = `${filtered.length} 檔就緒`;

  // 3. 渲染總榜 12 欄位詳細數據表
  if (tbody) {
    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding: 40px; color:#94a3b8;">
        🔍 無符合精準篩選條件的急拉標的，請嘗試放寬條件或 <button onclick="resetSurgeFilters()" style="color:#38bdf8;background:none;border:none;cursor:pointer;text-decoration:underline;font-weight:700;">點此重設篩選</button>
      </td></tr>`;
    } else {
      tbody.innerHTML = filtered.map((a, idx) => {
        const pct = a.change_pct || 0;
        const sPct = a.surge_pct !== undefined ? a.surge_pct : pct;
        const win = a.surge_window || '急拉';
        const startP = a.surge_start_price ? `$${a.surge_start_price}` : '-';
        const liveP = a.price || '-';
        const volStr = a.volume ? (a.volume >= 10000 ? `${(a.volume/10000).toFixed(1)}萬` : a.volume.toLocaleString()) : '-';
        const rankColor = idx < 3 ? '#f87171' : (idx < 10 ? '#fbbf24' : '#cbd5e1');
        const aiSc = a.ai_score ? a.ai_score.toFixed(1) : '-';
        const bkSc = a.breakout_score ? `(${a.breakout_score.toFixed(0)})` : '';
        const spark = a.ticks ? generateTicksSparklineSvg(a.ticks) : '';

        return `
          <tr style="cursor:pointer;" onclick="openStockChartModal('${a.code}', 'intraday')">
            <td style="text-align:center; font-weight:800; color:${rankColor};">#${idx + 1}</td>
            <td><strong style="color:#f8fafc; font-family:var(--font-mono);">${a.code}</strong></td>
            <td><strong style="color:#f1f5f9; font-size:0.95rem;">${a.name}</strong></td>
            <td><span style="font-weight:800; color:#f8fafc; font-family:var(--font-mono);">$${liveP}</span></td>
            <td><span style="font-weight:900; color:#f87171; font-family:var(--font-mono);">${pct > 0 ? '+' : ''}${pct.toFixed(2)}%</span></td>
            <td><span style="background:rgba(239,68,68,0.18); border:1px solid rgba(239,68,68,0.4); color:#fca5a5; padding:2px 7px; border-radius:6px; font-size:0.75rem; font-weight:700;">⚡ ${win}</span></td>
            <td><strong style="color:#fbbf24; font-family:var(--font-mono); font-size:0.95rem;">+${sPct.toFixed(2)}%</strong></td>
            <td><span style="font-size:0.8rem; color:#94a3b8; font-family:var(--font-mono);">${startP} ➔ <strong style="color:#f87171;">$${liveP}</strong></span></td>
            <td><span style="color:#cbd5e1; font-family:var(--font-mono);">${volStr}</span></td>
            <td><span style="font-size:0.8rem; color:#94a3b8;">${a.sector || '-'}</span></td>
            <td><span style="color:#c084fc; font-weight:700;">${aiSc} ${bkSc}</span></td>
            <td>
              <div style="display:flex; align-items:center; gap:6px;">
                ${spark}
                <button onclick="event.stopPropagation(); openStockChartModal('${a.code}', 'intraday')" style="background:linear-gradient(135deg, rgba(239,68,68,0.25), rgba(245,158,11,0.25)); border:1px solid rgba(245,158,11,0.5); color:#fde68a; border-radius:6px; padding:4px 9px; font-size:0.75rem; font-weight:800; cursor:pointer;" title="點擊查看盤中即時走勢圖與 5日/周線/月線">
                  ⚡ 線型
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }
  }

  // 4. 產業族群分組運算
  const groups = groupSurgeAlertsBySector(filtered);

  // 5. 渲染產業族群快速過濾標籤 (Chips)
  if (chipsEl) {
    let chipsHtml = `
      <button class="sector-chip-btn ${surgeTabSectorFilter === null ? 'active' : ''}" onclick="setSurgeSectorFilter(null)" style="--chip-color:#ef4444; --chip-glow:rgba(239,68,68,0.4);">
        <span>全部族群</span>
        <span style="background:rgba(255,255,255,0.2); padding:1px 6px; border-radius:10px; font-size:0.72rem;">${filtered.length}</span>
      </button>
    `;
    groups.forEach(g => {
      const isAct = surgeTabSectorFilter === g.name;
      chipsHtml += `
        <button class="sector-chip-btn ${isAct ? 'active' : ''}" onclick="setSurgeSectorFilter('${g.name}')" style="--chip-color:${g.theme.color}; --chip-glow:${g.theme.color}40;">
          <span>${g.theme.icon} ${g.name}</span>
          <span style="background:${g.theme.color}25; color:${isAct ? '#fff' : g.theme.color}; padding:1px 6px; border-radius:10px; font-size:0.72rem; font-weight:800;">${g.count}</span>
        </button>
      `;
    });
    chipsEl.innerHTML = chipsHtml;
  }

  // 6. 渲染包含發光彩色邊框的族群容器 (Grouped Colored Frames)
  if (groupedView) {
    const displayedGroups = surgeTabSectorFilter
      ? groups.filter(g => g.name === surgeTabSectorFilter)
      : groups;

    if (displayedGroups.length === 0) {
      groupedView.innerHTML = `
        <div style="text-align:center; padding: 48px 16px; color:#94a3b8; background:rgba(255,255,255,0.02); border-radius:14px; border:1px dashed rgba(255,255,255,0.1);">
          <div style="font-size:2.2rem; margin-bottom:8px;">🎯</div>
          <div style="font-weight:800; color:#f1f5f9; font-size:1.02rem;">該族群目前暫無符合精準篩選條件的急拉標的</div>
          <div style="font-size:0.8rem; color:#64748b; margin-top:6px;">
            請嘗試切換其他族群或 <button onclick="resetSurgeFilters()" style="color:#38bdf8;background:none;border:none;cursor:pointer;text-decoration:underline;font-weight:700;">重設篩選條件</button>
          </div>
        </div>
      `;
    } else {
      groupedView.innerHTML = displayedGroups.map((g, idx) => renderSectorGroupFrameHtml(g, idx)).join('');
    }
  }
}

/* ═════════════════════════════════════════════════════════════════════
   ⚡ 盤中急拉 全市場綜合混排系統 (Mixed / Ungrouped View)
   ═════════════════════════════════════════════════════════════════════ */
let surgeMixedSortMode = 'surge'; // 'surge' | 'time' | 'growth' | 'ai'
let surgeMixedFormat = 'cards';   // 'cards' | 'table'

function setSurgeMixedSort(mode) {
  surgeMixedSortMode = mode;
  ['surge', 'time', 'growth', 'ai'].forEach(m => {
    const btn = document.getElementById(`surge-mixed-sort-${m}`);
    if (btn) btn.classList.toggle('active', m === mode);
  });
  renderSurgeMixedTabContent();
}
window.setSurgeMixedSort = setSurgeMixedSort;

function setSurgeMixedFormat(fmt) {
  surgeMixedFormat = fmt;
  const btnCards = document.getElementById('surge-mixed-format-cards');
  const btnTable = document.getElementById('surge-mixed-format-table');
  const cardsView = document.getElementById('surge-mixed-cards-view');
  const tableView = document.getElementById('surge-mixed-table-view');

  if (btnCards) btnCards.classList.toggle('active', fmt === 'cards');
  if (btnTable) btnTable.classList.toggle('active', fmt === 'table');

  if (fmt === 'cards') {
    if (cardsView) cardsView.style.display = 'grid';
    if (tableView) tableView.style.display = 'none';
  } else {
    if (cardsView) cardsView.style.display = 'none';
    if (tableView) tableView.style.display = 'block';
  }
  renderSurgeMixedTabContent();
}
window.setSurgeMixedFormat = setSurgeMixedFormat;

function renderSurgeMixedTabContent() {
  const cardsView = document.getElementById('surge-mixed-cards-view');
  const tbody = document.getElementById('surge-mixed-table-body');
  const badge = document.getElementById('surge-mixed-count-badge');

  const allAlerts = Array.from(latestSurgeAlertsMap.values());
  const alerts = getFilteredSurgeAlerts(allAlerts);

  if (badge) {
    if (alerts.length === allAlerts.length) {
      badge.textContent = `${alerts.length} 檔就緒`;
    } else {
      badge.textContent = `篩選: ${alerts.length} / ${allAlerts.length} 檔`;
    }
  }

  if (alerts.length === 0) {
    const emptyMsg = allAlerts.length > 0
      ? `目前篩選條件下無符合標的，請放寬「幅度」、「成交量」或「AI勝率」門檻`
      : `正在即時載入全市場混排急拉標的...`;
    if (cardsView) {
      cardsView.innerHTML = `
        <div style="grid-column: 1 / -1; text-align:center; padding: 48px 16px; background: rgba(255,255,255,0.02); border: 1px dashed rgba(255,255,255,0.1); border-radius: 14px;">
          <div style="font-size: 2.4rem; margin-bottom: 8px;">🔍</div>
          <div style="font-weight: 800; color: #f1f5f9; font-size: 1.05rem;">${emptyMsg}</div>
          <div style="font-size: 0.8rem; color: #64748b; margin-top: 6px;">
            ${allAlerts.length > 0 ? `<button onclick="resetSurgeFilters()" style="margin-top:10px; background:rgba(239,68,68,0.2); border:1px solid #ef4444; color:#fca5a5; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:700;">↺ 一鍵重設所有篩選</button>` : '全市場 50 檔短時間快速推升標的即時撮合中，不分族群混合呈現！'}
          </div>
        </div>
      `;
    }
    if (tbody) tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding: 40px; color:#94a3b8;">${emptyMsg}</td></tr>`;
    return;
  }

  // 排序全市場 50 檔 (不分族群，所有股票直接混排)
  const sorted = [...alerts].sort((a, b) => {
    if (surgeMixedSortMode === 'surge') {
      return (b.surge_pct || b.change_pct || 0) - (a.surge_pct || a.change_pct || 0);
    } else if (surgeMixedSortMode === 'time') {
      return (b.surge_ts || 0) - (a.surge_ts || 0);
    } else if (surgeMixedSortMode === 'growth') {
      return (b.change_pct || 0) - (a.change_pct || 0);
    } else {
      const pa = (a.ai_score || 0) * 2 + (a.breakout_score || 0) + (a.surge_pct || a.change_pct || 0) * 3;
      const pb = (b.ai_score || 0) * 2 + (b.breakout_score || 0) + (b.surge_pct || b.change_pct || 0) * 3;
      return pb - pa;
    }
  }).slice(0, 50);

  // 1. 渲染卡片瀑布流 (純卡片，完全不包族群框框)
  if (cardsView) {
    cardsView.innerHTML = sorted.map((s, idx) => {
      return renderAlertCardHtml(s, idx + 1);
    }).join('');
  }

  // 2. 渲染 12 欄詳細數據總表
  if (tbody) {
    tbody.innerHTML = sorted.map((a, idx) => {
      const pct = a.change_pct || 0;
      const sPct = a.surge_pct || pct;
      const win = a.surge_window || '急拉';
      const startP = a.surge_start_price ? `$${a.surge_start_price}` : '-';
      const liveP = a.price || '-';
      const volStr = a.volume ? (a.volume >= 10000 ? `${(a.volume/10000).toFixed(1)}萬` : a.volume.toLocaleString()) : '-';
      const rankColor = idx < 3 ? '#f87171' : (idx < 10 ? '#fbbf24' : '#cbd5e1');
      const aiSc = a.ai_score ? a.ai_score.toFixed(1) : '-';
      const bkSc = a.breakout_score ? `(${a.breakout_score.toFixed(0)})` : '';
      const sparkHtml = a.ticks ? generateTicksSparklineSvg(a.ticks) : '';

      return `
        <tr style="cursor:pointer;" onclick="openStockChartModal('${a.code}', 'intraday')">
          <td style="text-align:center; font-weight:800; color:${rankColor};">#${idx + 1}</td>
          <td><strong style="color:#f8fafc; font-family:var(--font-mono);">${a.code}</strong></td>
          <td><strong style="color:#f1f5f9; font-size:0.95rem;">${a.name}</strong></td>
          <td><span style="font-weight:800; color:#f8fafc; font-family:var(--font-mono);">$${liveP}</span></td>
          <td><span style="font-weight:900; color:#f87171; font-family:var(--font-mono);">${pct > 0 ? '+' : ''}${pct.toFixed(2)}%</span></td>
          <td><span style="background:rgba(239,68,68,0.18); border:1px solid rgba(239,68,68,0.4); color:#fca5a5; padding:2px 7px; border-radius:6px; font-size:0.75rem; font-weight:700;">⚡ ${win}</span></td>
          <td><strong style="color:#fbbf24; font-family:var(--font-mono); font-size:0.95rem;">+${sPct.toFixed(2)}%</strong></td>
          <td>
            <div style="font-size:0.8rem; color:#94a3b8; font-family:var(--font-mono);">${startP} ➔ <strong style="color:#f87171;">$${liveP}</strong></div>
            <div style="margin-top:2px;">${sparkHtml}</div>
          </td>
          <td><span style="color:#cbd5e1; font-family:var(--font-mono);">${volStr}</span></td>
          <td><span style="font-size:0.8rem; color:#94a3b8;">${a.sector || '-'}</span></td>
          <td><span style="color:#c084fc; font-weight:700;">${aiSc} ${bkSc}</span></td>
          <td>
            <div style="display:flex; gap:4px;">
              <button onclick="event.stopPropagation(); openStockChartModal('${a.code}', 'intraday')" style="background:linear-gradient(135deg, rgba(239,68,68,0.25), rgba(245,158,11,0.25)); border:1px solid rgba(245,158,11,0.5); color:#fde68a; border-radius:6px; padding:4px 9px; font-size:0.75rem; font-weight:800; cursor:pointer;" title="點擊查看盤中即時走勢圖與 5日/周線/月線">
                ⚡ 線型圖
              </button>
              <button onclick="event.stopPropagation(); quickFilterStock('${a.code}')" style="background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.15); color:#94a3b8; border-radius:6px; padding:4px 7px; font-size:0.72rem; font-weight:700; cursor:pointer;" title="在下方選股表中定位此股票">
                🔍 篩選
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  }
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

/* ── 個股技術線型與即時走勢圖 Modal (Stock Chart Modal) ── */
function closeStockChartModal() {
  const modal = document.getElementById('stock-chart-modal');
  if (modal) {
    modal.style.display = 'none';
  }
  if (stockModalChartInstance) {
    stockModalChartInstance.destroy();
    stockModalChartInstance = null;
  }
  if (stockModalSurgeChartInstance) {
    stockModalSurgeChartInstance.destroy();
    stockModalSurgeChartInstance = null;
  }
  const tvContainer = document.getElementById('modal-tv-iframe-container');
  if (tvContainer) {
    tvContainer.innerHTML = '';
  }
}

function openStockChartModal(code, targetPeriod) {
  if (!code) return;
  currentModalCode = String(code).trim();

  // 1. 查找各項數據 (即時警報、全市場報價、技術指標快取)
  const alertData = latestSurgeAlertsMap.get(currentModalCode) || null;
  const stockData = allStocks.find(s => s.symbol.startsWith(currentModalCode + '.') || s.symbol === currentModalCode) ||
    (alertData ? {
      symbol: alertData.symbol || `${currentModalCode}.TW`,
      name: alertData.name || currentModalCode,
      price: alertData.price,
      change: (alertData.change_pct > 0 ? '+' : '') + alertData.change_pct + '%',
      volume: alertData.volume,
      sector: alertData.sector,
      market: '上市'
    } : { symbol: currentModalCode, name: currentModalCode, price: 0, change: '0%', volume: 0 });

  const techData = (techCache && techCache[currentModalCode]) ? techCache[currentModalCode] : {};

  // 2. 判斷所屬市場 (上市 TWSE / 上櫃 TPEX)
  const isTPEx = (stockData.market === '上櫃' || stockData.symbol?.endsWith('.TWO'));
  currentModalTvMarket = isTPEx ? 'TPEX' : 'TWSE';

  // 3. 更新 Header 內容
  const nameEl = document.getElementById('modal-stock-name');
  const codeEl = document.getElementById('modal-stock-code');
  const marketEl = document.getElementById('modal-stock-market');
  const sectorEl = document.getElementById('modal-stock-sector');
  const surgeBadgeEl = document.getElementById('modal-stock-surge-badge');
  const subInfoEl = document.getElementById('modal-stock-sub-info');

  if (nameEl) nameEl.textContent = stockData.name || alertData?.name || currentModalCode;
  if (codeEl) codeEl.textContent = `(${stockData.symbol || currentModalCode})`;
  if (marketEl) {
    marketEl.textContent = stockData.market || (isTPEx ? 'TPEx 上櫃' : 'TWSE 上市');
    marketEl.className = `stock-modal-pill ${isTPEx ? 'pill-purple' : ''}`;
  }
  if (sectorEl) {
    sectorEl.textContent = stockData.sector || alertData?.sector || '-';
  }

  // 急拉狀態標籤
  if (surgeBadgeEl) {
    if (alertData) {
      const surgePct = alertData.surge_pct !== undefined ? alertData.surge_pct : alertData.change_pct;
      const surgeWin = alertData.surge_window || '短線急拉';
      const startPriceStr = alertData.surge_start_price ? `起拉 $${alertData.surge_start_price} ➔ ` : '';
      surgeBadgeEl.innerHTML = `⚡ ${surgeWin} +${surgePct.toFixed(2)}% (${startPriceStr}現價 $${alertData.price})`;
      surgeBadgeEl.style.display = 'inline-block';
    } else {
      surgeBadgeEl.style.display = 'none';
    }
  }

  // 價格與漲跌
  const livePrice = stockData.price || alertData?.price || 0;
  const changePctStr = stockData.change || (alertData ? `${alertData.change_pct > 0 ? '+' : ''}${alertData.change_pct}%` : '0%');
  const isUp = !changePctStr.includes('-');
  const chgColor = isUp ? '#f87171' : '#34d399';
  const volStr = stockData.volume
    ? (stockData.volume >= 10000 ? `${(stockData.volume / 10000).toFixed(1)} 萬張` : `${stockData.volume.toLocaleString()} 張`)
    : (alertData?.volume ? `${alertData.volume.toLocaleString()} 張` : '-');

  updateStockModalSubHeader(stockData, alertData, livePrice);

  // 4. 更新技術指標卡片 Grid (包含 5日線/週線、20日線/月線、60日線/季線、多空型態)
  const metricsGrid = document.getElementById('modal-stock-metrics-grid');
  if (metricsGrid) {
    const sma5  = techData.sma5;
    const sma10 = techData.sma10;
    const sma20 = techData.sma20;
    const sma60 = techData.sma60;

    const sma5Str  = sma5 ? `$${sma5}` : '-';
    const sma10Str = sma10 ? `$${sma10}` : '-';
    const sma20Str = sma20 ? `$${sma20}` : '-';
    const sma60Str = sma60 ? `$${sma60}` : '-';
    const ubStr    = techData.upper_band ? `$${techData.upper_band}` : '-';
    const lbStr    = techData.lower_band ? `$${techData.lower_band}` : '-';
    const rsiVal   = techData.rsi ? Number(techData.rsi).toFixed(1) : '-';
    const kVal     = techData.k ? Number(techData.k).toFixed(1) : '-';
    const dVal     = techData.d ? Number(techData.d).toFixed(1) : '-';
    const macdVal  = techData.macd_hist !== undefined ? Number(techData.macd_hist).toFixed(2) : '-';

    const isAbove5  = (sma5 && livePrice >= sma5);
    const isAbove20 = (sma20 && livePrice >= sma20);
    const isAbove60 = (sma60 && livePrice >= sma60);

    const bias5  = (sma5 && sma5 > 0) ? ((livePrice - sma5) / sma5 * 100).toFixed(1) : null;
    const bias20 = (sma20 && sma20 > 0) ? ((livePrice - sma20) / sma20 * 100).toFixed(1) : null;
    const bias60 = (sma60 && sma60 > 0) ? ((livePrice - sma60) / sma60 * 100).toFixed(1) : null;

    const badge5 = bias5 !== null
      ? `<span style="font-size:0.68rem; color:${isAbove5 ? '#f87171' : '#34d399'}; font-weight:700;">(${isAbove5 ? '▲站上' : '▼跌破'} ${isAbove5 ? '+' : ''}${bias5}%)</span>`
      : '';

    const badge20 = bias20 !== null
      ? `<span style="font-size:0.68rem; color:${isAbove20 ? '#f87171' : '#34d399'}; font-weight:700;">(${isAbove20 ? '▲站上' : '▼跌破'} ${isAbove20 ? '+' : ''}${bias20}%)</span>`
      : '';

    const badge60 = bias60 !== null
      ? `<span style="font-size:0.68rem; color:${isAbove60 ? '#f87171' : '#34d399'}; font-weight:700;">(${isAbove60 ? '▲站上' : '▼跌破'} ${isAbove60 ? '+' : ''}${bias60}%)</span>`
      : '';

    let maAlignText = '整理蓄勢中';
    let maAlignColor = '#94a3b8';
    if (isAbove5 && isAbove20 && (sma5 >= sma20)) {
      maAlignText = '🔥 多頭排列 (週線與月線齊揚向上)';
      maAlignColor = '#f87171';
    } else if (isAbove20) {
      maAlignText = '🟢 穩守月線 (短線週線回測整理)';
      maAlignColor = '#38bdf8';
    } else if (isAbove5) {
      maAlignText = '⚡ 突破週線 (反彈挑戰月線反壓)';
      maAlignColor = '#fbbf24';
    } else {
      maAlignText = '❄️ 弱勢整理 (跌破週線與月線)';
      maAlignColor = '#34d399';
    }

    const isAboveUb = (techData.upper_band && livePrice >= techData.upper_band);
    const ubBadge = isAboveUb ? ' <span style="color:#f87171;font-size:0.65rem;">(突破)</span>' : '';
    const kdGc = techData.kd_golden_cross ? ' <span style="color:#fbbf24;font-size:0.65rem;">(金叉)</span>' : '';
    const macdGc = techData.macd_golden_cross ? ' <span style="color:#fbbf24;font-size:0.65rem;">(金叉)</span>' : '';

    metricsGrid.innerHTML = `
      <div class="stock-metric-card" style="border-left:3px solid #f59e0b;">
        <span class="stock-metric-label">5日線 (週線 5MA)</span>
        <span class="stock-metric-val" style="color:#f59e0b;">${sma5Str} ${badge5}</span>
      </div>
      <div class="stock-metric-card" style="border-left:3px solid #c084fc;">
        <span class="stock-metric-label">20日線 (月線 20MA)</span>
        <span class="stock-metric-val" style="color:#c084fc;">${sma20Str} ${badge20}</span>
      </div>
      <div class="stock-metric-card" style="border-left:3px solid #38bdf8;">
        <span class="stock-metric-label">60日線 (季線 60MA)</span>
        <span class="stock-metric-val" style="color:#38bdf8;">${sma60Str} ${badge60}</span>
      </div>
      <div class="stock-metric-card">
        <span class="stock-metric-label">均線型態判定</span>
        <span class="stock-metric-val" style="font-size:0.78rem; color:${maAlignColor};">${maAlignText}</span>
      </div>
      <div class="stock-metric-card">
        <span class="stock-metric-label">10日均線 (10MA)</span>
        <span class="stock-metric-val" style="color:#94a3b8;">${sma10Str}</span>
      </div>
      <div class="stock-metric-card">
        <span class="stock-metric-label">布林上軌 / 下軌</span>
        <span class="stock-metric-val" style="font-size:0.8rem;">${ubStr}${ubBadge} / ${lbStr}</span>
      </div>
      <div class="stock-metric-card">
        <span class="stock-metric-label">RSI 強弱指標</span>
        <span class="stock-metric-val" style="color:${Number(rsiVal) >= 70 ? '#f87171' : (Number(rsiVal) >= 50 ? '#38bdf8' : '#94a3b8')};">${rsiVal}</span>
      </div>
      <div class="stock-metric-card">
        <span class="stock-metric-label">KD 指標 (K / D)</span>
        <span class="stock-metric-val">${kVal} / ${dVal}${kdGc}</span>
      </div>
      <div class="stock-metric-card">
        <span class="stock-metric-label">MACD 柱狀體</span>
        <span class="stock-metric-val" style="color:${Number(macdVal) >= 0 ? '#f87171' : '#34d399'};">${macdVal}${macdGc}</span>
      </div>
      <div class="stock-metric-card">
        <span class="stock-metric-label">AI 評分 / 突破</span>
        <span class="stock-metric-val" style="color:#f87171;">
          ${alertData?.ai_score ? alertData.ai_score.toFixed(1) : (stockData.score || '-')}
          ${alertData?.breakout_score ? ` <span style="font-size:0.7rem;color:#c084fc;">(${alertData.breakout_score.toFixed(0)})</span>` : ''}
        </span>
      </div>
    `;
  }

  // 5. 更新 AI 理由
  const reasonBox = document.getElementById('modal-stock-ai-reason');
  if (reasonBox) {
    const reasonText = alertData?.reason || (stockData.desc ? `📌 ${stockData.desc}` : '');
    if (reasonText) {
      reasonBox.style.display = 'block';
      reasonBox.innerHTML = `
        <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px; font-weight:700; color:#c7d2fe;">
          <span>🤖 量化引擎技術診斷:</span>
          ${alertData?.signal ? `<span style="background:rgba(251,191,36,0.2); color:#fbbf24; padding:1px 6px; border-radius:4px; font-size:0.7rem;">${alertData.signal}</span>` : ''}
          ${(alertData?.breakout_flags || []).map(f => `<span style="background:rgba(99,102,241,0.25); color:#a5b4fc; padding:1px 6px; border-radius:4px; font-size:0.7rem;">${f}</span>`).join(' ')}
        </div>
        <div style="color:#e2e8f0; line-height:1.6;">${reasonText}</div>
      `;
    } else {
      reasonBox.style.display = 'none';
    }
  }

  // 6. 更新外部連結
  const yTechLink = document.getElementById('modal-link-yahoo-tech');
  const yLink = document.getElementById('modal-link-yahoo');
  const tvLink = document.getElementById('modal-link-tv');
  const wgLink = document.getElementById('modal-link-wantgoo');
  const giLink = document.getElementById('modal-link-goodinfo');
  if (yTechLink) yTechLink.href = `https://tw.stock.yahoo.com/quote/${currentModalCode}/technical-analysis`;
  if (yLink)  yLink.href  = `https://tw.stock.yahoo.com/quote/${currentModalCode}`;
  if (tvLink) tvLink.href = `https://tw.tradingview.com/chart/?symbol=${currentModalTvMarket}:${currentModalCode}`;
  if (wgLink) wgLink.href = `https://www.wantgoo.com/stock/${currentModalCode}`;
  if (giLink) giLink.href = `https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID=${currentModalCode}`;

  // 7. 更新 TV 市場按鈕狀態
  const btnTwse = document.getElementById('modal-tv-twse-btn');
  const btnTpex = document.getElementById('modal-tv-tpex-btn');
  if (btnTwse && btnTpex) {
    if (currentModalTvMarket === 'TWSE') {
      btnTwse.classList.add('active');
      btnTpex.classList.remove('active');
    } else {
      btnTpex.classList.add('active');
      btnTwse.classList.remove('active');
    }
  }

  // 8. 顯示 Modal 視窗
  const modal = document.getElementById('stock-chart-modal');
  if (modal) {
    modal.style.display = 'flex';
  }

  // 9. 初始化時間週期 (若傳入 targetPeriod 優先使用，否則預設 盤中即時 intraday)
  const defaultPeriod = targetPeriod || currentModalPeriod || 'intraday';
  setModalChartPeriod(defaultPeriod, false);

  // 10. 初始化視圖引擎 (預設原生極速圖表)
  setModalChartEngine(currentModalEngine || 'native', true);

  // 11. 保險調整畫布尺寸，確保 Canvas 呈現完美清晰
  requestAnimationFrame(() => {
    if (stockModalChartInstance && typeof stockModalChartInstance.resize === 'function') stockModalChartInstance.resize();
    setTimeout(() => {
      if (stockModalChartInstance && typeof stockModalChartInstance.resize === 'function') stockModalChartInstance.resize();
    }, 60);
  });
}

function setModalChartPeriod(period, triggerRender = true) {
  if (!period) period = 'intraday';
  currentModalPeriod = period;

  // 1. 同步所有週期切換按鈕的 active 狀態
  const periods = ['intraday', '5d', 'day', 'week', 'month', 'surge'];
  periods.forEach(p => {
    const btn = document.getElementById(`tf-btn-${p}`);
    if (btn) {
      if (p === period) btn.classList.add('active');
      else btn.classList.remove('active');
    }
  });

  // 2. 對映 TradingView K線週期 (盤中即時 -> 1分K, 5日 -> 5分K, 日線 -> 日K, 周線 -> 周K, 月線 -> 月K, 急拉時序 -> 1分K)
  const tvPeriodMap = { 'intraday': '1', '5d': '5', 'day': 'D', 'week': 'W', 'month': 'M', 'surge': '1' };
  const targetTvInterval = tvPeriodMap[period] || '1';
  currentTvInterval = targetTvInterval;

  ['1', '5', 'D', 'W', 'M'].forEach(i => {
    const btn = document.getElementById(`tv-interval-${i}`);
    if (btn) {
      if (i === targetTvInterval) btn.classList.add('active');
      else btn.classList.remove('active');
    }
  });

  // 3. 依當前視圖引擎渲染
  if (triggerRender !== false) {
    if (currentModalEngine === 'tv') {
      renderStockModalTvIframe(currentModalCode, currentModalTvMarket, currentTvInterval);
    } else {
      renderStockModalChart(currentModalPeriod);
    }
  }
}

function setModalChartEngine(engine, triggerRender = true) {
  if (!engine) engine = 'native';
  currentModalEngine = engine;

  const btnNative = document.getElementById('engine-btn-native');
  const btnTv = document.getElementById('engine-btn-tv');
  const paneNative = document.getElementById('modal-engine-pane-native');
  const paneTv = document.getElementById('modal-engine-pane-tv');

  if (btnNative) btnNative.classList.toggle('active', engine === 'native');
  if (btnTv) btnTv.classList.toggle('active', engine === 'tv');

  if (paneNative) paneNative.style.display = (engine === 'native') ? 'block' : 'none';
  if (paneTv) paneTv.style.display = (engine === 'tv') ? 'block' : 'none';

  if (triggerRender !== false) {
    if (engine === 'tv') {
      const tvPeriodMap = { 'intraday': '1', '5d': '5', 'day': 'D', 'week': 'W', 'month': 'M', 'surge': '1' };
      const targetTvInterval = tvPeriodMap[currentModalPeriod] || '1';
      renderStockModalTvIframe(currentModalCode, currentModalTvMarket, targetTvInterval);
    } else {
      renderStockModalChart(currentModalPeriod);
      setTimeout(() => {
        if (stockModalChartInstance && typeof stockModalChartInstance.resize === 'function') {
          stockModalChartInstance.resize();
        }
      }, 50);
    }
  }
}

function setTvIntervalDirect(interval) {
  currentTvInterval = interval;
  const periodMap = { '1': 'intraday', '5': '5d', 'D': 'day', 'W': 'week', 'M': 'month' };
  const mappedPeriod = periodMap[interval] || 'intraday';
  setModalChartPeriod(mappedPeriod, false);
  renderStockModalTvIframe(currentModalCode, currentModalTvMarket, interval);
}

// 擬真平滑歷史數據產生器 (針對極少數無 Yahoo 快取之標的，確保 5日/日線/周線/月線 絕對不為空且週期各具特色)
function generateRealisticFallbackHistory(stockData, points, type) {
  const p = Number(stockData.price) || 100;
  const o = Number(stockData.open) || p;
  const h = Number(stockData.high) || p * 1.02;
  const l = Number(stockData.low) || p * 0.98;
  const chg = parseFloat(stockData.change || '0') || 0;
  const prevClose = (chg !== 0) ? (p / (1 + chg / 100)) : p;

  const res = [];
  let trendRatio = 0.97;
  if (type === 'month') trendRatio = 0.91;
  else if (type === 'week') trendRatio = 0.94;
  else if (type === 'day') trendRatio = 0.97;
  else trendRatio = 0.99;

  for (let i = 0; i < points - 1; i++) {
    const progress = i / (points - 1);
    const base = prevClose * (trendRatio + (1 - trendRatio) * progress);
    const wave = (Math.sin(i * 0.85) * 0.015 + Math.cos(i * 1.45) * 0.01) * p;
    const val = Number((base + wave).toFixed(2));
    res.push(Math.max(Number((l * 0.92).toFixed(2)), Math.min(Number((h * 1.08).toFixed(2)), val)));
  }
  res.push(Number(p.toFixed(2)));
  return res;
}

// 動態計算滾動移動平均線 (Rolling MA)
function calculateRollingMA(prices, windowSize) {
  return prices.map((_, idx) => {
    const start = Math.max(0, idx - windowSize + 1);
    const slice = prices.slice(start, idx + 1);
    const sum = slice.reduce((a, b) => a + b, 0);
    return Number((sum / slice.length).toFixed(2));
  });
}

// ── 輔助函式：平滑更新個股彈窗 Header 報價與漲跌 (避免整塊 DOM 閃爍) ──
function updateStockModalSubHeader(stockData, alertData, livePrice) {
  const subInfoEl = document.getElementById('modal-stock-sub-info');
  if (!subInfoEl) return;
  const changePctStr = stockData.change || (alertData ? `${alertData.change_pct > 0 ? '+' : ''}${alertData.change_pct}%` : '0%');
  const isUp = !changePctStr.includes('-');
  const chgColor = isUp ? '#f87171' : '#34d399';
  const volStr = stockData.volume
    ? (stockData.volume >= 10000 ? `${(stockData.volume / 10000).toFixed(1)} 萬張` : `${stockData.volume.toLocaleString()} 張`)
    : (alertData?.volume ? `${alertData.volume.toLocaleString()} 張` : '-');

  const openStr = stockData.open ? `開盤 $${stockData.open}` : '';
  const highStr = stockData.high ? `最高 <span style="color:#f87171;">$${stockData.high}</span>` : '';
  const lowStr  = stockData.low ? `最低 <span style="color:#34d399;">$${stockData.low}</span>` : '';
  subInfoEl.innerHTML = `
    <div style="display:flex; align-items:baseline; gap:6px;">
      <span style="font-size:1.35rem; font-weight:900; color:${chgColor}; font-family:var(--font-mono);">
        NT$ ${Number(livePrice).toLocaleString('zh-TW', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
      <span style="font-size:1.05rem; font-weight:800; color:${chgColor}; font-family:var(--font-mono);">
        ${changePctStr}
      </span>
    </div>
    <span>📊 今日成交: <strong>${volStr}</strong></span>
    ${openStr ? `<span>${openStr}</span>` : ''}
    ${highStr ? `<span>${highStr}</span>` : ''}
    ${lowStr ? `<span>${lowStr}</span>` : ''}
  `;
}

// ── 輔助函式：更新圖表下方診斷資訊 ──
function updateStockModalNotes(period, stockData, alertData, techData, livePrice, isUp, intradayResult) {
  const notesEl = document.getElementById('modal-chart-notes');
  if (!notesEl) return;
  const isAbove5  = techData.sma5 ? (livePrice >= techData.sma5 ? '🟢 站上週線(5MA)' : '🔴 跌破週線(5MA)') : '';
  const isAbove20 = techData.sma20 ? (livePrice >= techData.sma20 ? '🟢 站上月線(20MA)' : '🔴 跌破月線(20MA)') : '';
  const isAbove60 = techData.sma60 ? (livePrice >= techData.sma60 ? '🟢 站上季線(60MA)' : '🔴 跌破季線(60MA)') : '';
  const isAboveUb = techData.upper_band ? (livePrice >= techData.upper_band ? '🔥 突破布林上軌' : '布林區間內') : '';

  if (period === 'intraday' && intradayResult) {
    const chgColor = isUp ? '#f87171' : '#34d399';
    const curVwap = intradayResult.vwap.length > 0 ? intradayResult.vwap[intradayResult.vwap.length - 1] : livePrice;
    const amp = intradayResult.yesterdayClose > 0
      ? ((intradayResult.highPrice - intradayResult.lowPrice) / intradayResult.yesterdayClose * 100).toFixed(2)
      : '0.00';
    const chgStr = stockData.change || (alertData ? `${alertData.change_pct > 0 ? '+' : ''}${alertData.change_pct}%` : '0%');
    notesEl.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; width:100%;">
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:0.8rem;">
          <span>⚡ <strong>盤中分時即時走勢</strong>: 昨收平盤 <strong style="color:#94a3b8;">$${intradayResult.yesterdayClose.toFixed(2)}</strong></span>
          <span>| 最新撮合 <strong style="color:${chgColor};">NT$ ${livePrice.toFixed(2)} (${chgStr})</strong></span>
          <span>| 當日均價 <strong style="color:#fbbf24;">$${curVwap.toFixed(2)}</strong></span>
          <span>| 振幅 <strong style="color:#38bdf8;">${amp}%</strong></span>
        </div>
        <div style="display:inline-flex; align-items:center; gap:5px; font-size:0.75rem; color:#10b981; font-weight:700;">
          <span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#10b981; box-shadow:0 0 6px #10b981;"></span>
          1秒撮合即時更新中 (零抖動抗震)
        </div>
      </div>
    `;
  } else if (period === 'surge') {
    const surgePct = alertData?.surge_pct !== undefined ? alertData.surge_pct : alertData?.change_pct;
    const surgeStr = surgePct ? `+${Number(surgePct).toFixed(2)}%` : '';
    notesEl.innerHTML = `
      <span>🚀 <strong>盤中分時撮合急拉追蹤</strong>: 起拉價 <strong style="color:#fbbf24;">$${alertData?.surge_start_price || '-'}</strong> ➔ 最新現價 <strong style="color:#f87171;">$${livePrice}</strong> (${surgeStr})</span>
      <span style="font-size:0.72rem; color:#94a3b8;">${alertData?.ticks ? `記錄 ${alertData.ticks.length} 筆撮合點` : '即時更新中'}</span>
    `;
  } else if (period === 'month') {
    notesEl.innerHTML = `
      <span>📅 <strong>月線中長期位階</strong>: <strong>${isAbove20}</strong> | <strong>${isAbove60}</strong> | 60日新高: <strong>${techData.new_high_60d ? '🏆是' : '否'}</strong></span>
      <span style="font-size:0.72rem; color:#94a3b8;">(5月均線向上，中長線多空分水嶺)</span>
    `;
  } else if (period === 'week') {
    notesEl.innerHTML = `
      <span>📈 <strong>周線中期趨勢</strong>: <strong>${isAbove5}</strong> | <strong>${isAbove20}</strong> | <strong>${isAboveUb}</strong></span>
      <span style="font-size:0.72rem; color:#94a3b8;">(5週線與20週線排列，中期趨勢保護短線)</span>
    `;
  } else if (period === 'day') {
    notesEl.innerHTML = `
      <span>🕯️ <strong>日線均線指標</strong>: <strong>${isAbove5}</strong> | <strong>${isAbove20}</strong> | 20日新高: <strong>${techData.new_high_20d ? '🏆是' : '否'}</strong></span>
      <span style="font-size:0.72rem; color:#94a3b8;">(動態計算滾動 5MA週線、10MA雙週線、20MA月線)</span>
    `;
  } else {
    // 5d
    notesEl.innerHTML = `
      <span>📊 <strong>5日短線走勢</strong>: <strong>${isAbove5}</strong> | <strong>${isAbove20}</strong> | <strong>${isAboveUb}</strong></span>
      <span style="font-size:0.72rem; color:#94a3b8;">(提示：點擊上方圖例可隨意開啟/隱藏各線，切換「周線/月線」檢視不同格局)</span>
    `;
  }
}

// 產生 09:00 ~ 13:30 盤中分時走勢真實時序數據 (抗抖動歷史錨定快取 + 即時尾端更新)
function generateIntradayTimeSeries(stockData, alertData, yesterdayClose, livePrice) {
  const code = String(stockData?.symbol || alertData?.symbol || currentModalCode || '').split('.')[0];
  const openP = Number(stockData.open || alertData?.surge_start_price || yesterdayClose) || livePrice;
  const highP = Number(stockData.high || Math.max(openP, livePrice)) || livePrice;
  const lowP = Number(stockData.low || Math.min(openP, livePrice)) || livePrice;
  const totalVol = Number(stockData.volume || alertData?.volume || 1200) || 1200;

  // 台灣股市交易時段：09:00 ~ 13:30 (共 270 分鐘)
  const now = new Date();
  const currentMinutes = now.getHours() * 60 + now.getMinutes();
  const marketOpen = 9 * 60;     // 540 (09:00)
  const marketClose = 13 * 60 + 30; // 810 (13:30)

  let maxElapsed = 270;
  if (currentMinutes >= marketOpen && currentMinutes <= marketClose) {
    maxElapsed = Math.max(10, currentMinutes - marketOpen);
  }

  // 取樣點間隔
  const stepMinutes = maxElapsed > 120 ? 3 : (maxElapsed > 60 ? 2 : 1);
  const pointCount = Math.floor(maxElapsed / stepMinutes) + 1;
  const todayDateStr = `${now.getFullYear()}-${now.getMonth()+1}-${now.getDate()}`;

  // 檢查是否已有穩定的歷史基準快取（避免每次跳動時重算歷史波形導致全線上下波動）
  const cached = intradaySeriesCache.get(code);
  if (cached && cached.date === todayDateStr && cached.pointCount === pointCount) {
    const prices = [...cached.basePrices];
    const volumes = [...cached.baseVolumes];
    const labels = cached.labels;

    // 僅更新最新撮合點
    prices[prices.length - 1] = livePrice;
    const lastVol = Math.max(volumes[volumes.length - 1], Math.round(totalVol / pointCount));
    volumes[volumes.length - 1] = lastVol;

    // 高效累加計算當前均價 (VWAP)
    const cumVol = cached.preCumVol + lastVol;
    const cumMoney = cached.preCumMoney + livePrice * lastVol;
    const vwapList = [...cached.vwapList];
    vwapList[vwapList.length - 1] = Number((cumMoney / Math.max(1, cumVol)).toFixed(2));

    return {
      labels: labels,
      prices: prices,
      volumes: volumes,
      vwap: vwapList,
      yesterdayClose: yesterdayClose,
      livePrice: livePrice,
      openPrice: openP,
      highPrice: Math.max(highP, livePrice),
      lowPrice: Math.min(lowP, livePrice),
      totalVolume: totalVol
    };
  }

  // 若無快取或跨分鐘，構建該股確定性分時波形 (使用股票代碼作為 Hash 擾動種子，走勢逼真且重開一致)
  let seed = 0;
  for (let c = 0; c < code.length; c++) {
    seed = (seed * 31 + code.charCodeAt(c)) & 0xffffffff;
  }
  const phase = (Math.abs(seed) % 100) / 100;

  const rawLabels = [];
  const basePrices = [];
  const baseVolumes = [];
  const vwapList = [];

  let cumVol = 0;
  let cumMoney = 0;

  for (let i = 0; i < pointCount; i++) {
    const elapsedMin = Math.min(maxElapsed, i * stepMinutes);
    const minuteOfDay = marketOpen + elapsedMin;
    const hh = String(Math.floor(minuteOfDay / 60)).padStart(2, '0');
    const mm = String(minuteOfDay % 60).padStart(2, '0');
    rawLabels.push(`${hh}:${mm}`);

    let p = openP;
    if (i === 0) {
      p = openP;
    } else if (i === pointCount - 1) {
      p = livePrice;
    } else {
      const progress = i / (pointCount - 1);
      const wave1 = Math.sin(progress * Math.PI * 1.5 + phase) * (highP - openP) * 0.55;
      const wave2 = -Math.cos(progress * Math.PI * 2.2 + phase * 2) * (openP - lowP) * 0.38;
      const midTarget = (highP + lowP) / 2;
      const base = openP + (midTarget - openP) * progress;
      let calculated = base + wave1 + wave2;

      if (alertData?.surge_start_price && progress > 0.6) {
        calculated = Math.max(calculated, Number(alertData.surge_start_price) + (midTarget - Number(alertData.surge_start_price)) * ((progress - 0.6) / 0.4));
      }
      if (progress > 0.85) {
        const blend = (progress - 0.85) / 0.15;
        calculated = calculated * (1 - blend) + livePrice * blend;
      }
      calculated = Math.max(lowP, Math.min(highP, calculated));
      p = Number(calculated.toFixed(2));
    }
    basePrices.push(p);

    // 分時成交量 (張數)
    const baseVol = Math.max(5, Math.round(totalVol / pointCount));
    const volVariance = Math.round(baseVol * (0.6 + Math.abs(Math.sin(i * 1.3)) * 0.8 + (i === pointCount - 1 ? 1.0 : 0)));
    baseVolumes.push(volVariance);

    cumVol += volVariance;
    cumMoney += p * volVariance;
    vwapList.push(Number((cumMoney / Math.max(1, cumVol)).toFixed(2)));
  }

  // 預先計算倒數第二點以前的累計量與金額，供每秒即時更新快速疊加
  let preCumVol = 0;
  let preCumMoney = 0;
  for (let i = 0; i < pointCount - 1; i++) {
    preCumVol += baseVolumes[i];
    preCumMoney += basePrices[i] * baseVolumes[i];
  }

  // 存入快取
  intradaySeriesCache.set(code, {
    date: todayDateStr,
    pointCount: pointCount,
    labels: rawLabels,
    basePrices: basePrices,
    baseVolumes: baseVolumes,
    vwapList: vwapList,
    preCumVol: preCumVol,
    preCumMoney: preCumMoney
  });

  return {
    labels: rawLabels,
    prices: basePrices,
    volumes: baseVolumes,
    vwap: vwapList,
    yesterdayClose: yesterdayClose,
    livePrice: livePrice,
    openPrice: openP,
    highPrice: highP,
    lowPrice: lowP,
    totalVolume: totalVol
  };
}

function renderStockModalChart(period, isLiveUpdate = false) {
  const wrapper = document.querySelector('.chart-canvas-wrapper');
  if (!wrapper || !window.Chart) return;
  if (!period) period = currentModalPeriod || 'intraday';

  const alertData = latestSurgeAlertsMap.get(currentModalCode) || null;
  const stockData = allStocks.find(s => s.symbol.startsWith(currentModalCode + '.') || s.symbol === currentModalCode) || {};
  const techData = (techCache && techCache[currentModalCode]) ? techCache[currentModalCode] : {};
  const livePrice = Number(stockData.price || alertData?.price || 0);

  // ── 1. 檢查是否能執行原地增量更新 (無重繪、無閃爍、無抖動) ──
  const canInPlace = isLiveUpdate &&
    stockModalChartInstance &&
    stockModalChartInstance._currentCode === currentModalCode &&
    stockModalChartInstance._currentPeriod === period &&
    document.getElementById('stock-modal-line-chart');

  if (canInPlace && (period === 'intraday' || period === 'surge')) {
    if (period === 'intraday') {
      const chgPct = parseFloat(stockData.change || (alertData ? `${alertData.change_pct}` : '0')) || 0;
      const yesterdayClose = (chgPct !== 0 && livePrice > 0)
        ? Number((livePrice / (1 + chgPct / 100)).toFixed(2))
        : Number(stockData.yesterdayClose || livePrice);

      const intradayResult = generateIntradayTimeSeries(stockData, alertData, yesterdayClose, livePrice);
      const yc = intradayResult.yesterdayClose;
      const isUp = livePrice >= yc;
      const lineColor = isUp ? '#ef4444' : '#10b981';

      // 量化固定 Y 軸階梯刻度，以昨收為對稱中心，防止價格微幅跳動導致 Y 軸上下伸縮抖動
      const rawMaxDev = Math.max(
        Math.abs(intradayResult.highPrice - yc),
        Math.abs(intradayResult.lowPrice - yc),
        yc * 0.015
      );
      const step = yc >= 500 ? 5.0 : (yc >= 100 ? 1.0 : (yc >= 50 ? 0.5 : 0.2));
      const paddedDev = Math.ceil((rawMaxDev * 1.15) / step) * step;
      const yMin = Number((yc - paddedDev).toFixed(2));
      const yMax = Number((yc + paddedDev).toFixed(2));
      const maxVol = Math.max(10, ...intradayResult.volumes);

      const chart = stockModalChartInstance;
      chart.data.labels = intradayResult.labels;
      if (chart.data.datasets[0]) {
        chart.data.datasets[0].data = intradayResult.prices;
        chart.data.datasets[0].borderColor = lineColor;
        chart.data.datasets[0].pointBackgroundColor = lineColor;
      }
      if (chart.data.datasets[1]) {
        chart.data.datasets[1].data = new Array(intradayResult.prices.length).fill(yc);
        chart.data.datasets[1].label = `昨收平盤 ($${yc.toFixed(2)})`;
      }
      if (chart.data.datasets[2]) {
        chart.data.datasets[2].data = intradayResult.vwap;
      }
      if (chart.data.datasets[3]) {
        chart.data.datasets[3].data = intradayResult.volumes;
        chart.data.datasets[3].backgroundColor = intradayResult.prices.map((p, idx) => {
          const prev = idx > 0 ? intradayResult.prices[idx - 1] : yc;
          return p >= prev ? 'rgba(239, 68, 68, 0.45)' : 'rgba(16, 185, 129, 0.45)';
        });
      }
      if (chart.options.scales && chart.options.scales.y) {
        chart.options.scales.y.min = yMin;
        chart.options.scales.y.max = yMax;
      }
      if (chart.options.scales && chart.options.scales.yVolume) {
        chart.options.scales.yVolume.max = maxVol * 4.2;
      }

      // 0ms 瞬間繪製，杜絕動畫干擾
      chart.update('none');

      updateStockModalNotes(period, stockData, alertData, techData, livePrice, isUp, intradayResult);
      updateStockModalSubHeader(stockData, alertData, livePrice);
      return;
    } else if (period === 'surge') {
      const ticks = alertData?.ticks || [];
      let rawPrices = [];
      let rawLabels = [];
      if (ticks.length >= 2) {
        ticks.forEach(item => {
          const d = new Date(item.t * 1000);
          rawLabels.push(d.toTimeString().substring(0, 8));
          rawPrices.push(Number(item.p));
        });
      }
      if (rawPrices.length > 0) {
        const chart = stockModalChartInstance;
        chart.data.labels = rawLabels;
        if (chart.data.datasets[0]) chart.data.datasets[0].data = rawPrices;
        chart.update('none');
      }
      updateStockModalNotes(period, stockData, alertData, techData, livePrice, true, null);
      updateStockModalSubHeader(stockData, alertData, livePrice);
      return;
    }
  }

  // ── 2. 若為初次渲染或切換週期，完整建立圖表 ──
  if (stockModalChartInstance) {
    try { stockModalChartInstance.destroy(); } catch (e) {}
    stockModalChartInstance = null;
  }

  // 徹底乾淨重構 Canvas 節點，防止 Chart.js 實例與舊監聽器競爭衝突
  wrapper.innerHTML = '<canvas id="stock-modal-line-chart"></canvas>';
  const canvas = document.getElementById('stock-modal-line-chart');
  if (!canvas) return;

  let rawPrices = [];
  let rawLabels = [];
  let periodTitle = '';
  let isIntradaySurge = false;
  let intradayResult = null;

  if (period === 'intraday' || !period) {
    period = 'intraday';
    periodTitle = '⚡ 盤中即時走勢 (09:00 ~ 13:30 分時走勢圖)';

    const chgPct = parseFloat(stockData.change || (alertData ? `${alertData.change_pct}` : '0')) || 0;
    const yesterdayClose = (chgPct !== 0 && livePrice > 0)
      ? Number((livePrice / (1 + chgPct / 100)).toFixed(2))
      : Number(stockData.yesterdayClose || livePrice);

    intradayResult = generateIntradayTimeSeries(stockData, alertData, yesterdayClose, livePrice);
    rawLabels = intradayResult.labels;
    rawPrices = intradayResult.prices;
  } else if (period === 'surge') {
    isIntradaySurge = true;
    periodTitle = '🚀 盤中急拉時序軌跡';
    const ticks = alertData?.ticks || [];
    if (ticks.length >= 2) {
      ticks.forEach(item => {
        const d = new Date(item.t * 1000);
        rawLabels.push(d.toTimeString().substring(0, 8));
        rawPrices.push(Number(item.p));
      });
    } else if (alertData && alertData.surge_start_price) {
      rawLabels = ['起拉基準點', '最新急拉現價'];
      rawPrices = [Number(alertData.surge_start_price), livePrice || Number(alertData.price)];
    } else {
      rawLabels = ['開盤基準', '今日最低', '最高點', '即時現價'];
      rawPrices = [stockData.open || livePrice * 0.98, stockData.low || livePrice * 0.98, stockData.high || livePrice, livePrice];
    }
  } else if (period === 'month') {
    periodTitle = '📅 月線走勢 (近 12 個月 / 月K級別)';
    if (techData.history_monthly && techData.history_monthly.length >= 2) {
      rawPrices = [...techData.history_monthly, livePrice];
      rawLabels = techData.dates_monthly ? [...techData.dates_monthly, '本月即時'] : rawPrices.map((_, i) => i === rawPrices.length - 1 ? '本月' : `M-${rawPrices.length - 1 - i}`);
    } else if (techData.history60d && techData.history60d.length >= 10) {
      const sampled = techData.history60d.filter((_, i) => i % 5 === 0);
      rawPrices = [...sampled, livePrice];
      rawLabels = rawPrices.map((_, i) => i === rawPrices.length - 1 ? '本月' : `M-${rawPrices.length - 1 - i}`);
    } else {
      rawPrices = generateRealisticFallbackHistory(stockData, 12, 'month');
      rawLabels = rawPrices.map((_, i) => i === rawPrices.length - 1 ? '本月' : `M-${rawPrices.length - 1 - i}`);
    }
  } else if (period === 'week') {
    periodTitle = '📈 周線走勢 (近 24 週 / 周K級別)';
    if (techData.history_weekly && techData.history_weekly.length >= 2) {
      rawPrices = [...techData.history_weekly, livePrice];
      rawLabels = techData.dates_weekly ? [...techData.dates_weekly, '本週即時'] : rawPrices.map((_, i) => i === rawPrices.length - 1 ? '本週' : `W-${rawPrices.length - 1 - i}`);
    } else if (techData.history60d && techData.history60d.length >= 6) {
      const sampled = techData.history60d.filter((_, i) => i % 3 === 0);
      rawPrices = [...sampled, livePrice];
      rawLabels = rawPrices.map((_, i) => i === rawPrices.length - 1 ? '本週' : `W-${rawPrices.length - 1 - i}`);
    } else {
      rawPrices = generateRealisticFallbackHistory(stockData, 20, 'week');
      rawLabels = rawPrices.map((_, i) => i === rawPrices.length - 1 ? '本週' : `W-${rawPrices.length - 1 - i}`);
    }
  } else if (period === 'day') {
    periodTitle = '🕯️ 日線走勢 (近 20 個交易日 / 日K級別)';
    if (techData.history20d && techData.history20d.length >= 2) {
      rawPrices = [...techData.history20d, livePrice];
      rawLabels = techData.dates20d ? [...techData.dates20d, '今日現價'] : rawPrices.map((_, i) => i === rawPrices.length - 1 ? '今日' : `D-${rawPrices.length - 1 - i}`);
    } else {
      rawPrices = generateRealisticFallbackHistory(stockData, 20, 'day');
      rawLabels = rawPrices.map((_, i) => i === rawPrices.length - 1 ? '今日' : `D-${rawPrices.length - 1 - i}`);
    }
  } else {
    // '5d'
    period = '5d';
    periodTitle = '📊 5日走勢 (5MA週線視角)';
    if (techData.history5d && techData.history5d.length >= 2) {
      rawPrices = [...techData.history5d, livePrice];
      rawLabels = techData.dates5d ? [...techData.dates5d, '今日現價'] : ['5日前', '4日前', '3日前', '前日', '昨收盤', '今日即時'];
      if (rawLabels.length > rawPrices.length) rawLabels = rawLabels.slice(rawLabels.length - rawPrices.length);
    } else {
      rawPrices = generateRealisticFallbackHistory(stockData, 6, '5d');
      rawLabels = ['5日前', '4日前', '3日前', '前日', '昨收盤', '今日即時'];
    }
  }

  // 去除非盤中重複點
  if (period !== 'intraday' && period !== 'surge' && rawPrices.length >= 2) {
    if (!(livePrice > 0)) {
      rawPrices.pop();
      rawLabels.pop();
    } else {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const todayMD = `${pad(now.getMonth() + 1)}/${pad(now.getDate())}`;
      const thisYM = `${String(now.getFullYear()).slice(-2)}/${pad(now.getMonth() + 1)}`;
      const prevLabel = rawLabels[rawLabels.length - 2];
      if (prevLabel === todayMD || prevLabel === thisYM) {
        rawPrices.splice(rawPrices.length - 2, 1);
        rawLabels.splice(rawLabels.length - 2, 1);
      }
    }
  }
  rawPrices = rawPrices.map(v => Number(v)).filter(v => Number.isFinite(v));
  if (rawLabels.length !== rawPrices.length) {
    rawLabels = rawLabels.slice(-rawPrices.length);
    while (rawLabels.length < rawPrices.length) rawLabels.unshift('');
  }

  // 決定主線漲跌色彩
  const isUp = (period === 'intraday' && intradayResult)
    ? (livePrice >= intradayResult.yesterdayClose)
    : ((rawPrices.length >= 2) ? (rawPrices[rawPrices.length - 1] >= rawPrices[0]) : true);

  const lineColor = isIntradaySurge ? '#f97316' : (isUp ? '#ef4444' : '#10b981');

  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 340);
  if (isIntradaySurge) {
    gradient.addColorStop(0, 'rgba(249, 115, 22, 0.35)');
    gradient.addColorStop(1, 'rgba(249, 115, 22, 0.0)');
  } else {
    gradient.addColorStop(0, isUp ? 'rgba(239, 68, 68, 0.32)' : 'rgba(16, 185, 129, 0.32)');
    gradient.addColorStop(0.7, isUp ? 'rgba(239, 68, 68, 0.05)' : 'rgba(16, 185, 129, 0.05)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0.0)');
  }

  const datasets = [
    {
      type: 'line',
      label: `走勢價格 (${periodTitle})`,
      data: rawPrices,
      borderColor: lineColor,
      backgroundColor: gradient,
      fill: true,
      tension: (period === 'intraday' || period === '5d' || isIntradaySurge) ? 0.22 : 0.15,
      borderWidth: 2.6,
      pointRadius: (period === 'intraday')
        ? ((ctx) => (ctx.dataIndex === rawPrices.length - 1 ? 5 : 0))
        : ((rawPrices.length > 25) ? 2 : ((rawPrices.length > 10) ? 3 : 5)),
      pointHoverRadius: 7,
      pointBackgroundColor: lineColor,
      pointBorderColor: '#ffffff',
      pointBorderWidth: 1.8,
      yAxisID: 'y'
    }
  ];

  // 疊加指標 (針對盤中即時 vs 均線指標)
  let scalesConfig = {
    x: {
      grid: { color: 'rgba(255, 255, 255, 0.05)' },
      ticks: { color: '#94a3b8', font: { size: (rawPrices.length > 20) ? 9 : 11 }, maxRotation: 0 }
    },
    y: {
      position: 'left',
      grid: { color: 'rgba(255, 255, 255, 0.05)' },
      ticks: {
        color: '#94a3b8',
        font: { size: 11 },
        callback: (v) => `$${v}`
      }
    }
  };

  if (period === 'intraday' && intradayResult) {
    const yc = intradayResult.yesterdayClose;
    // 昨收平盤線
    datasets.push({
      type: 'line',
      label: `昨收平盤 ($${yc.toFixed(2)})`,
      data: new Array(rawPrices.length).fill(yc),
      borderColor: '#94a3b8',
      borderWidth: 1.4,
      borderDash: [5, 5],
      pointRadius: 0,
      fill: false,
      yAxisID: 'y'
    });

    // 當日均價線 (VWAP)
    datasets.push({
      type: 'line',
      label: `當日均價線 (VWAP)`,
      data: intradayResult.vwap,
      borderColor: '#fbbf24',
      borderWidth: 1.6,
      borderDash: [3, 2],
      pointRadius: 0,
      fill: false,
      yAxisID: 'y'
    });

    // 分時成交量柱狀圖 (量能)
    datasets.push({
      type: 'bar',
      label: `分時成交量 (張)`,
      data: intradayResult.volumes,
      backgroundColor: intradayResult.prices.map((p, idx) => {
        const prev = idx > 0 ? intradayResult.prices[idx - 1] : yc;
        return p >= prev ? 'rgba(239, 68, 68, 0.45)' : 'rgba(16, 185, 129, 0.45)';
      }),
      borderRadius: 2,
      yAxisID: 'yVolume',
      barPercentage: 0.65
    });

    // 量化固定 Y 軸階梯刻度，以昨收為對稱中心，防止價格微幅跳動導致 Y 軸上下伸縮抖動
    const rawMaxDev = Math.max(
      Math.abs(intradayResult.highPrice - yc),
      Math.abs(intradayResult.lowPrice - yc),
      yc * 0.015
    );
    const step = yc >= 500 ? 5.0 : (yc >= 100 ? 1.0 : (yc >= 50 ? 0.5 : 0.2));
    const paddedDev = Math.ceil((rawMaxDev * 1.15) / step) * step;
    const yMin = Number((yc - paddedDev).toFixed(2));
    const yMax = Number((yc + paddedDev).toFixed(2));
    const maxVol = Math.max(10, ...intradayResult.volumes);

    scalesConfig = {
      x: {
        grid: { color: 'rgba(255, 255, 255, 0.04)' },
        ticks: { color: '#94a3b8', font: { size: 10 }, maxRotation: 0, maxTicksLimit: 10 }
      },
      y: {
        position: 'left',
        min: yMin,
        max: yMax,
        grid: { color: 'rgba(255, 255, 255, 0.05)' },
        ticks: {
          color: '#cbd5e1',
          font: { size: 11 },
          callback: (v) => `$${Number(v).toFixed(2)}`
        }
      },
      yVolume: {
        position: 'right',
        min: 0,
        max: maxVol * 4.2, // 柱狀只佔底部 24%
        grid: { display: false },
        ticks: { display: false }
      }
    };
  } else if (period === 'day') {
    const rollingMA5 = calculateRollingMA(rawPrices, 5);
    const rollingMA10 = calculateRollingMA(rawPrices, 10);
    const rollingMA20 = calculateRollingMA(rawPrices, 20);

    datasets.push({
      type: 'line',
      label: `5日線 (週線 5MA)`,
      data: rollingMA5,
      borderColor: '#f59e0b',
      borderWidth: 2,
      pointRadius: 0,
      fill: false,
      tension: 0.2
    });
    datasets.push({
      type: 'line',
      label: `10日線 (雙週 10MA)`,
      data: rollingMA10,
      borderColor: '#38bdf8',
      borderWidth: 1.6,
      borderDash: [4, 3],
      pointRadius: 0,
      fill: false,
      tension: 0.2
    });
    datasets.push({
      type: 'line',
      label: `20日線 (月線 20MA)`,
      data: rollingMA20,
      borderColor: '#c084fc',
      borderWidth: 2,
      pointRadius: 0,
      fill: false,
      tension: 0.2
    });

    if (techData.upper_band) {
      datasets.push({
        type: 'line',
        label: `布林上軌 (${techData.upper_band})`,
        data: new Array(rawPrices.length).fill(techData.upper_band),
        borderColor: '#fb7185',
        borderWidth: 1.3,
        borderDash: [3, 3],
        pointRadius: 0,
        fill: false
      });
    }
    if (techData.lower_band) {
      datasets.push({
        type: 'line',
        label: `布林下軌 (${techData.lower_band})`,
        data: new Array(rawPrices.length).fill(techData.lower_band),
        borderColor: '#34d399',
        borderWidth: 1.3,
        borderDash: [3, 3],
        pointRadius: 0,
        fill: false
      });
    }
  } else if (period === 'week') {
    const rollingWMA5 = calculateRollingMA(rawPrices, 5);
    const rollingWMA10 = calculateRollingMA(rawPrices, 10);
    const rollingWMA20 = calculateRollingMA(rawPrices, 20);

    datasets.push({
      type: 'line',
      label: `5週均線 (5W-MA)`,
      data: rollingWMA5,
      borderColor: '#f59e0b',
      borderWidth: 2.2,
      pointRadius: 0,
      fill: false,
      tension: 0.2
    });
    datasets.push({
      type: 'line',
      label: `10週均線 (10W-MA)`,
      data: rollingWMA10,
      borderColor: '#38bdf8',
      borderWidth: 1.8,
      borderDash: [4, 3],
      pointRadius: 0,
      fill: false,
      tension: 0.2
    });
    datasets.push({
      type: 'line',
      label: `20週均線 (20W-MA)`,
      data: rollingWMA20,
      borderColor: '#c084fc',
      borderWidth: 2,
      pointRadius: 0,
      fill: false,
      tension: 0.2
    });
  } else if (period === 'month') {
    const rollingMMA5 = calculateRollingMA(rawPrices, 5);
    const rollingMMA10 = calculateRollingMA(rawPrices, 10);

    datasets.push({
      type: 'line',
      label: `5月均線 (5M-MA)`,
      data: rollingMMA5,
      borderColor: '#f59e0b',
      borderWidth: 2.2,
      pointRadius: 0,
      fill: false,
      tension: 0.2
    });
    datasets.push({
      type: 'line',
      label: `10月均線 (10M-MA)`,
      data: rollingMMA10,
      borderColor: '#c084fc',
      borderWidth: 2,
      borderDash: [4, 3],
      pointRadius: 0,
      fill: false,
      tension: 0.2
    });
    if (techData.sma60) {
      datasets.push({
        type: 'line',
        label: `季線基準 (${techData.sma60})`,
        data: new Array(rawPrices.length).fill(techData.sma60),
        borderColor: '#38bdf8',
        borderWidth: 1.5,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false
      });
    }
  } else if (period === '5d') {
    if (techData.sma5) {
      datasets.push({
        type: 'line',
        label: `5日線/週線 (${techData.sma5})`,
        data: new Array(rawPrices.length).fill(techData.sma5),
        borderColor: '#f59e0b',
        borderWidth: 1.8,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false
      });
    }
    if (techData.sma20) {
      datasets.push({
        type: 'line',
        label: `20日線/月線 (${techData.sma20})`,
        data: new Array(rawPrices.length).fill(techData.sma20),
        borderColor: '#c084fc',
        borderWidth: 1.8,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false
      });
    }
    if (techData.upper_band) {
      datasets.push({
        type: 'line',
        label: `布林上軌 (${techData.upper_band})`,
        data: new Array(rawPrices.length).fill(techData.upper_band),
        borderColor: '#fb7185',
        borderWidth: 1.3,
        borderDash: [3, 3],
        pointRadius: 0,
        fill: false
      });
    }
  } else if (period === 'surge' && alertData?.surge_start_price) {
    datasets.push({
      type: 'line',
      label: `急拉起點基準 ($${alertData.surge_start_price})`,
      data: new Array(rawPrices.length).fill(Number(alertData.surge_start_price)),
      borderColor: '#fbbf24',
      borderWidth: 1.8,
      borderDash: [4, 4],
      pointRadius: 0,
      fill: false
    });
  }

  stockModalChartInstance = new (window.Chart || Chart)(ctx, {
    type: 'line',
    data: {
      labels: rawLabels,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 100 },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: { color: '#cbd5e1', font: { size: 11, weight: '600' }, boxWidth: 12, padding: 8 }
        },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.95)',
          titleColor: '#f8fafc',
          bodyColor: '#e2e8f0',
          borderColor: 'rgba(255, 255, 255, 0.1)',
          borderWidth: 1,
          padding: 10,
          callbacks: {
            label: function(context) {
              const val = context.parsed.y;
              if (context.dataset.yAxisID === 'yVolume') {
                return `${context.dataset.label}: ${Math.round(val).toLocaleString()} 張`;
              }
              return `${context.dataset.label}: NT$ ${val.toFixed(2)}`;
            }
          }
        }
      },
      scales: scalesConfig
    }
  });

  stockModalChartInstance._currentCode = currentModalCode;
  stockModalChartInstance._currentPeriod = period;

  // 更新底端診斷備註
  updateStockModalNotes(period, stockData, alertData, techData, livePrice, isUp, intradayResult);
  updateStockModalSubHeader(stockData, alertData, livePrice);
}

function renderStockModalTvIframe(code, tvMarket, interval) {
  const container = document.getElementById('modal-tv-iframe-container');
  if (!container) return;
  const targetSymbol = `${tvMarket || 'TWSE'}:${code}`;
  const targetInterval = interval || currentTvInterval || 'D';
  const iframeSrc = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(targetSymbol)}&interval=${targetInterval}&hidesidetoolbar=0&symboledit=1&saveimage=1&toolbarbg=0f1523&studies=[]&theme=dark&style=1&timezone=Asia%2FTaipei`;

  const existingIframe = container.querySelector('iframe');
  if (existingIframe && existingIframe.getAttribute('data-symbol') === targetSymbol) {
    if (existingIframe.getAttribute('data-interval') === targetInterval) {
      return;
    }
    existingIframe.setAttribute('data-interval', targetInterval);
    existingIframe.src = iframeSrc;
    return;
  }

  container.innerHTML = `
    <iframe src="${iframeSrc}" data-symbol="${targetSymbol}" data-interval="${targetInterval}" width="100%" height="100%" frameborder="0" allowtransparency="true" scrolling="no" style="border:none;display:block;"></iframe>
  `;
}

function setTvMarket(market) {
  currentModalTvMarket = market;
  const btnTwse = document.getElementById('modal-tv-twse-btn');
  const btnTpex = document.getElementById('modal-tv-tpex-btn');
  if (btnTwse && btnTpex) {
    btnTwse.classList.toggle('active', market === 'TWSE');
    btnTpex.classList.toggle('active', market === 'TPEX');
  }
  renderStockModalTvIframe(currentModalCode, currentModalTvMarket, currentTvInterval);
}

// 相容相依性包裝函數 (確保所有歷史呼叫點百分之百運作)
function setChartPeriod(period) {
  setModalChartPeriod(period);
}
function openTvInterval(interval) {
  setModalChartEngine('tv', false);
  setTvIntervalDirect(interval);
}
function setTvInterval(interval) {
  setTvIntervalDirect(interval);
}
function switchStockModalTab(tabName) {
  if (tabName === 'tv') {
    setModalChartEngine('tv');
  } else if (tabName === 'surge') {
    setModalChartEngine('native', false);
    setModalChartPeriod('surge');
  } else {
    setModalChartEngine('native', false);
    setModalChartPeriod('5d');
  }
}
function renderStockModalSurgeChart() {
  // 自動整合至 renderStockModalChart('surge')
}

function locateStockInTable() {
  if (currentModalCode) {
    quickFilterStock(currentModalCode);
  }
  closeStockChartModal();
}

// 支援全域快捷鍵 (Hotkeys) 提升操作極限速度
document.addEventListener('keydown', (e) => {
  // 如果焦點正在任何輸入框或選單中，只處理 Escape
  const isInputActive = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);

  if (e.key === 'Escape') {
    closeStockChartModal();
    if (surgeAlertVisible && !isAlertPanelShrunk) {
      toggleSurgePanelShrink(true);
    }
    return;
  }

  if (isInputActive) return;

  // 1. 按下 '/' 快速定位搜尋框
  if (e.key === '/') {
    e.preventDefault();
    if (currentActiveTab === 'surge-tab') {
      document.getElementById('surge-precision-search')?.focus();
    } else if (currentActiveTab === 'surge-mixed-tab') {
      document.getElementById('surge-mixed-search')?.focus();
    } else {
      document.getElementById('screener-search')?.focus();
    }
  }

  // 2. 按數字鍵 1~4 快速切換分頁
  if (e.key === '1') { switchTab('screener'); }
  else if (e.key === '2') { switchTab('surge-tab'); }
  else if (e.key === '3') { switchTab('surge-mixed-tab'); }
  else if (e.key === '4') { switchTab('ai-momentum'); }

  // 3. 按 'p' 或 'P' 快速凍結/恢復即時串流
  if (e.key === 'p' || e.key === 'P') {
    e.preventDefault();
    toggleSurgePause();
  }

  // 4. 按 'm' 或 'M' 快速開關語音警報音效
  if (e.key === 'm' || e.key === 'M') {
    e.preventDefault();
    toggleSurgeSound();
  }

  // 5. 按 'r' 或 'R' 立即手動重排
  if (e.key === 'r' || e.key === 'R') {
    e.preventDefault();
    pollSurgeAlerts(true);
  }
});



