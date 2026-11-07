import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const out=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/refresh-prices-r1/',import.meta.url);
await fs.mkdir(out,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
const sheet=book.worksheets.getItem('LootRules');
if(sheet.getRange('E1').values[0][0]!=='refresh_gold'||sheet.getRange('E4').values[0][0]!=='server')throw new Error('Unexpected original scope cell');
if(process.argv.includes('--before')) {
 console.log((await book.inspect({kind:'table',range:'LootRules!A1:F12',maxChars:2500,tableMaxRows:12,tableMaxCols:6})).ndjson);
 const image=await book.render({sheetName:'LootRules',range:'A1:F12',scale:1.5,format:'png'});
 await fs.writeFile(new URL('before.png',out),new Uint8Array(await image.arrayBuffer()));
} else {
 sheet.getRange('E4').values=[['both']];
 book.recalculate();
 console.log((await book.inspect({kind:'table',range:'LootRules!A1:F12',maxChars:2500,tableMaxRows:12,tableMaxCols:6})).ndjson);
 console.log((await book.inspect({kind:'match',range:'LootRules!A1:P12',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
 const image=await book.render({sheetName:'LootRules',range:'A1:F12',scale:1.5,format:'png'});
 await fs.writeFile(new URL('after.png',out),new Uint8Array(await image.arrayBuffer()));
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',out)));
}
