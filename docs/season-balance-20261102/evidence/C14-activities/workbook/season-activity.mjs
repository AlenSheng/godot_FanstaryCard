import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/limited-activities/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--before')) {
 console.log((await book.inspect({kind:'table',range:'SeasonActivityExchange!A1:E9',maxChars:1400,tableMaxRows:9,tableMaxCols:5})).ndjson);
 const png=await book.render({sheetName:'SeasonActivityExchange',range:'A1:E9',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before-exchanges.png',output),new Uint8Array(await png.arrayBuffer()));
} else {
 const tables=[{name:'SeasonActivityRules',values:[
  ['rule_id','enabled','completion_kind','tokens_per_completion','token_cap','time_zone','start_hour','late_exchange','direct_gold','direct_diamonds','direct_equipment','direct_red_materials'],
  ['string','bool','string','int64','int64','string','int64','bool','int64','int64','int64','int64'],
  Array(12).fill('true'),Array(12).fill('server'),
  ['设计第17章有限活动预算','仅本包完整活动策略启用','候选任务：服务器确认成功撤离；原文未指定获章任务','候选每次4枚，三次获满；不是原文强制数字','每账号/活动/来源季总额12；绑定且不能跨活动','活动自然日按上海；保存UTC','自然日00:00；不同于商店04:00','只补兑原期，绝不挪入新期预算','压力分支默认0，当前规则禁止直接投放','默认0；不增加永久钻石','默认0；不直接发紫橙实物','默认0；不能绕红周额度造材料'],
  ['season-limited-activity-v1',true,'Extracted',4,12,'Asia/Shanghai',0,true,0,0,0,0]
 ]},{name:'SeasonActivityCalendar',values:[
  ['event_id','first_day_42','days'],['string','int64','int64'],Array(3).fill('true'),Array(3).fill('both'),
  ['同来源季两期独立账号预算','候选运营日期，42天为第12/33日；30/60天按日序比例缩放','每期连续三个自然日，左闭右开'],
  ['activity-one',12,3],['activity-two',33,3]
 ]}];
 for(const table of tables) {
  const sheet=book.worksheets.add(table.name),end=String.fromCharCode(64+table.values[0].length),rows=table.values.length;
  const area=sheet.getRange('A1:'+end+rows);area.values=table.values;
  area.format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  area.format.columnWidth=27;area.format.rowHeight=25;area.format.verticalAlignment='center';
  sheet.getRange('A1:'+end+'1').format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:38,horizontalAlignment:'center'};
  sheet.getRange('A2:'+end+'4').format.fill='#DCEAF7';
  sheet.getRange('A5:'+end+'5').format={fill:'#F5E5C3',rowHeight:116,wrapText:true};
  for(let col=0;col<table.values[0].length;col++)if(table.values[1][col]==='int64')sheet.getRangeByIndexes(5,col,rows-5,1).setNumberFormat('0');
  sheet.showGridLines=false;sheet.freezePanes.freezeRows(5);
 }
 book.recalculate();
 for(const table of tables) {
  const ranges=table.name==='SeasonActivityRules'?['A1:F6','G1:L6']:['A1:C7'];
  for(let i=0;i<ranges.length;i++) {
   const png=await book.render({sheetName:table.name,range:ranges[i],scale:1.25,format:'png'});
   await fs.writeFile(new URL(table.name+'-'+(i+1)+'.png',output),new Uint8Array(await png.arrayBuffer()));
  }
 }
 console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:800})).ndjson);
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
 await fs.writeFile(new URL('activity-rows.json',output),JSON.stringify(tables,null,2));
}
