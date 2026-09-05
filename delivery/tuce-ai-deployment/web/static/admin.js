// 留资数据查看界面
// - GET /api/v1/leads 拉取线索，请求头 X-Admin-Token 携带口令
// - 401 时弹出口令输入框，口令存 sessionStorage 后重试
// - 统计总数/今日新增（北京时间），支持刷新与 CSV 导出（带 BOM 兼容 Excel）

const leadsBody = document.getElementById('leads-body');
const emptyTip = document.getElementById('empty-tip');
const adminError = document.getElementById('admin-error');
const statTotal = document.getElementById('stat-total');
const statToday = document.getElementById('stat-today');
const statReports = document.getElementById('stat-reports');
const resultCount = document.getElementById('result-count');
const searchInput = document.getElementById('lead-search');
const refreshBtn = document.getElementById('refresh-btn');
const exportBtn = document.getElementById('export-btn');
const clearBtn = document.getElementById('clear-btn');
const adminStatus = document.getElementById('admin-status');
let loading = false;
let clearing = false;

const tokenOverlay = document.getElementById('token-overlay');
const tokenForm = document.getElementById('token-form');
const tokenInput = document.getElementById('token-input');
const tokenError = document.getElementById('token-error');

const reportOverlay = document.getElementById('report-overlay');
const reportClose = document.getElementById('report-close');
const reportMeta = document.getElementById('report-meta');
const reportBody = document.getElementById('report-body');

const TOKEN_KEY = 'adminToken';

let leads = [];
let query = '';
let reportTrigger = null;

function token() {
  return sessionStorage.getItem(TOKEN_KEY) || '';
}

function fmtGpa(lead) {
  if (lead.gpa == null) return '—';
  return lead.gpa_scale ? `${lead.gpa} / ${lead.gpa_scale}` : `${lead.gpa}（满分未记录）`;
}

// 留资时间存的是 UTC ISO，展示转北京时间
function fmtTime(iso) {
  return new Date(iso).toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour12: false,
  });
}

function isTodayCN(iso) {
  const fmt = { timeZone: 'Asia/Shanghai' };
  return (
    new Date(iso).toLocaleDateString('zh-CN', fmt) ===
    new Date().toLocaleDateString('zh-CN', fmt)
  );
}

function showError(msg) {
  adminError.textContent = msg;
  adminError.hidden = false;
}

async function loadData() {
  if (loading || clearing) return;
  loading = true;
  clearBtn.disabled = true;
  adminError.hidden = true;
  refreshBtn.disabled = true;
  refreshBtn.classList.add('is-loading');
  try {
    const res = await fetch('/api/v1/leads', {
      headers: { 'X-Admin-Token': token() },
    });
    if (res.status === 401) {
      openTokenModal();
      return;
    }
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      showError(error.detail || `数据加载失败（${res.status}）`);
      return;
    }
    const data = await res.json();
    leads = data.leads || [];
    render();
  } catch (err) {
    if (err instanceof TypeError) {
      showError('网络异常，请检查连接后重试');
    }
    console.error(err);
  } finally {
    loading = false;
    clearBtn.disabled = clearing || !leads.length;
    refreshBtn.disabled = false;
    refreshBtn.classList.remove('is-loading');
  }
}

function render() {
  clearBtn.disabled = loading || clearing || !leads.length;
  statTotal.textContent = leads.length;
  statToday.textContent = leads.filter((l) => isTodayCN(l.created_at)).length;
  statReports.textContent = leads.filter((l) => l.result_json).length;

  const normalized = query.toLocaleLowerCase('zh-CN');
  const visibleLeads = leads.filter((lead) =>
    [lead.wechat, lead.phone, lead.major, lead.target_country, lead.school_tier, lead.degree]
      .some((value) => String(value ?? '').toLocaleLowerCase('zh-CN').includes(normalized))
  );
  resultCount.textContent = query
    ? `找到 ${visibleLeads.length} 条匹配结果`
    : `共 ${leads.length} 条记录`;

  leadsBody.innerHTML = '';
  for (const lead of visibleLeads) {
    const tr = document.createElement('tr');
    const language =
      lead.language_score != null
        ? `${lead.language_type || ''} ${lead.language_score}`.trim()
        : '';
    const cells = [
      ['编号', `#${lead.id}`],
      ['留资时间', fmtTime(lead.created_at)],
      ['微信', lead.wechat],
      ['手机', lead.phone],
      ['GPA / 均分', fmtGpa(lead)],
      ['专业', lead.major ?? '—'],
      ['目标国家', lead.target_country ?? '—'],
      ['院校档次', lead.school_tier ?? '—'],
      ['学位', lead.degree ?? '—'],
      ['语言成绩', language || '—'],
    ];
    cells.forEach(([label, value]) => {
      const td = document.createElement('td');
      td.textContent = value;
      td.dataset.label = label;
      tr.appendChild(td);
    });

    // 报告列：有结果入库的线索可点开查看选校推荐（P1）
    const reportTd = document.createElement('td');
    reportTd.dataset.label = '测评报告';
    if (lead.result_json) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-ghost view-report-btn';
      btn.innerHTML = '查看报告 <span aria-hidden="true">→</span>';
      btn.addEventListener('click', () => openReportModal(lead));
      reportTd.appendChild(btn);
    } else {
      reportTd.textContent = '—';
    }
    tr.appendChild(reportTd);

    leadsBody.appendChild(tr);
  }
  emptyTip.hidden = visibleLeads.length > 0;
  emptyTip.querySelector('strong').textContent = leads.length ? '没有找到相关线索' : '暂无留资记录';
  emptyTip.querySelector('small').textContent = leads.length ? '可以尝试调整搜索关键词' : '新的用户留资后将显示在这里';
  document.querySelector('.table-wrap').hidden = visibleLeads.length === 0;
}

searchInput.addEventListener('input', () => {
  query = searchInput.value.trim();
  render();
});

// 测评报告弹窗（P1）
const LEVEL_CLASS = { 冲刺: 'reach', 匹配: 'match', 保底: 'safety' };

function openReportModal(lead) {
  reportTrigger = document.activeElement;
  reportMeta.textContent = [
    `微信 ${lead.wechat}`,
    lead.gpa != null ? `GPA / 均分 ${fmtGpa(lead)}` : '',
    lead.major || '',
    lead.target_country || '',
  ]
    .filter(Boolean)
    .join(' · ');

  reportBody.innerHTML = '';
  let tiers;
  try {
    tiers = JSON.parse(lead.result_json).tiers;
  } catch (_) {
    tiers = null;
  }
  if (!Array.isArray(tiers) || tiers.length === 0) {
    reportBody.textContent = '报告数据异常，无法解析';
    showReportModal();
    return;
  }

  for (const tier of tiers) {
    const card = document.createElement('div');
    card.className = 'tier-card';

    const header = document.createElement('div');
    header.className = `tier-header ${LEVEL_CLASS[tier.level] || 'match'}`;
    header.textContent = tier.level;

    const body = document.createElement('div');
    body.className = 'tier-body';
    for (const school of tier.schools || []) {
      const item = document.createElement('div');
      item.className = 'school-item';

      const name = document.createElement('div');
      name.className = 'school-name';
      name.textContent = school.name;

      const reason = document.createElement('div');
      reason.className = 'school-reason';
      reason.textContent = school.reason;

      item.appendChild(name);
      item.appendChild(reason);
      body.appendChild(item);
    }

    card.appendChild(header);
    card.appendChild(body);
    reportBody.appendChild(card);
  }
  showReportModal();
}

function showReportModal() {
  reportOverlay.hidden = false;
  reportOverlay.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
  reportClose.focus();
}

function closeReportModal() {
  reportOverlay.hidden = true;
  reportOverlay.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('modal-open');
  if (reportTrigger instanceof HTMLElement) reportTrigger.focus();
}

reportClose.addEventListener('click', closeReportModal);
reportOverlay.addEventListener('click', (e) => {
  if (e.target === reportOverlay) closeReportModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !reportOverlay.hidden) closeReportModal();
  if (e.key === 'Tab' && !reportOverlay.hidden) {
    e.preventDefault();
    reportClose.focus();
  }
});

// 口令弹窗
function openTokenModal() {
  tokenError.hidden = true;
  tokenInput.value = '';
  tokenOverlay.hidden = false;
  tokenOverlay.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
  tokenInput.focus();
}

tokenForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const value = tokenInput.value.trim();
  if (!value) {
    tokenError.textContent = '请输入口令';
    tokenError.hidden = false;
    return;
  }
  try {
    const res = await fetch('/api/v1/leads', {
      headers: { 'X-Admin-Token': value },
    });
    if (res.status === 401) {
      tokenError.textContent = '口令不正确';
      tokenError.hidden = false;
      return;
    }
    sessionStorage.setItem(TOKEN_KEY, value);
    tokenOverlay.hidden = true;
    tokenOverlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
    if (res.ok) {
      const data = await res.json();
      leads = data.leads || [];
      render();
    } else {
      const error = await res.json().catch(() => ({}));
      showError(error.detail || `数据加载失败（${res.status}）`);
    }
  } catch (err) {
    if (err instanceof TypeError) {
      tokenError.textContent = '网络异常，请重试';
      tokenError.hidden = false;
    }
    console.error(err);
  }
});

// CSV 导出：纯前端生成，带 BOM 保证 Excel 正确识别中文
function exportCsv() {
  if (!leads.length) return;
  const headers = [
    'ID', '留资时间', '微信', '手机', 'GPA / 均分', '专业',
    '目标国家', '院校档次', '学位', '语言成绩',
  ];
  const rows = leads.map((lead) => [
    lead.id,
    fmtTime(lead.created_at),
    lead.wechat,
    lead.phone,
    lead.gpa != null ? fmtGpa(lead) : '',
    lead.major ?? '',
    lead.target_country ?? '',
    lead.school_tier ?? '',
    lead.degree ?? '',
    lead.language_score != null
      ? `${lead.language_type || ''} ${lead.language_score}`.trim()
      : '',
  ]);
  const csv =
    '﻿' +
    [headers, ...rows]
      .map((row) =>
        row
          .map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`)
          .join(',')
      )
      .join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `leads-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function clearHistory() {
  if (loading || clearing || !leads.length) return;
  const confirmation = window.prompt('将永久清除全部历史留资（包括搜索结果之外的记录），无法撤销。建议先导出 CSV。测评报告仍会保留。\n\n请输入“确认清除”继续：');
  if (confirmation !== '确认清除') return;
  clearing = true;
  clearBtn.disabled = true;
  refreshBtn.disabled = true;
  exportBtn.disabled = true;
  clearBtn.textContent = '正在清除…';
  adminError.hidden = true;
  adminStatus.hidden = true;
  try {
    const res = await fetch('/api/v1/leads', {
      method: 'DELETE',
      headers: { 'X-Admin-Token': token(), 'X-Confirm-Clear': 'clear-all-leads' },
    });
    if (res.status === 401) {
      openTokenModal();
      return;
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '清除失败，请重试');
    leads = [];
    query = '';
    searchInput.value = '';
    closeReportModal();
    reportBody.innerHTML = '';
    reportMeta.textContent = '';
    render();
    adminStatus.textContent = `已清除 ${data.deleted} 条历史留资。`;
    adminStatus.hidden = false;
  } catch (err) {
    showError(err instanceof TypeError ? '网络异常，操作结果尚未确认，请刷新核实后再操作' : err.message);
  } finally {
    clearing = false;
    clearBtn.disabled = !leads.length;
    refreshBtn.disabled = false;
    exportBtn.disabled = false;
    clearBtn.textContent = '清除历史留资';
  }
}

clearBtn.addEventListener('click', clearHistory);
refreshBtn.addEventListener('click', loadData);
exportBtn.addEventListener('click', exportCsv);

loadData();
