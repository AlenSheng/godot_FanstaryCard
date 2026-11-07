import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/bot-rewards/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--inspect')) {
 console.log((await book.inspect({kind:'table',range:'SeasonEquipmentRules!A1:E6',maxChars:1100,tableMaxRows:6,tableMaxCols:5})).ndjson);
 const png=await book.render({sheetName:'SeasonEquipmentRules',range:'A1:E6',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before.png',output),new Uint8Array(await png.arrayBuffer()));
} else {
 const tables=[{name:'SeasonBotRewards',values:[
 ['rule_id','gold','fragments','equipment_chance_bp','equipment_quality','equipment_level','maximum_per_human','mortal_pve'],
 ['string','int64','int64','int64','string','int64','int64','bool'],
 Array(8).fill('true'),Array(8).fill('both'),
 ['设计第十一章；首轮保守候选，仍需经济验收','独立低额金币；不乘难度倍率','独立碎片；不乘难度倍率','万分概率：1000为10%；最多一件','品质上限蓝；不继承战斗投影','生成固定+0；禁止作为强化/配方来源','每真人每局只首次击败机器人发奖','脚本PVE允许死亡；不得作为怪物曲线证据'],
 ['season-bot-reward-v1',5,1,1000,'Blue',0,1,true]]}];
 for(const table of tables) {
  const sheet=book.worksheets.add(table.name),end=String.fromCharCode(64+table.values[0].length),rows=table.values.length;
  const area=sheet.getRange('A1:'+end+rows);area.values=table.values;
  area.format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  area.format.columnWidth=27;area.format.rowHeight=25;area.format.verticalAlignment='center';
  sheet.getRange('A1:'+end+'1').format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:38,horizontalAlignment:'center'};
  sheet.getRange('A2:'+end+'4').format.fill='#DCEAF7';
  sheet.getRange('A5:'+end+'5').format={fill:'#F5E5C3',rowHeight:100,wrapText:true};
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
 await fs.writeFile(new URL('bot-reward-rows.json',output),JSON.stringify(tables,null,2));
}

