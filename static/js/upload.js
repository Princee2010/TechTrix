// My Documents page: upload queue + document library.
let queue = [], docs = [], pollTimer = null;
const dz = $('#dropzone'), fileInput = $('#fileInput');

dz.onclick = () => fileInput.click();
dz.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } };
['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
dz.addEventListener('drop', e => addFiles(e.dataTransfer.files));
fileInput.onchange = () => { addFiles(fileInput.files); fileInput.value = ''; };

function addFiles(list) {
  for (const f of list) {
    if (!/\.pdf$/i.test(f.name)) { toast(f.name + ': only PDF files are allowed', 'err'); continue; }
    if (f.size > 20 * 1024 * 1024) { toast(f.name + ' is larger than 20 MB', 'err'); continue; }
    if (!queue.some(q => q.name === f.name && q.size === f.size)) queue.push(f);
  }
  renderQueue();
}

function renderQueue() {
  $('#queueCard').hidden = !queue.length;
  $('#queue').innerHTML = queue.map((f, i) => `<div class="queue-item"><div class="pdf-ico">PDF</div>
    <div class="grow"><div class="ell">${esc(f.name)}</div><div class="muted small">${fmtSize(f.size)}</div></div>
    <button class="btn sm" onclick="queue.splice(${i},1);renderQueue()">Remove</button></div>`).join('');
}

$('#uploadBtn').onclick = async () => {
  if (!queue.length) return;
  const btn = $('#uploadBtn'); btn.disabled = true; btn.textContent = 'Uploading…';
  const fd = new FormData(); queue.forEach(f => fd.append('files', f));
  try {
    const r = await api('/api/documents/upload', {method: 'POST', body: fd});
    (r.errors || []).forEach(e => toast(e.file + ': ' + e.error, 'err'));
    if (r.uploaded.length) toast(r.uploaded.length + ' document(s) uploaded. Processing started.', 'ok');
    queue = []; renderQueue();
  } catch (e) { toast(e.message, 'err'); }
  btn.disabled = false; btn.textContent = 'Upload documents';
  loadDocs();
};

async function loadDocs() {
  docs = await api('/api/documents');
  renderDocs();
  clearTimeout(pollTimer);
  if (docs.some(d => d.status === 'processing')) pollTimer = setTimeout(loadDocs, 2000);
}

function renderDocs() {
  const term = $('#docSearch').value.toLowerCase();
  const list = docs.filter(d => d.filename.toLowerCase().includes(term));
  $('#docRows').innerHTML = list.length ? list.map(d => `<tr>
    <td><div class="row" style="flex-wrap:nowrap"><div class="pdf-ico">PDF</div><div class="ell" style="max-width:300px" title="${esc(d.filename)}">${esc(d.filename)}</div></div></td>
    <td>${d.pages}</td><td class="hide-sm">${fmtSize(d.size_bytes)}</td>
    <td><span class="badge ${d.status}">${d.status[0].toUpperCase() + d.status.slice(1)}</span>${d.error ? `<div class="errline">${esc(d.error)}</div>` : ''}</td>
    <td><div class="actions">
      <button class="btn sm" onclick="openDetails(${d.id})">Open</button>
      ${d.status === 'processed' ? `<a class="btn sm primary" href="/chat?doc=${d.id}">Ask about this PDF</a>` : ''}
      ${d.status === 'failed' ? `<button class="btn sm primary" onclick="retryDoc(${d.id})">Retry</button>` : ''}
      <a class="btn sm" href="/viewer?document_id=${d.id}&page=1">Preview</a>
      <button class="btn sm danger" onclick="delDoc(${d.id})">Delete</button></div></td></tr>`).join('')
    : `<tr><td colspan="5" class="empty">${docs.length ? 'No documents match your search.' : 'No documents yet. Upload a PDF above to get started.'}</td></tr>`;
}
$('#docSearch').oninput = renderDocs;

async function retryDoc(id) {
  try { await api('/api/documents/' + id + '/reprocess', {method: 'POST'}); toast('Processing again…', 'ok'); loadDocs(); }
  catch (e) { toast(e.message, 'err'); }
}

async function delDoc(id) {
  const d = docs.find(x => x.id === id);
  if (!confirm(`Delete "${d.filename}"?\nIts indexed data will also be removed. This cannot be undone.`)) return;
  try { await api('/api/documents/' + id, {method: 'DELETE'}); toast('Document deleted', 'ok'); loadDocs(); }
  catch (e) { toast(e.message, 'err'); }
}

async function openDetails(id) {
  const d = await api('/api/documents/' + id);
  $('#detailBody').innerHTML = `<h2 class="ell" title="${esc(d.filename)}">${esc(d.filename)}</h2>
    <dl class="kv"><dt>Status</dt><dd><span class="badge ${d.status}">${d.status}</span> ${esc(d.error || '')}</dd>
    <dt>Total pages</dt><dd>${d.pages}</dd><dt>File size</dt><dd>${fmtSize(d.size_bytes)}</dd>
    <dt>Uploaded</dt><dd>${fmtDateTime(d.uploaded_at)}</dd>
    <dt>Text chunks</dt><dd>${d.chunk_count}</dd><dt>Characters extracted</dt><dd>${d.char_count.toLocaleString()}</dd>
    <dt>Pages read with OCR</dt><dd>${d.ocr_pages}</dd>
    <dt>Pages without text</dt><dd>${d.empty_pages}${d.empty_pages ? ' (no readable text found)' : ''}</dd></dl>
    <div class="actions"><a class="btn" href="/viewer?document_id=${d.id}&page=1">Open PDF</a>
    ${d.status === 'processed' ? `<a class="btn primary" href="/chat?doc=${d.id}">Ask questions</a>` : ''}
    <button class="btn danger" onclick="$('#detailDlg').close();delDoc(${d.id})">Delete</button>
    <button class="btn" onclick="$('#detailDlg').close()">Close</button></div>`;
  $('#detailDlg').showModal();
}
loadDocs().then(() => { const o = parseInt(new URLSearchParams(location.search).get('open')); if (o && docs.some(d => d.id === o)) openDetails(o); });
