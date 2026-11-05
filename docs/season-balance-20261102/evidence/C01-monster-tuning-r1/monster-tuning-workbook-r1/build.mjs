import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--before')) {
 console.log((await book.inspect({kind:'table',range:'SeasonEquipmentRules!A1:D7',maxChars:2000,tableMaxRows:7,tableMaxCols:4})).ndjson);
 const image=await book.render({sheetName:'SeasonEquipmentRules',range:'A1:D7',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before.png',output),new Uint8Array(await image.arrayBuffer()));
} else {
 const proposal=JSON.parse(await fs.readFile(new URL('../season-monster-tuning-proposal-r1.json',import.meta.url),'utf8'));
 const values=[['id','rule_id','baseline_id','group_id','member_order','monster_id','base_hp','base_shield','shield_intent_value'],
 ['string','string','string','string','int64','string','int64','int64','int64'],
 ['true','true','true','true','true','true','true','true','true'],
 ['server','server','server','server','server','server','server','server','server'],
 ['原组与成员顺序唯一键','仅新目录启用的校准规则','旧工厂基准固定；旧包不漂移','仅E1/E3/E4/E6精英组','从1开始；E6第二成员不改','必须匹配原组成员身份','难度缩放前生命；大于0','难度缩放前初盾；显式0有效','只覆盖原Shield步骤值；不改伤害或意图顺序']];
 for(const r of proposal.changes)values.push([r.profile_id,'season-monster-tuning-v1','gdd-0.70-fixed-base-v1',r.group_id,r.member_order,r.monster_id,r.candidate_base_hp,r.candidate_base_shield,r.candidate_loop_shield]);
 const sheet=book.worksheets.add('SeasonMonsterTuning');
 const area=sheet.getRange('A1:I9');area.values=values;
 area.format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};area.format.rowHeight=36;area.format.verticalAlignment='center';area.format.wrapText=true;
 const widths=[16,32,32,13,17,22,17,19,27];
 for(let i=0;i<widths.length;i++)sheet.getRangeByIndexes(0,i,9,1).format.columnWidth=widths[i];
 sheet.getRange('A1:I1').format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},rowHeight:40,wrapText:true,horizontalAlignment:'center'};
 sheet.getRange('A2:I4').format.fill='#DCEAF7';sheet.getRange('A5:I5').format={fill:'#F5E5C3',rowHeight:104,wrapText:true};
 sheet.getRange('E6:E9').setNumberFormat('0');sheet.getRange('G6:I9').setNumberFormat('0');sheet.showGridLines=false;sheet.freezePanes.freezeRows(5);
 book.recalculate();
 console.log((await book.inspect({kind:'table',range:'SeasonMonsterTuning!A1:I9',maxChars:3400,tableMaxRows:9,tableMaxCols:9})).ndjson);
 console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:800})).ndjson);
 for(const [name,range] of [['identity','A1:F9'],['values','G1:I9']]){
  const image=await book.render({sheetName:'SeasonMonsterTuning',range,scale:1.25,format:'png'});
  await fs.writeFile(new URL(name+'.png',output),new Uint8Array(await image.arrayBuffer()));
 }
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
 await fs.writeFile(new URL('rows.json',output),JSON.stringify(values,null,2));
}
