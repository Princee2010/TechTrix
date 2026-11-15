// Ask Your Documents: document selection + RAG chat.
let docs = [], selected = new Set(), convId = null, busy = false;
const box = $('#messages'), input = $('#question');

async function init() {
  docs = await api('/api/documents');
  const params = new URLSearchParams(location.search);
  const pre = parseInt(params.get('doc'));
  if (pre) selected.add(pre);
  renderDocs();
  if (params.get('c')) await loadConversation(params.get('c'));
  else showHello();
}

function renderDocs() {
  const term = $('#docFilter').value.toLowerCase();
  const list = docs.filter(d => d.filename.toLowerCase().includes(term));
  $('#docList').innerHTML = list.length ? list.map(d => {
    const ok = d.status === 'processed';
    return `<label class="docopt" style="${ok ? '' : 'opacity:.55;cursor:not-allowed'}">
      <input type="checkbox" value="${d.id}" ${selected.has(d.id) ? 'checked' : ''} ${ok ? '' : 'disabled'}>
      <div class="grow"><div class="ell" title="${esc(d.filename)}">${esc(d.filename)}</div>
      <div class="muted small">${d.pages} pages${ok ? '' : ' · ' + d.status}</div></div></label>`;
  }).join('') : '<div class="empty small">No documents found. <a href="/documents">Upload a PDF</a></div>';
  $$('#docList input').forEach(cb => cb.onchange = () => {
    cb.checked ? selected.add(+cb.value) : selected.delete(+cb.value); updateCount();
  });
  updateCount();
}
function updateCount() {
  const valid = [...selected].filter(id => docs.some(d => d.id === id && d.status === 'processed'));
  selected = new Set(valid);
  $('#selCount').textContent = selected.size + ' selected';
  $('#selAll').checked = docs.filter(d => d.status === 'processed').length > 0 && selected.size === docs.filter(d => d.status === 'processed').length;
}
$('#docFilter').oninput = renderDocs;
$('#selAll').onchange = e => {
  selected = new Set(e.target.checked ? docs.filter(d => d.status === 'processed').map(d => d.id) : []);
  renderDocs();
};

function showHello() {
  box.innerHTML = `<div class="hello"><h2>Ask your documents</h2><p>Select one or more PDFs on the left, then ask a question.
  Answers come only from your documents and link back to the exact page.</p></div>`;
}

function fmt(text) {   // minimal, safe formatting: escape, **bold**, line breaks
  return esc(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>');
}

function addUser(text) {
  if ($('.hello', box)) box.innerHTML = '';
  const d = document.createElement('div'); d.className = 'msg user'; d.textContent = text; box.appendChild(d);
  box.scrollTop = box.scrollHeight;
}

function addAI(m) {
  const noMatch = m.no_match;
  const d = document.createElement('div'); d.className = 'msg ai' + (noMatch ? ' nomatch' : '');
  const src = (m.sources || []).map(s => `<div class="src"><div class="t">[${s.n}] ${esc(s.filename)} · Page ${s.page}</div>
    <div class="snip">${esc(s.snippet)}…</div>
    <a href="/viewer?document_id=${s.document_id}&page=${s.page}${s.chunk_id ? '&chunk=' + s.chunk_id : ''}" target="_blank" rel="noopener">View source</a></div>`).join('');
  d.innerHTML = `<div class="who">DocuMind AI</div>
    ${m.warning ? `<div class="notice">⚠ ${esc(m.warning)}</div>` : ''}
    ${noMatch ? '<b>No relevant information found</b><br><br>' : ''}<div class="ans">${fmt(m.answer || m.content)}</div>
    ${src ? `<div class="sources"><b>Sources used</b>${src}</div>` : ''}
    <div class="msg-actions">
      <button class="btn sm" data-a="copy">Copy answer</button>
      ${noMatch ? '' : `<button class="btn sm" data-a="up">Helpful</button><button class="btn sm" data-a="down">Not helpful</button>
      <button class="btn sm" data-a="dl">Download</button>`}</div>`;
  const text = m.answer || m.content;
  d.querySelector('[data-a=copy]').onclick = () => navigator.clipboard.writeText(text).then(() => toast('Answer copied', 'ok'));
  const up = d.querySelector('[data-a=up]'), down = d.querySelector('[data-a=down]'), dl = d.querySelector('[data-a=dl]');
  const fb = async (v, el, other) => {
    try { await api(`/api/messages/${m.message_id || m.id}/feedback`, {method: 'POST', body: {value: v}}); el.classList.add('on'); other.classList.remove('on'); toast('Thanks for the feedback', 'ok'); }
    catch (e) { toast(e.message, 'err'); }
  };
  if (up) { up.onclick = () => fb(1, up, down); down.onclick = () => fb(-1, down, up); if (m.feedback === 1) up.classList.add('on'); if (m.feedback === -1) down.classList.add('on'); }
  if (dl) dl.onclick = () => {
    const refs = (m.sources || []).map(s => `[${s.n}] ${s.filename}, page ${s.page}`).join('\n');
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text + '\n\nSources:\n' + refs], {type: 'text/plain'}));
    a.download = 'documind-answer.txt'; a.click();
  };
  box.appendChild(d); box.scrollTop = box.scrollHeight;
}

async function send() {
  const q = input.value.trim();
  if (!q || busy) return;
  if (!selected.size) { toast('Select at least one processed document first', 'err'); return; }
  busy = true; $('#sendBtn').disabled = true; input.value = '';
  addUser(q);
  const typing = document.createElement('div'); typing.className = 'msg ai';
  typing.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>'; box.appendChild(typing);
  box.scrollTop = box.scrollHeight;
  try {
    const r = await api('/api/chat', {method: 'POST', body: {question: q, document_ids: [...selected], conversation_id: convId}});
    convId = r.conversation_id; typing.remove(); addAI(r);
  } catch (e) {
    typing.remove(); toast(e.message, 'err'); input.value = q;   // keep the question so it can be re-sent
    const last = box.lastElementChild; if (last && last.classList.contains('user')) last.remove();
  }
  busy = false; $('#sendBtn').disabled = false; input.style.height = 'auto'; input.focus();
}
$('#sendBtn').onclick = send;
input.oninput = () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 140) + 'px'; };
input.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };

$('#newChat').onclick = () => { convId = null; history.replaceState(null, '', '/chat'); showHello(); };
$('#clearChat').onclick = async () => {
  if (!confirm('Clear this conversation? It will also be removed from Chat History.')) return;
  if (convId) { try { await api('/api/conversations/' + convId, {method: 'DELETE'}); } catch (e) {} }
  convId = null; history.replaceState(null, '', '/chat'); showHello();
};

async function loadConversation(id) {
  try {
    const r = await api('/api/conversations/' + id);
    convId = r.conversation.id; box.innerHTML = '';
    const last = [...r.messages].reverse().find(m => m.doc_ids && m.doc_ids.length);
    if (last) { selected = new Set(last.doc_ids); renderDocs(); }
    r.messages.forEach(m => m.role === 'user' ? addUser(m.content) : addAI({...m, no_match: !!m.no_match}));
  } catch (e) { toast('Could not open that conversation', 'err'); showHello(); }
}
init();
