const categoryMeta = {
  home: { title: 'Global Issue Map', subtitle: '세계 주요 이슈를 한 화면에서 읽는 지도형 브리핑 대시보드.', center: [25, 15], zoom: 2.3 },
  war: { title: 'Conflict Signal Map', subtitle: '전쟁과 군사 긴장을 지도 기반으로 빠르게 확인하는 브리핑 화면입니다.', center: [32, 35], zoom: 2.6 },
  politics: { title: 'Political Motion Map', subtitle: '외교, 선거, 제재 이슈를 국가 단위 흐름으로 정리합니다.', center: [30, 35], zoom: 2.2 },
  economy: { title: 'Economic Signal Map', subtitle: '시장, 금리, 환율, 경기 흐름을 뉴스와 함께 읽는 경제 지도입니다.', center: [30, 20], zoom: 2.2 },
  disaster: { title: 'Disaster Impact Map', subtitle: '재난과 공급망 충격을 지역별 영향 중심으로 확인합니다.', center: [18, 115], zoom: 2.2 },
  saved: { title: 'My Saved Articles', subtitle: '로그인한 뒤 저장한 기사만 모아 다시 읽고 지도에서 재확인하는 개인 보관함입니다.', center: [25, 15], zoom: 2.3 },
};

const fallbackImpactProfiles = {
  home: [
    { title: '글로벌 자산', subtitle: '핵심 뉴스에 따라 안전자산과 위험자산이 함께 움직입니다.' },
    { title: '에너지 민감도', subtitle: '분쟁과 공급망 이슈가 유가와 원자재에 반영됩니다.' },
    { title: '대표 지수', subtitle: '국제 정치와 경제 뉴스가 증시에 연쇄적으로 반영됩니다.' },
  ],
  war: [
    { title: '금 가격', subtitle: '위험회피 심리 강화 시 안전자산 수요가 올라갈 수 있습니다.' },
    { title: '석유 가격', subtitle: '중동, 해상 물류, 제재 이슈에 따라 유가가 민감하게 움직입니다.' },
    { title: '주식시장', subtitle: '전쟁 기사 강도가 커질수록 글로벌 증시 변동성이 확대될 수 있습니다.' },
  ],
  politics: [
    { title: '외교 관계', subtitle: '정책 발표와 외교 일정이 통상 흐름에 영향을 줄 수 있습니다.' },
    { title: '무역', subtitle: '제재, 관세, 협상 뉴스가 실물 교역 기대를 바꿉니다.' },
    { title: '시장 심리', subtitle: '정치 이벤트는 위험자산 선호와 변동성에 바로 반영됩니다.' },
  ],
  disaster: [
    { title: '공급망', subtitle: '항만, 생산시설, 물류 거점 차질 가능성을 먼저 확인합니다.' },
    { title: '교통', subtitle: '항공, 항만, 철도, 도로 복구 일정이 핵심 변수입니다.' },
    { title: '산업 영향', subtitle: '보험, 제조, 유통 등 산업별 충격 강도가 달라질 수 있습니다.' },
  ],
  saved: [
    { title: '저장한 기사', subtitle: '관심 이슈를 다시 추적하고 비교하기 위한 개인 보관함입니다.' },
    { title: '지도 복기', subtitle: '저장 당시의 위치와 이슈 색상을 그대로 다시 확인할 수 있습니다.' },
    { title: '후속 확인', subtitle: '원문 기사와 함께 업데이트 방향을 다시 점검할 수 있습니다.' },
  ],
};

const state = {
  category: 'home',
  selectedPinId: null,
  news: { articles: [], pins: [] },
  newsMeta: { sourceType: '', message: '', loadedCategory: '' },
  marketMetrics: null,
  marketMetricsError: '',
  auth: { authenticated: false, nickname: '' },
  savedArticles: [],
};

let map;
let markerLayer;
const markerIndex = new Map();
const inFlightNewsRequests = new Map();

function scoreForArticle(index) {
  return Math.max(62, 96 - index * 3);
}

function currentMeta() {
  return categoryMeta[state.category] || categoryMeta.home;
}

function selectedPin() {
  return state.news.pins.find((pin) => pin.id === state.selectedPinId) || null;
}

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-';
  }
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function formatDelta(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '변동값 없음';
  }
  const numeric = Number(value);
  const sign = numeric > 0 ? '+' : '';
  return `${sign}${numeric.toFixed(2)}`;
}

function buildSparkline(series = [], stroke = '#2563eb') {
  if (!series.length) {
    return '<div class="impact-fallback">시계열 데이터를 불러오지 못했습니다.</div>';
  }

  const values = series.map((item) => Number(item.y ?? item.value)).filter((value) => Number.isFinite(value));
  if (!values.length) {
    return '<div class="impact-fallback">시계열 데이터를 불러오지 못했습니다.</div>';
  }

  const width = 320;
  const height = 120;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - ((value - min) / range) * (height - 16) - 8;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');

  return `
    <svg viewBox="0 0 ${width} ${height}" class="impact-sparkline" preserveAspectRatio="none" aria-hidden="true">
      <polyline fill="none" stroke="${stroke}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${points}"></polyline>
    </svg>
  `;
}

function currentFeedHeading() {
  if (state.category === 'saved') {
    return {
      title: '저장한 기사 목록',
      copy: state.auth.authenticated
        ? '로그인한 계정에 저장된 기사만 다시 불러옵니다.'
        : '닉네임만 입력해 로그인하면 Saved 탭을 사용할 수 있습니다.',
    };
  }

  let copy = 'Live articles are loaded from NewsAPI for the selected category.';
  if (state.newsMeta.sourceType === 'live_newsapi') {
    copy = 'This view is currently showing live NewsAPI articles.';
  } else if (state.newsMeta.sourceType === 'cache') {
    copy = '실시간 호출이 잠시 실패해 최근 캐시 결과를 표시하고 있습니다.';
  } else if (state.newsMeta.sourceType === 'unavailable') {
    copy = 'Live NewsAPI articles are unavailable, so the list is empty.';
  } else if (state.newsMeta.sourceType === 'error') {
    copy = state.newsMeta.message || '뉴스를 불러오지 못했습니다.';
  }

  return {
    title: 'NewsAPI Article Top 10',
    copy,
  };
}

function renderHeader() {
  const meta = currentMeta();
  const feedHeading = currentFeedHeading();
  document.getElementById('pageTitle').textContent = meta.title;
  document.getElementById('pageSubtitle').textContent = meta.subtitle;
  document.getElementById('feedTitle').textContent = feedHeading.title;
  document.getElementById('feedCopy').textContent = feedHeading.copy;
  document.getElementById('lastUpdated').textContent = new Date().toLocaleString('ko-KR');
  document.querySelectorAll('.view-tab').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.category === state.category);
  });
}

function renderAuthPanel() {
  const authPanel = document.getElementById('authPanel');
  if (!authPanel) {
    return;
  }

  if (state.auth.authenticated) {
    authPanel.innerHTML = `
      <div class="auth-state auth-state--logged-in">
        <strong>${state.auth.nickname}</strong>
        <p>기사 저장과 Saved 탭을 바로 사용할 수 있습니다.</p>
        <div class="auth-actions">
          <button class="detail-button primary auth-button" type="button" data-open-saved-tab>Saved 보기</button>
          <button class="detail-button auth-button" type="button" data-logout>로그아웃</button>
        </div>
      </div>
    `;
    return;
  }

  authPanel.innerHTML = `
    <form class="auth-form" id="loginForm">
      <label class="auth-label" for="nicknameInput">닉네임만 입력하면 바로 시작됩니다.</label>
      <input id="nicknameInput" name="nickname" class="auth-input" type="text" minlength="2" maxlength="24" placeholder="예: huigim" required />
      <button class="detail-button primary auth-button" type="submit">간단 로그인</button>
    </form>
  `;
}

function renderFallbackImpactMetrics() {
  const impactMetrics = document.getElementById('impactMetrics');
  const pin = selectedPin();
  const profiles = fallbackImpactProfiles[state.category] || fallbackImpactProfiles.home;
  impactMetrics.innerHTML = profiles.map((metric, index) => `
    <article class="impact-card">
      <div class="impact-card-head">
        <h4 class="impact-card-title">${metric.title}</h4>
        <p class="impact-card-copy">${metric.subtitle}</p>
      </div>
      <div class="impact-chart impact-chart--text">
        <div class="impact-fallback">${index === 0 && pin ? (pin.ai_impact || pin.summary || '관련 설명이 없습니다.') : (pin?.summary || '선택한 기사 기준 영향 설명이 표시됩니다.')}</div>
      </div>
    </article>
  `).join('');
}

function renderMarketMetrics() {
  const impactMetrics = document.getElementById('impactMetrics');

  if (state.marketMetricsError) {
    impactMetrics.innerHTML = `<div class="impact-fallback">${state.marketMetricsError}</div>`;
    return;
  }

  const metrics = state.marketMetrics?.metrics || [];
  if (!metrics.length) {
    renderFallbackImpactMetrics();
    return;
  }

  impactMetrics.innerHTML = metrics.map((metric) => {
    const positive = Number(metric.change || 0) >= 0;
    const accent = metric.id === 'gold' ? '#d4a017' : metric.id === 'wti' ? '#ef4444' : '#2563eb';
    return `
      <article class="impact-card impact-card--real">
        <div class="impact-card-head">
          <h4 class="impact-card-title">${metric.title}</h4>
          ${metric.subtitle ? `<p class="impact-card-copy">${metric.subtitle}</p>` : ''}
        </div>
        <div class="impact-kpi-row">
          <strong class="impact-kpi-value">${formatNumber(metric.value)}</strong>
          <span class="impact-kpi-unit">${metric.unit || ''}</span>
        </div>
        <div class="impact-kpi-meta ${positive ? 'is-positive' : 'is-negative'}">${formatDelta(metric.change)}</div>
        <div class="impact-chart impact-chart--sparkline">
          ${buildSparkline(metric.series, accent)}
        </div>
        <p class="impact-card-note">${metric.series_note || ''}</p>
        <p class="impact-card-source">${metric.updated_at || '-'} · ${metric.source || '시장 데이터'}</p>
      </article>
    `;
  }).join('');
}

function renderImpactMetrics() {
  renderMarketMetrics();
}

function normalizeSavedIds() {
  return new Set(state.savedArticles.map((article) => article.article_id));
}

function isSavedPin(pin) {
  return Boolean(pin && normalizeSavedIds().has(pin.id));
}

function buildSavedPin(article, index) {
  return {
    id: article.article_id,
    saved_id: article.id,
    title: article.title,
    summary: article.summary,
    url: article.url,
    source: article.source,
    lat: article.lat ?? (20 + index * 2.1),
    lng: article.lng ?? (10 + index * 4.3),
    category: article.category,
    country: article.country || 'GL',
    country_name: article.country_name || article.region || 'Global',
    location_label: article.location_label || article.region || 'Global',
    matched_location: Boolean(article.lat && article.lng),
    location_confidence: article.lat && article.lng ? 1 : 0,
    pin_color: article.pin_color || '#2563EB',
    ai_opinion: `${article.title} 관련 저장 기사입니다. 이후 흐름을 다시 확인하기 위한 개인 보관 기록입니다.`,
    ai_forecast: '저장한 기사를 기준으로 후속 보도와 시장 반응을 비교해 보세요.',
    ai_impact: '이슈 성격에 따라 금, 유가, 주식시장 또는 정책 기대가 다시 움직일 수 있습니다.',
  };
}

function buildSavedHeadline(article) {
  return {
    id: article.article_id,
    saved_id: article.id,
    title: article.title,
    source: article.source,
    summary: article.summary,
    url: article.url,
    country: article.country,
    location_label: article.location_label || article.region || 'Global',
    saved_at: article.saved_at,
  };
}

function renderMapFeed() {
  const mapFeedStats = document.getElementById('mapFeedStats');
  const mapFeedList = document.getElementById('mapFeedList');
  const articles = state.news.articles || [];
  const sourceCount = new Set(articles.map((article) => article.source).filter(Boolean)).size;

  if (state.category === 'saved') {
    mapFeedStats.innerHTML = `
      <article class="map-feed-stat"><span>저장 기사</span><strong>${articles.length}건</strong></article>
      <article class="map-feed-stat"><span>로그인 상태</span><strong>${state.auth.authenticated ? state.auth.nickname : '미로그인'}</strong></article>
      <article class="map-feed-stat"><span>최근 확인</span><strong>${new Date().toLocaleTimeString('ko-KR')}</strong></article>
    `;
  } else {
    mapFeedStats.innerHTML = `
      <article class="map-feed-stat"><span>기사량</span><strong>${articles.length}건</strong></article>
      <article class="map-feed-stat"><span>매체 수</span><strong>${sourceCount}개</strong></article>
      <article class="map-feed-stat"><span>최근 감지</span><strong>${new Date().toLocaleTimeString('ko-KR')}</strong></article>
    `;
  }

  if (!articles.length) {
    const emptyMessage = state.category === 'saved'
      ? '저장한 기사가 없습니다. 먼저 로그인한 뒤 기사 저장 버튼을 눌러 보세요.'
      : state.newsMeta.sourceType === 'unavailable'
        ? (state.newsMeta.message || 'Live NewsAPI articles are unavailable.')
        : '표시할 기사가 없습니다.';
    mapFeedList.innerHTML = `<div class="map-feed-empty">${emptyMessage}</div>`;
    return;
  }

  mapFeedList.innerHTML = articles.slice(0, 10).map((article, index) => `
    <article class="map-feed-item">
      <div class="map-feed-rank">${index + 1}</div>
      <div class="map-feed-body">
        <h4 class="map-feed-title"><a href="${article.url}" target="_blank" rel="noreferrer noopener">${article.title}</a></h4>
        <div class="map-feed-meta">${article.source || 'Unknown source'} · ${article.location_label || article.country || 'Global'} · ${article.summary || '요약 없음'}</div>
        ${article.saved_at ? `<div class="map-feed-meta">저장 시각 · ${new Date(article.saved_at).toLocaleString('ko-KR')}</div>` : ''}
      </div>
      <div class="map-feed-score">
        <strong>${state.category === 'saved' ? '보관 기사' : `영향도 ${scoreForArticle(index)}`}</strong>
        ${state.category === 'saved'
          ? `<button class="map-feed-inline-action" type="button" data-remove-saved="${article.saved_id}">삭제</button>`
          : `<div class="map-feed-bar"><div class="map-feed-bar-fill" style="width: ${scoreForArticle(index)}%;"></div></div>`}
      </div>
    </article>
  `).join('');
}

function renderEvidence() {
  const evidenceList = document.getElementById('evidenceList');
  const pin = selectedPin();
  const relatedArticles = (state.news.articles || []).filter((article) => article.id !== pin?.id).slice(0, 3);

  evidenceList.innerHTML = relatedArticles.length
    ? relatedArticles.map((article) => `
      <article class="evidence-item">
        <a href="${article.url}" target="_blank" rel="noreferrer noopener">${article.title}</a>
        <p>${article.source || 'Unknown source'} · ${article.location_label || article.country || 'Global'}</p>
      </article>
    `).join('')
    : '<div class="map-feed-empty">추가 근거 기사가 없습니다.</div>';
}

function renderDetail(pin) {
  const detailTitle = document.getElementById('detailTitle');
  const detailSummary = document.getElementById('detailSummary');
  const detailChips = document.getElementById('detailChips');
  const detailActions = document.getElementById('detailActions');
  const detailGrid = document.getElementById('detailGrid');

  if (!pin) {
    detailTitle.textContent = state.category === 'saved' ? '저장한 기사를 선택해 주세요' : '핀을 선택해 주세요';
    detailSummary.textContent = state.category === 'saved'
      ? 'Saved 탭에서 저장한 기사 핀을 누르면 기사 내용과 원문 링크가 여기에 표시됩니다.'
      : '지도에서 사건 핀을 누르면 해당 이슈의 핵심 내용과 기사 주소가 여기에 표시됩니다.';
    detailChips.innerHTML = '';
    detailActions.innerHTML = '';
    detailGrid.innerHTML = '';
    renderImpactMetrics();
    renderEvidence();
    return;
  }

  const saved = isSavedPin(pin);
  const saveLabel = !state.auth.authenticated ? '로그인 후 저장' : saved ? '이미 저장됨' : '기사 저장';

  detailTitle.textContent = pin.title;
  detailSummary.textContent = pin.summary || '상세 요약 정보가 없습니다.';
  detailChips.innerHTML = `
    <span class="chip">${pin.category || state.category}</span>
    <span class="chip">${pin.source || 'source'}</span>
    <span class="chip">${pin.location_label || pin.country_name || pin.country || 'Global'}</span>
  `;
  detailActions.innerHTML = `
    <button class="detail-button primary" type="button" data-open-url="${pin.url || ''}">뉴스 보기</button>
    <button class="detail-button" type="button" data-save-article="${pin.id}" ${!state.auth.authenticated || saved ? 'disabled' : ''}>${saveLabel}</button>
    ${state.category === 'saved' && pin.saved_id ? `<button class="detail-button" type="button" data-remove-saved="${pin.saved_id}">저장 삭제</button>` : ''}
    <button class="detail-button" type="button" data-focus-pin="${pin.id}">핀 위치 보기</button>
  `;
  detailGrid.innerHTML = `
    <article class="detail-item detail-item--summary">
      <span>기사 제목 · 상세내용 · 기사 주소</span>
      <strong>${pin.title}</strong>
      <p class="detail-copy">${pin.summary || '상세 내용이 아직 없습니다.'}</p>
      <a class="detail-link" href="${pin.url || '#'}" ${pin.url ? 'target="_blank" rel="noreferrer noopener"' : ''}>${pin.url || '기사 주소 없음'}</a>
    </article>
    <article class="detail-item detail-item--forecast">
      <span>AI 의견과 미래 예상 동향</span>
      <strong>${pin.ai_opinion || 'AI 분석을 준비 중입니다.'}</strong>
      <p class="detail-copy">${pin.ai_forecast || '후속 보도에 따라 변동성이 확대될 가능성이 있습니다.'}</p>
    </article>
    <article class="detail-item detail-item--impact">
      <span>기사가 영향을 준 내용</span>
      <strong>${pin.ai_impact || '연관 시장 지표와 후속 기사 흐름을 함께 확인해야 합니다.'}</strong>
      <p class="detail-copy">위치 일치도 ${Math.round((pin.location_confidence || 0) * 100)}% · ${pin.matched_location ? '기사에서 위치가 직접 확인됨' : '기사 위치가 불명확해 글로벌 핀으로 배치됨'}</p>
    </article>
  `;
  renderImpactMetrics();
  renderEvidence();
}

function renderMapPins(resetView = true) {
  markerLayer.clearLayers();
  markerIndex.clear();
  const colorMap = { '#EF4444': 'red', '#22C55E': 'green', '#F59E0B': 'yellow', '#F97316': 'orange', '#2563EB': 'blue', '#8B5CF6': 'purple' };

  state.news.pins.forEach((pin) => {
    const icon = L.divIcon({
      className: 'map-pin-icon',
      html: `<div class="map-pin-wrap color-${colorMap[pin.pin_color] || 'blue'}${pin.id === state.selectedPinId ? ' is-selected' : ''}"><span class="map-pin-ring"></span><span class="map-pin-core">${pin.country === 'GL' ? 'GL' : (pin.country || '').slice(0, 2)}</span></div>`,
      iconSize: [42, 42],
      iconAnchor: [21, 21],
    });
    const marker = L.marker([pin.lat, pin.lng], { icon }).addTo(markerLayer);
    marker.on('click', () => {
      state.selectedPinId = pin.id;
      renderMapPins(false);
      renderDetail(pin);
    });
    markerIndex.set(pin.id, { marker, pin });
  });

  if (resetView) {
    if (state.news.pins.length && state.category === 'saved') {
      const group = L.featureGroup(Array.from(markerLayer.getLayers()));
      map.fitBounds(group.getBounds().pad(0.25), { maxZoom: 4, animate: true, duration: 0.5 });
      return;
    }
    map.flyTo(currentMeta().center, currentMeta().zoom, { duration: 0.6 });
  }
}

async function fetchMarketMetrics() {
  state.marketMetricsError = '';

  try {
    const [goldResponse, wtiResponse, spResponse] = await Promise.all([
      fetch('/api/market/gold'),
      fetch('/api/market/wti'),
      fetch('/api/market/sp500'),
    ]);

    const [gold, wti, sp500] = await Promise.all([
      goldResponse.json(),
      wtiResponse.json(),
      spResponse.json(),
    ]);

    if (!goldResponse.ok) {
      throw new Error(gold.detail || 'Gold market load failed');
    }
    if (!wtiResponse.ok) {
      throw new Error(wti.detail || 'WTI market load failed');
    }
    if (!spResponse.ok) {
      throw new Error(sp500.detail || 'SP500 market load failed');
    }

    state.marketMetrics = {
      metrics: [
        {
          id: 'gold',
          title: '금 가격',
          subtitle: '',
          value: gold.price,
          unit: gold.unit || 'USD/oz',
          change: gold.series?.length >= 2 ? gold.series.at(-1).y - gold.series.at(-2).y : null,
          updated_at: gold.timestamp,
          series: gold.series || [],
          series_note: '금 선물 일간 시계열',
          source: gold.source || '시장 데이터',
        },
        {
          id: 'wti',
          title: 'WTI 유가',
          subtitle: '',
          value: wti.price,
          unit: wti.unit || 'USD/bbl',
          change: wti.series?.length >= 2 ? wti.series.at(-1).y - wti.series.at(-2).y : null,
          updated_at: wti.timestamp,
          series: wti.series || [],
          series_note: 'WTI 원유 일간 시계열',
          source: wti.source || '시장 데이터',
        },
        {
          id: 'spy',
          title: 'S&P500',
          subtitle: '',
          value: sp500.price,
          unit: sp500.unit || 'USD',
          change: sp500.previous_close != null && sp500.price != null ? sp500.price - sp500.previous_close : null,
          updated_at: sp500.timestamp,
          series: sp500.series || [],
          series_note: 'S&P500 일간 시계열',
          source: sp500.source || '시장 데이터',
        },
      ],
    };
  } catch (error) {
    console.error(error);
    state.marketMetrics = null;
    state.marketMetricsError = `시장 지표를 불러오지 못했습니다. ${error.message}`;
  }
}

async function fetchSavedArticles(showMessage = false) {
  if (!state.auth.authenticated) {
    state.savedArticles = [];
    return [];
  }

  const response = await fetch('/api/articles/saved');
  if (response.status === 401) {
    state.auth = { authenticated: false, nickname: '' };
    state.savedArticles = [];
    renderAuthPanel();
    if (showMessage) {
      alert('로그인이 만료되었습니다. 다시 로그인해 주세요.');
    }
    return [];
  }

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || '저장한 기사를 불러오지 못했습니다.');
  }

  state.savedArticles = Array.isArray(result) ? result : [];
  return state.savedArticles;
}

async function loadSavedCategory() {
  state.category = 'saved';
  state.newsMeta = { sourceType: 'saved', message: '', loadedCategory: 'saved' };
  renderHeader();
  await fetchMarketMetrics();

  if (!state.auth.authenticated) {
    state.news = { articles: [], pins: [] };
    state.selectedPinId = null;
    renderMapFeed();
    renderMapPins(true);
    renderDetail(null);
    return;
  }

  const savedArticles = await fetchSavedArticles();
  state.news = {
    articles: savedArticles.map(buildSavedHeadline),
    pins: savedArticles.map(buildSavedPin),
  };
  state.selectedPinId = state.news.pins[0]?.id || null;
  renderMapFeed();
  renderMapPins(true);
  renderDetail(selectedPin());
}

async function fetchHomeNews(category = 'home') {
  const mapFeedList = document.getElementById('mapFeedList');
  const endpoint = category === 'home'
    ? '/api/news/home'
    : `/api/news/category/${encodeURIComponent(category)}`;

  if (state.category === category && state.newsMeta.loadedCategory === category) {
    return;
  }

  const existingRequest = inFlightNewsRequests.get(category);
  if (existingRequest) {
    await existingRequest;
    return;
  }

  const request = (async () => {
    try {
      const response = await fetch(endpoint);
      const result = await response.json();
      if (!response.ok || !result.success) {
        throw new Error(result.detail || result.message || 'News load failed');
      }

      state.category = category;
      state.news = {
        articles: result.data.top_headlines || [],
        pins: result.data.map_pins || [],
      };
      state.newsMeta = {
        sourceType: result.source_type || '',
        message: result.message || '',
        loadedCategory: category,
      };
      state.selectedPinId = state.news.pins[0]?.id || null;

      await Promise.all([
        fetchMarketMetrics(),
        fetchSavedArticles().catch(() => []),
      ]);

      renderHeader();
      renderAuthPanel();
      renderMapFeed();
      renderMapPins(true);
      renderDetail(selectedPin());
    } catch (error) {
      console.error(error);
      state.category = category;
      state.news = { articles: [], pins: [] };
      state.newsMeta = { sourceType: 'error', message: `News load failed: ${error.message}`, loadedCategory: category };
      renderHeader();
      mapFeedList.innerHTML = `<div class="map-feed-empty">${state.newsMeta.message}</div>`;
      renderDetail(null);
    } finally {
      if (inFlightNewsRequests.get(category) === request) {
        inFlightNewsRequests.delete(category);
      }
    }
  })();

  inFlightNewsRequests.set(category, request);
  await request;
}

async function loadCategory(category) {
  if (category === state.category && state.newsMeta.loadedCategory === category) {
    return;
  }

  if (category === 'saved') {
    try {
      await loadSavedCategory();
    } catch (error) {
      console.error(error);
      state.news = { articles: [], pins: [] };
      state.selectedPinId = null;
      renderHeader();
      renderMapFeed();
      renderMapPins(true);
      renderDetail(null);
    }
    return;
  }

  await fetchHomeNews(category);
}

async function loadSession() {
  try {
    const response = await fetch('/api/auth/session');
    const result = await response.json();
    if (response.ok && result.authenticated) {
      state.auth = { authenticated: true, nickname: result.nickname || '' };
      await fetchSavedArticles().catch(() => []);
    } else {
      state.auth = { authenticated: false, nickname: '' };
      state.savedArticles = [];
    }
  } catch (error) {
    console.error(error);
    state.auth = { authenticated: false, nickname: '' };
    state.savedArticles = [];
  }
  renderAuthPanel();
}

async function loginWithNickname(nickname) {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nickname }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || '로그인에 실패했습니다.');
  }
  state.auth = { authenticated: true, nickname: result.nickname || nickname };
  await fetchSavedArticles().catch(() => []);
  renderAuthPanel();
  renderDetail(selectedPin());
}

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  state.auth = { authenticated: false, nickname: '' };
  state.savedArticles = [];
  renderAuthPanel();
  if (state.category === 'saved') {
    await loadSavedCategory();
  } else {
    renderDetail(selectedPin());
  }
}

async function saveSelectedArticle() {
  const pin = selectedPin();
  if (!pin) {
    return;
  }
  if (!state.auth.authenticated) {
    alert('닉네임 로그인 후 저장할 수 있습니다.');
    return;
  }
  if (isSavedPin(pin)) {
    return;
  }

  const payload = {
    article_id: pin.id,
    title: pin.title,
    url: pin.url,
    category: pin.category || state.category,
    source: pin.source,
    summary: pin.summary,
    region: pin.location_label || pin.country_name || pin.country,
    continent: null,
    location_label: pin.location_label || pin.country_name || pin.country,
    country: pin.country,
    country_name: pin.country_name,
    lat: pin.lat,
    lng: pin.lng,
    pin_color: pin.pin_color,
  };

  const response = await fetch('/api/articles/saved', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || '기사 저장에 실패했습니다.');
  }

  await fetchSavedArticles();
  renderDetail(selectedPin());
}

async function deleteSavedArticle(savedId) {
  const response = await fetch(`/api/articles/saved/${savedId}`, { method: 'DELETE' });
  if (!response.ok) {
    let detail = '저장한 기사 삭제에 실패했습니다.';
    try {
      const result = await response.json();
      detail = result.detail || detail;
    } catch (error) {
      console.error(error);
    }
    throw new Error(detail);
  }
  await fetchSavedArticles();
  if (state.category === 'saved') {
    await loadSavedCategory();
  } else {
    renderDetail(selectedPin());
  }
}

document.addEventListener('click', async (event) => {
  const tab = event.target.closest('.view-tab');
  if (tab) {
    await loadCategory(tab.dataset.category);
    return;
  }

  const openButton = event.target.closest('[data-open-url]');
  if (openButton?.dataset.openUrl) {
    window.open(openButton.dataset.openUrl, '_blank', 'noopener,noreferrer');
    return;
  }

  const focusButton = event.target.closest('[data-focus-pin]');
  if (focusButton) {
    const target = markerIndex.get(focusButton.dataset.focusPin);
    if (target) {
      map.flyTo([target.pin.lat, target.pin.lng], Math.max(map.getZoom(), 4), { duration: 0.8 });
    }
    return;
  }

  const saveButton = event.target.closest('[data-save-article]');
  if (saveButton) {
    try {
      await saveSelectedArticle();
    } catch (error) {
      console.error(error);
      alert(error.message);
    }
    return;
  }

  const removeButton = event.target.closest('[data-remove-saved]');
  if (removeButton) {
    try {
      await deleteSavedArticle(removeButton.dataset.removeSaved);
    } catch (error) {
      console.error(error);
      alert(error.message);
    }
    return;
  }

  if (event.target.closest('[data-logout]')) {
    await logout();
    return;
  }

  if (event.target.closest('[data-open-saved-tab]')) {
    await loadCategory('saved');
  }
});

document.addEventListener('submit', async (event) => {
  const loginForm = event.target.closest('#loginForm');
  if (!loginForm) {
    return;
  }
  event.preventDefault();
  const formData = new FormData(loginForm);
  const nickname = String(formData.get('nickname') || '').trim();
  if (!nickname) {
    return;
  }
  try {
    await loginWithNickname(nickname);
  } catch (error) {
    console.error(error);
    alert(error.message);
  }
});

document.addEventListener('DOMContentLoaded', async () => {
  map = L.map('map', { zoomControl: false, attributionControl: true, minZoom: 2 }).setView(categoryMeta.home.center, categoryMeta.home.zoom);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    subdomains: 'abcd',
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
  }).addTo(map);
  markerLayer = L.layerGroup().addTo(map);

  renderHeader();
  renderAuthPanel();
  renderImpactMetrics();
  renderEvidence();
  await loadSession();
  await loadCategory('home');
});
