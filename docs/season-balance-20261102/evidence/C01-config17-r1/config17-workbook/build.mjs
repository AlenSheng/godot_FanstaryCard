import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const base = path.dirname(fileURLToPath(import.meta.url));
const output = path.join(base, 'outputs', '01a1737c-c1cf-7342-92cd-7cea01eded79');
await fs.mkdir(output, { recursive: true });
const input = path.join(base, 'FantasyCard_Config.source16.original.xlsx');
if (crypto.createHash('sha256').update(await fs.readFile(input)).digest('hex') !== 'f778bb9d27859ef186bc5ab99381b7fc43d9191349ebec7835476fc36fd142e7') throw new Error('Original16 workbook SHA mismatch');
const book = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const cards = book.worksheets.getItem('Cards');
const difficulty = book.worksheets.getItem('SeasonDifficulty');
const before = process.argv.includes('--before');
if (!before) {
  if (cards.getRange('A55').values[0][0] !== 'MAG-10' || cards.getRange('N55').values[0][0] !== 1) throw new Error('Original MAG-10 cell mismatch');
  cards.getRange('N55').values = [[0]];
  difficulty.getRange('N1:N11').copyFrom(difficulty.getRange('M1:M11'), 'all');
  difficulty.getRange('N1:N11').values = [
    ['mage_return_rate_bp'], ['int64'], ['false'], ['both'], ['每自然抽牌间隔返牌额度(万分比)'],
    [500], [500], [500], [500], [500], [500]
  ];
  difficulty.getRange('N1:N11').format.columnWidth = 42;
  book.recalculate();
}
for (const [sheet, range, label] of [['Cards', 'H51:S56', 'cards'], ['SeasonDifficulty', 'J1:N11', 'difficulty']]) {
  const png = await book.render({ sheetName: sheet, range, scale: 1.25, format: 'png' });
  await fs.writeFile(path.join(output, `${before ? 'before' : 'after'}-${label}.png`), new Uint8Array(await png.arrayBuffer()));
}
console.log((await book.inspect({ kind: 'table', range: 'Cards!A55:N55', tableMaxRows: 1, tableMaxCols: 14, maxChars: 1600 })).ndjson);
console.log((await book.inspect({ kind: 'table', range: 'SeasonDifficulty!M1:N11', tableMaxRows: 11, tableMaxCols: 2, maxChars: 2200 })).ndjson);
if (!before) {
  console.log((await book.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 20 }, maxChars: 800 })).ndjson);
  await (await SpreadsheetFile.exportXlsx(book)).save(path.join(output, 'FantasyCard_Config.xlsx'));
  await fs.writeFile(path.join(output, 'edit-scope.original.json'), JSON.stringify({ changes: ['Cards!N55:1->0', 'SeasonDifficulty!N1:N11:new optional published per-difficulty Mage return rate'], effectiveRateBasisPoints: 500, formalPublicationActivated: false }, null, 2));
}
