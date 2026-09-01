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
const modalClose = document.getElementById('modal-close');
const leadForm = document.getElementById('lead-form');
const leadSubmitBtn = document.getElementById('lead-submit');
const fillExampleBtn = document.getElementById('fill-example-btn');

let currentContext = null; // 最近一次测评背景 { gpa, major, target_country }
let currentReportId = null; // 服务端保存的报告 ID，留资时只提交该 ID
let modalTrigger = null;
let loadingTimer = null;
const LANGUAGE_RULES = {
  雅思: { min: 0, max: 9, step: 0.5, example: '例：7.0' },
  托福: { min: 0, max: 120, step: 1, example: '例：100' },
  '托福（1–6分制）': { min: 1, max: 6, step: 0.5, example: '例：5.0' },
};

function syncInputHints() {
  const scale = Number(document.getElementById('gpa-scale').value);
  const gpaInput = document.getElementById('gpa');
  gpaInput.max = String(scale);
  gpaInput.placeholder = scale === 100 ? '例：85' : scale === 5 ? '例：4.2' : '例：3.6';
  document.getElementById('gpa-hint').textContent = `按成绩单原始分数填写，满分 ${scale}`;
  const other = document.getElementById('country').value === '其他';
  document.getElementById('country-other-field').hidden = !other;
  document.getElementById('country-other').disabled = !other;
  document.getElementById('country-other').required = other;
  const rule = LANGUAGE_RULES[document.getElementById('lang-type').value];
  const scoreInput = document.getElementById('lang-score');
  scoreInput.min = String(rule?.min ?? 0);
  scoreInput.max = String(rule?.max ?? 120);
  scoreInput.step = String(rule?.step ?? 0.5);
  scoreInput.placeholder = rule?.example || '先选择语言类型';
  document.getElementById('language-hint').textContent = rule
    ? `总分 ${rule.min}～${rule.max}，以 ${rule.step} 分递增；未考可留空`
    : '语言类型与总分需一起填写；未考可留空';
}

['gpa-scale', 'country', 'lang-type'].forEach((id) => {
  document.getElementById(id).addEventListener('change', syncInputHints);
});
syncInputHints();

// 档位 → CSS 类名映射
const LEVEL_CLASS = {
  冲刺: 'reach',
  匹配: 'match',
  保底: 'safety',
};

// 中国大陆手机号：1 开头共 11 位
const PHONE_RE = /^1[3-9]\d{9}$/;

// 一键填入演示背景，仅填表、不自动提交，方便用户了解格式与修改内容
fillExampleBtn.addEventListener('click', () => {
  document.getElementById('gpa-scale').value = '4';
  document.getElementById('gpa').value = '3.7';
  document.getElementById('major').value = '计算机科学';
  document.getElementById('country').value = '美国';
  document.getElementById('school-tier').value = '211';
  document.getElementById('degree').value = '硕士';
  document.getElementById('lang-type').value = '雅思';
  document.getElementById('lang-score').value = '7';
  document.getElementById('country-other').value = '';
  syncInputHints();
  clearFieldErrors(form);
  hideFormError(form);
});

// ---- 表单校验与错误提示（D7） ----

function setFieldError(input, msg) {
  const field = input.closest('.field');
  let errEl = field.querySelector('.field-error');
  if (!errEl) {
    errEl = document.createElement('span');
    errEl.className = 'field-error';
    field.appendChild(errEl);
  }
  errEl.textContent = msg;
  input.classList.add('invalid');
}

function clearFieldErrors(formEl) {
  formEl.querySelectorAll('.field-error').forEach((el) => el.remove());
  formEl.querySelectorAll('.invalid').forEach((el) => el.classList.remove('invalid'));
}

function showFormError(formEl, msg) {
  let errEl = formEl.querySelector('.form-error');
  if (!errEl) {
    errEl = document.createElement('div');
    errEl.className = 'form-error';
    formEl.appendChild(errEl);
  }
  errEl.textContent = msg;
  errEl.hidden = false;
}

function hideFormError(formEl) {
  const errEl = formEl.querySelector('.form-error');
  if (errEl) errEl.hidden = true;
}

// 提取服务端错误信息：优先返回接口返回的 detail，网络异常给固定提示
async function serverMessage(res) {
  try {
    const data = await res.json();
    if (data.detail) return data.detail;
  } catch (_) {
    /* 响应不是 JSON，走默认提示 */
  }
  return `请求失败（${res.status}）`;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const gpaInput = document.getElementById('gpa');
  const majorInput = document.getElementById('major');
  const countryInput = document.getElementById('country');
  const tierInput = document.getElementById('school-tier');
  const degreeInput = document.getElementById('degree');
  const langTypeInput = document.getElementById('lang-type');
  const langScoreInput = document.getElementById('lang-score');

  clearFieldErrors(form);
  hideFormError(form);

  const gpa = gpaInput.valueAsNumber;
  const gpaScale = Number(document.getElementById('gpa-scale').value);
  const major = majorInput.value.trim();
  const country = countryInput.value === '其他'
    ? document.getElementById('country-other').value.trim()
    : countryInput.value;
  const schoolTier = tierInput.value;
  const degree = degreeInput.value;
  const langType = langTypeInput.value;
  const langScoreRaw = langScoreInput.value.trim();
  const langScore = langScoreRaw === '' ? NaN : langScoreInput.valueAsNumber;

  if (!Number.isFinite(gpa) || gpa < 0.01 || gpa > gpaScale) {
    setFieldError(gpaInput, `GPA / 均分需大于 0 且不超过所选满分 ${gpaScale}`);
    return;
  }
  if (!major || major.length > 50) {
    setFieldError(majorInput, '请填写申请专业（最多 50 字）');
    return;
  }
  if (!country || country === '其他' || country.length > 30) {
    setFieldError(countryInput.value === '其他' ? document.getElementById('country-other') : countryInput,
      '请填写具体的目标国家或地区（最多 30 字）');
    return;
  }
  // 语言类型与成绩需成对填写
  if ((langType && Number.isNaN(langScore)) || (!langType && !Number.isNaN(langScore))) {
    setFieldError(langScoreInput, '语言类型和成绩需一起填写');
    return;
  }
  if (!Number.isNaN(langScore)) {
    const rule = LANGUAGE_RULES[langType];
    if (!rule || !Number.isFinite(langScore) || langScore < rule.min || langScore > rule.max || langScore % rule.step !== 0) {
      setFieldError(langScoreInput, `${langType}成绩需为 ${rule?.min}～${rule?.max}，以 ${rule?.step} 分递增`);
      return;
    }
  }

  setLoading(true);
  try {
    const payload = { gpa, gpa_scale: gpaScale, major, target_country: country };
    if (schoolTier) payload.school_tier = schoolTier;
    if (degree) payload.degree = degree;
    if (langType && !Number.isNaN(langScore)) {
      payload.language_type = langType;
      payload.language_score = langScore;
    }
    const res = await fetch('/api/v1/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await serverMessage(res));
    const data = await res.json();
    currentContext = {
      gpa,
      gpa_scale: gpaScale,
      major,
      target_country: country,
      school_tier: schoolTier || null,
      degree: degree || null,
      language_type: langType || null,
      language_score: Number.isNaN(langScore) ? null : langScore,
    };
    currentReportId = data.report_id;
    renderTiers(data.tiers);
    unlockBtn.hidden = false;
    document.getElementById('result-tip').hidden = false;
    document.getElementById('thank-you').hidden = true;
    resultArea.hidden = false;
    resultArea.scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    const msg =
      err instanceof TypeError
        ? '网络异常，请检查连接后重试'
        : err.message || '测评失败，请稍后重试';
    showFormError(form, msg);
    console.error(err);
  } finally {
    setLoading(false);
  }
});

function setLoading(loading) {
  clearTimeout(loadingTimer);
  fillExampleBtn.disabled = loading;
  const status = document.getElementById('evaluate-status');
  status.hidden = !loading;
  status.textContent = loading ? '正在生成初步建议，请稍候，无需重复提交。' : '';
  if (loading) loadingTimer = setTimeout(() => {
    status.textContent = 'AI 仍在生成建议，可能需要更长时间；请保留此页面。';
  }, 20000);
  submitBtn.disabled = loading;
  unlockBtn.disabled = loading;
  submitBtn.innerHTML = loading
    ? '<span class="spinner"></span>正在分析申请背景...'
    : '生成我的选校建议 <span aria-hidden="true">→</span>';
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
      reason.textContent = school.reason || '留资后查看完整推荐理由';

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
  modalTrigger = document.activeElement;
  modalOverlay.hidden = false;
  document.body.classList.add('modal-open');
  modalOverlay.setAttribute('aria-hidden', 'false');
  window.setTimeout(() => document.getElementById('wechat').focus(), 0);
}

function closeModal() {
  modalOverlay.hidden = true;
  document.body.classList.remove('modal-open');
  modalOverlay.setAttribute('aria-hidden', 'true');
  if (modalTrigger instanceof HTMLElement) modalTrigger.focus();
}

unlockBtn.addEventListener('click', openModal);
modalCancel.addEventListener('click', closeModal);
modalClose.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', (e) => {
  if (e.target === modalOverlay) closeModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !modalOverlay.hidden) closeModal();
  if (e.key === 'Tab' && !modalOverlay.hidden) {
    const focusable = [...modalOverlay.querySelectorAll('button:not([disabled]), input:not([disabled])')];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
});

leadForm.addEventListener('input', (e) => {
  if (!(e.target instanceof HTMLInputElement)) return;
  e.target.classList.remove('invalid');
  e.target.closest('.field')?.querySelector('.field-error')?.remove();
  hideFormError(leadForm);
});

// 留资提交（D5 实现）
leadForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const wechatInput = document.getElementById('wechat');
  const phoneInput = document.getElementById('phone');

  clearFieldErrors(leadForm);
  hideFormError(leadForm);

  const wechat = wechatInput.value.trim();
  const phone = phoneInput.value.trim();

  if (wechat.length < 2) {
    setFieldError(wechatInput, '请填写微信号');
    wechatInput.focus();
    return;
  }
  if (!PHONE_RE.test(phone)) {
    setFieldError(phoneInput, '请填写正确的 11 位手机号');
    phoneInput.focus();
    return;
  }

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
        gpa_scale: currentContext?.gpa_scale ?? null,
        major: currentContext?.major ?? null,
        target_country: currentContext?.target_country ?? null,
        school_tier: currentContext?.school_tier ?? null,
        degree: currentContext?.degree ?? null,
        language_type: currentContext?.language_type ?? null,
        language_score: currentContext?.language_score ?? null,
        report_id: currentReportId,
      }),
    });
    if (!res.ok) throw new Error(await serverMessage(res));
    const data = await res.json();
    if (!data.report?.tiers) throw new Error('报告加载失败，请联系顾问');
    renderTiers(data.report.tiers);
    unlockReport();
    closeModal();
    leadForm.reset();
  } catch (err) {
    const msg =
      err instanceof TypeError
        ? '网络异常，请检查连接后重试'
        : err.message || '提交失败，请稍后重试';
    showFormError(leadForm, msg);
    console.error(err);
  } finally {
    leadSubmitBtn.disabled = false;
    leadSubmitBtn.innerHTML = '立即解锁完整报告 <span aria-hidden="true">→</span>';
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
