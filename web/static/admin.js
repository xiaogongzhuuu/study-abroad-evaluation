// 留资数据查看界面
// - GET /api/v1/leads 拉取线索，请求头 X-Admin-Token 携带口令
// - 401 时弹出口令输入框，口令存 sessionStorage 后重试
// - 统计总数/今日新增（北京时间），支持刷新与 CSV 导出（带 BOM 兼容 Excel）

const leadsBody = document.getElementById('leads-body');
const emptyTip = document.getElementById('empty-tip');
const adminError = document.getElementById('admin-error');
const statTotal = document.getElementById('stat-total');
const statToday = document.getElementById('stat-today');
const refreshBtn = document.getElementById('refresh-btn');
const exportBtn = document.getElementById('export-btn');

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

function token() {
  return sessionStorage.getItem(TOKEN_KEY) || '';
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
  adminError.hidden = true;
  try {
    const res = await fetch('/api/v1/leads', {
      headers: { 'X-Admin-Token': token() },
    });
    if (res.status === 401) {
      openTokenModal();
      return;
    }
    if (!res.ok) {
      showError(`数据加载失败（${res.status}）`);
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
  }
}

function render() {
  statTotal.textContent = leads.length;
  statToday.textContent = leads.filter((l) => isTodayCN(l.created_at)).length;

  leadsBody.innerHTML = '';
  for (const lead of leads) {
    const tr = document.createElement('tr');
    const language =
      lead.language_score != null
        ? `${lead.language_type || ''} ${lead.language_score}`.trim()
        : '';
    [
      lead.id,
      fmtTime(lead.created_at),
      lead.wechat,
      lead.phone,
      lead.gpa ?? '',
      lead.major ?? '',
      lead.target_country ?? '',
      lead.school_tier ?? '',
      lead.degree ?? '',
      language,
    ].forEach((value) => {
      const td = document.createElement('td');
      td.textContent = value;
      tr.appendChild(td);
    });

    // 报告列：有结果入库的线索可点开查看选校推荐（P1）
    const reportTd = document.createElement('td');
    if (lead.result_json) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-ghost view-report-btn';
      btn.textContent = '查看';
      btn.addEventListener('click', () => openReportModal(lead));
      reportTd.appendChild(btn);
    } else {
      reportTd.textContent = '—';
    }
    tr.appendChild(reportTd);

    leadsBody.appendChild(tr);
  }
  emptyTip.hidden = leads.length > 0;
}

// 测评报告弹窗（P1）
const LEVEL_CLASS = { 冲刺: 'reach', 匹配: 'match', 保底: 'safety' };

function openReportModal(lead) {
  reportMeta.textContent = [
    `微信 ${lead.wechat}`,
    lead.gpa != null ? `GPA ${lead.gpa}` : '',
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
    reportOverlay.hidden = false;
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
  reportOverlay.hidden = false;
}

reportClose.addEventListener('click', () => {
  reportOverlay.hidden = true;
});
reportOverlay.addEventListener('click', (e) => {
  if (e.target === reportOverlay) reportOverlay.hidden = true;
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !reportOverlay.hidden) reportOverlay.hidden = true;
});

// 口令弹窗
function openTokenModal() {
  tokenError.hidden = true;
  tokenInput.value = '';
  tokenOverlay.hidden = false;
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
    if (res.ok) {
      const data = await res.json();
      leads = data.leads || [];
      render();
    } else {
      showError(`数据加载失败（${res.status}）`);
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
    'ID', '留资时间', '微信', '手机', 'GPA', '专业',
    '目标国家', '院校档次', '学位', '语言成绩',
  ];
  const rows = leads.map((lead) => [
    lead.id,
    fmtTime(lead.created_at),
    lead.wechat,
    lead.phone,
    lead.gpa ?? '',
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

refreshBtn.addEventListener('click', loadData);
exportBtn.addEventListener('click', exportCsv);

loadData();
