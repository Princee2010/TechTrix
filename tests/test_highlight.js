// Optional: checks that the cited passage can be located in PDF.js's own text output.
//   npm install pdfjs-dist@3.11.174      then      node tests/test_highlight.js <file.pdf> <page> "<passage from that page>"
const { findPassageItems } = require('../static/js/highlight.js');
const pdfjs = require('pdfjs-dist/legacy/build/pdf.js');
(async () => {
  const [file, page, passage] = process.argv.slice(2);
  const doc = await pdfjs.getDocument({ data: new Uint8Array(require('fs').readFileSync(file)) }).promise;
  const tc = await (await doc.getPage(+page)).getTextContent();
  const idx = findPassageItems(tc.items, passage);
  console.log(idx ? 'HIGHLIGHT items: ' + idx.length + ' -> "' + idx.map(i => tc.items[i].str).join(' ').slice(0, 120) + '"' : 'NOT LOCATED');
  process.exit(idx ? 0 : 1);
})();
