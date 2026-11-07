import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/crafting/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--inspect')) {
 console.log((await book.inspect({kind:'table',range:'SeasonEquipmentRules!A1:E6',maxChars:1100,tableMaxRows:6,tableMaxCols:5})).ndjson);
 const png=await book.render({sheetName:'SeasonEquipmentRules',range:'A1:E6',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before.png',output),new Uint8Array(await png.arrayBuffer()));
} else {
 const tables=[
 {name:'SeasonCrafting',values:[
 ['quality_id','minimum_difficulty','mark_kind','mark_cost','reforge_fragment_cost','wish_attempts'],
 ['string','int64','string','int64','int64','int64'],
 Array(6).fill('true'),Array(6).fill('both'),
 ['品质；红装排除','打造最低开放且本人解锁难度','消耗类型；高阶可1比1抵扣低阶','每次定向打造费用','一件真实本体按已学配方重铸碎片费','同组最多次数命中效果，成功清零'],
 ['Purple',1,'Blueprint',4,1,3],['Orange',2,'OrangeBlueprint',14,2,3]]},
 {name:'SeasonMarkRules',values:[
 ['difficulty_id','mark_kind','elite_marks','boss_marks','match_cap'],
 ['string','string','int64','int64','int64'],
 Array(5).fill('true'),Array(5).fill('both'),
 ['原始对局难度','仅本人首次清格；撤离入账','每个首次精英格','每个首次Boss格','每名玩家每局上限；死/退/PVP/Bot无章'],
 ['D0','None',0,0,0],['D1','Blueprint',1,2,4],
 ...[2,3,4,5].map(n=>['D'+n,'OrangeBlueprint',1,2,4])]}
 ];
 for(const table of tables) {
  const sheet=book.worksheets.add(table.name),end=String.fromCharCode(64+table.values[0].length),rows=table.values.length;
  const area=sheet.getRange('A1:'+end+rows);area.values=table.values;
  area.format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  area.format.columnWidth=27;area.format.rowHeight=25;area.format.verticalAlignment='center';
  sheet.getRange('A1:'+end+'1').format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:38,horizontalAlignment:'center'};
  sheet.getRange('A2:'+end+'4').format.fill='#DCEAF7';
  sheet.getRange('A5:'+end+'5').format={fill:'#F5E5C3',rowHeight:62,wrapText:true};
  for(let col=0;col<table.values[0].length;col++)if(table.values[1][col]==='int64')sheet.getRangeByIndexes(5,col,rows-5,1).setNumberFormat('0');
  sheet.showGridLines=false;sheet.freezePanes.freezeRows(5);
 }
 book.recalculate();
 for(const table of tables) {
  const end=String.fromCharCode(64+table.values[0].length);
  console.log((await book.inspect({kind:'table',range:table.name+'!A6:'+end+table.values.length,maxChars:1200,tableMaxRows:6,tableMaxCols:6})).ndjson);
  const png=await book.render({sheetName:table.name,range:'A1:'+end+table.values.length,scale:1.25,format:'png'});
  await fs.writeFile(new URL(table.name+'.png',output),new Uint8Array(await png.arrayBuffer()));
 }
 console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:800})).ndjson);
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
 await fs.writeFile(new URL('crafting-rows.json',output),JSON.stringify(tables,null,2));
}

