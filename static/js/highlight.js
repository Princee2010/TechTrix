// Locates a cited passage inside a PDF.js page so it can be highlighted.
// Pure functions (no DOM) so they can be tested with Node.
function _norm(s) { return String(s).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''); }

/**
 * items: PDF.js textContent.items for ONE page; passage: the cited chunk text.
 * Returns a sorted array of item indexes to highlight, or null if the passage can't be located.
 */
function findPassageItems(items, passage) {
  let page = '', owner = [];                       // normalised page text + item index of every character
  items.forEach((it, i) => { const n = _norm(it.str || ''); page += n; for (let k = 0; k < n.length; k++) owner.push(i); });
  const want = _norm(passage);
  if (want.length < 12 || page.length < 12) return null;

  let start = page.indexOf(want), end = start >= 0 ? start + want.length : -1;
  if (start < 0) {
    // PDF.js and PyMuPDF can order text slightly differently: anchor on the beginning and end instead
    for (const size of [60, 40, 25, 15]) {
      if (want.length < size) continue;
      const h = page.indexOf(want.slice(0, size));
      const t = page.indexOf(want.slice(-size), Math.max(h, 0));
      if (h >= 0 && t >= h) { start = h; end = t + size; break; }
      if (h >= 0) { start = h; end = Math.min(page.length, h + want.length); break; }
      if (t >= 0) { end = t + size; start = Math.max(0, end - want.length); break; }
    }
  }
  if (start < 0 || end <= start) return null;
  const set = new Set();
  for (let k = start; k < Math.min(end, owner.length); k++) set.add(owner[k]);
  return [...set].sort((a, b) => a - b);
}
if (typeof module !== 'undefined') module.exports = { findPassageItems };
