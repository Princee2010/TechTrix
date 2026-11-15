// Shared helpers used by every page.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtSize = b => b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
const fmtDate = s => s ? new Date(s.replace(' ', 'T') + 'Z').toLocaleDateString(undefined, {day: 'numeric', month: 'short', year: 'numeric'}) : '';
const fmtDateTime = s => s ? new Date(s.replace(' ', 'T') + 'Z').toLocaleString(undefined, {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : '';

async function api(url, opts = {}) {
  if (opts.body && !(opts.body instanceof FormData) && typeof opts.body !== 'string') {
    opts.body = JSON.stringify(opts.body);
    opts.headers = {'Content-Type': 'application/json', ...(opts.headers || {})};
  }
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error((data && (data.error || (data.errors && data.errors[0] && data.errors[0].error))) || 'Request failed (' + res.status + ')');
  return data;
}

function toast(msg, type = '') {
  let box = $('#toasts');
  if (!box) { box = document.createElement('div'); box.id = 'toasts'; document.body.appendChild(box); }
  const t = document.createElement('div');
  t.className = 'toast ' + type; t.textContent = msg; box.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

// Light/dark theme (stored in the browser)
function setTheme(t) { document.documentElement.dataset.theme = t; localStorage.setItem('dm-theme', t); }
document.addEventListener('DOMContentLoaded', () => {
  const tb = $('#themeBtn');
  if (tb) tb.onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  const mb = $('#menuBtn');
  if (mb) mb.onclick = () => $('#sidebar').classList.toggle('open');
});
