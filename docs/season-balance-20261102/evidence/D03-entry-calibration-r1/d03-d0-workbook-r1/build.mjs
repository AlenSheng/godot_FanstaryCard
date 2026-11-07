import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--before')){
 console.log((await book.inspect({kind:'table',range:'SeasonDifficulty!A1:F11',maxChars:2600,tableMaxRows:11,tableMaxCols:6})).ndjson);
 const preview=await book.render({sheetName:'SeasonDifficulty',range:'A1:F11',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before.png',output),new Uint8Array(await preview.arrayBuffer()));
}else{
 const sheet=book.worksheets.getItem('SeasonDifficulty');
 sheet.getRange('C6:D6').values=[[0.5,0.5]];
 book.recalculate();
 console.log((await book.inspect({kind:'table',range:'SeasonDifficulty!A1:F11',maxChars:2600,tableMaxRows:11,tableMaxCols:6})).ndjson);
 const preview=await book.render({sheetName:'SeasonDifficulty',range:'A1:F11',scale:1.25,format:'png'});
 await fs.writeFile(new URL('after.png',output),new Uint8Array(await preview.arrayBuffer()));
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
}
