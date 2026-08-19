// 前端交互逻辑（D4 实现）
// - 表单提交 → 调用 POST /api/v1/evaluate
// - 结果卡片动态渲染（三档 6 校）
// - 留资弹窗：模糊遮罩 + 解锁入口

const form = document.getElementById('evaluate-form');
const submitBtn = document.getElementById('submit-btn');
const resultArea = document.getElementById('result-area');
const tiersEl = document.getElementById('tiers');
const unlockBtn = document.getElementById('unlock-btn');

const modalOverlay = document.getElementById('modal-overlay');
const modalCancel = document.getElementById('modal-cancel');
const leadForm = document.getElementById('lead-form');
const leadSubmitBtn = document.getElementById('lead-submit');

let currentContext = null; // 最近一次测评背景 { gpa, major, target_country }

// 档位 → CSS 类名映射
const LEVEL_CLASS = {
  冲刺: 'reach',
  匹配: 'match',
  保底: 'safety',
};

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const gpa = parseFloat(document.getElementById('gpa').value);
  const major = document.getElementById('major').value.trim();
  const country = document.getElementById('country').value;

  if (!gpa || Number.isNaN(gpa)) {
    alert('请填写有效的 GPA');
    return;
  }
  if (!major) {
    alert('请填写申请专业');
    return;
  }
  if (!country) {
    alert('请选择目标国家');
    return;
  }

  setLoading(true);
  try {
    const res = await fetch('/api/v1/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gpa, major, target_country: country }),
    });
    if (!res.ok) throw new Error(`请求失败：${res.status}`);
    const data = await res.json();
    currentContext = { gpa, major, target_country: country };
    renderTiers(data.tiers);
    resultArea.hidden = false;
    resultArea.scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    alert('测评失败，请稍后重试');
    console.error(err);
  } finally {
    setLoading(false);
  }
});

function setLoading(loading) {
  submitBtn.disabled = loading;
  submitBtn.innerHTML = loading
    ? '<span class="spinner"></span>测评中...'
    : '开始测评';
}

function renderTiers(tiers) {
  tiersEl.innerHTML = '';
  for (const tier of tiers) {
    const card = document.createElement('div');
    card.className = 'tier-card';

    const header = document.createElement('div');
    header.className = `tier-header ${LEVEL_CLASS[tier.level] || 'match'}`;
    header.textContent = tier.level;

    const body = document.createElement('div');
    body.className = 'tier-body';

    for (const school of tier.schools) {
      const item = document.createElement('div');
      item.className = 'school-item';

      const name = document.createElement('div');
      name.className = 'school-name';
      name.textContent = school.name;

      const reason = document.createElement('div');
      reason.className = 'school-reason blurred';
      reason.textContent = school.reason;

      item.appendChild(name);
      item.appendChild(reason);
      body.appendChild(item);
    }

    card.appendChild(header);
    card.appendChild(body);
    tiersEl.appendChild(card);
  }
}

// 留资弹窗：解锁入口
function openModal() {
  modalOverlay.hidden = false;
}

function closeModal() {
  modalOverlay.hidden = true;
}

unlockBtn.addEventListener('click', openModal);
modalCancel.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', (e) => {
  if (e.target === modalOverlay) closeModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !modalOverlay.hidden) closeModal();
});

// 留资提交（D5 实现）
leadForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const wechat = document.getElementById('wechat').value.trim();
  const phone = document.getElementById('phone').value.trim();
  if (!wechat || !phone) return;

  leadSubmitBtn.disabled = true;
  leadSubmitBtn.innerHTML = '<span class="spinner"></span>解锁中...';
  try {
    const res = await fetch('/api/v1/leads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        wechat,
        phone,
        gpa: currentContext?.gpa ?? null,
        major: currentContext?.major ?? null,
        target_country: currentContext?.target_country ?? null,
      }),
    });
    if (!res.ok) throw new Error(`请求失败：${res.status}`);
    unlockReport();
    closeModal();
  } catch (err) {
    alert('提交失败，请稍后重试');
    console.error(err);
  } finally {
    leadSubmitBtn.disabled = false;
    leadSubmitBtn.innerHTML = '解锁完整报告';
  }
});

// 解锁：去除模糊遮罩 + 隐藏解锁按钮 + 展示感谢信息
function unlockReport() {
  document
    .querySelectorAll('.school-reason.blurred')
    .forEach((el) => el.classList.remove('blurred'));

  unlockBtn.hidden = true;
  document.getElementById('result-tip').hidden = true;
  document.getElementById('thank-you').hidden = false;
}
