/* 官网接入：设置 data-url 为部署后的测评 HTTPS 地址。不会读取或发送官网表单数据。 */
(() => {
  const script = document.currentScript;
  const rawUrl = script?.dataset.url;
  if (!rawUrl || document.getElementById('tuce-ai-widget')) return;
  let url;
  try { url = new URL(rawUrl, window.location.href); } catch { return; }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !(local && url.protocol === 'http:')) return;
  if (url.username || url.password) return;
  const mount = () => {
    if (document.getElementById('tuce-ai-widget')) return;
    const host = document.createElement('div');
    host.id = 'tuce-ai-widget';
    host.style.cssText = 'all:initial;position:fixed;right:20px;bottom:max(88px,env(safe-area-inset-bottom));z-index:10000;display:block;';
    const shadow = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = `
      a{box-sizing:border-box;display:flex;align-items:center;gap:10px;padding:13px 19px;
        border:1px solid #bc985b;border-radius:999px;background:#152b27;color:#fff;
        box-shadow:0 6px 24px #152b2733;text-decoration:none;font:600 14px/1.4 system-ui,-apple-system,"PingFang SC",sans-serif;transition:background .15s;}
      a:hover{background:#25463e}a:focus-visible{outline:3px solid #bd995d;outline-offset:4px}
      .spark{color:#e0bf83;font-size:22px;line-height:1}
      @media(max-width:480px){a{padding:12px 15px;font-size:13px}}
      @media(prefers-reduced-motion:reduce){a{transition:none}}
    `;
    const link = document.createElement('a');
    link.href = url.href;
    link.setAttribute('aria-label', 'AI 智能选校，进入免费测评');
    const spark = document.createElement('span');
    spark.className = 'spark';
    spark.textContent = '✦';
    spark.setAttribute('aria-hidden', 'true');
    link.append(spark, document.createTextNode('AI 智能选校'));
    shadow.append(style, link);
    document.body.append(host);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
