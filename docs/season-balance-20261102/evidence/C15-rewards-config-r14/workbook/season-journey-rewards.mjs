import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/season-journey-rewards-r1/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--before')) {
 console.log((await book.inspect({kind:'table',range:'SeasonWeeklyContracts!A1:D8',maxChars:1800,tableMaxRows:8,tableMaxCols:4})).ndjson);
 const png=await book.render({sheetName:'SeasonWeeklyContracts',range:'A1:D8',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before-contracts.png',output),new Uint8Array(await png.arrayBuffer()));
} else {
 const approved=JSON.parse(await fs.readFile(repo+'/docs/season-balance-20261102/C15-rewards-candidate.json','utf8'));
 if(!approved.user_approval.main_rewards_accepted||approved.main_rewards.length!==20||approved.post20.length!==10)throw new Error('Approved complete reward source required');
 const rewards=[['reward_id','level','kind','amount','ownership','requires_class_choice','cosmetic_id'],
  ['string','int64','string','int64','string','bool','string'],['true','true','true','true','true','true','false'],
  ['both','both','both','both','both','both','both'],
  ['2026-11-05用户确认；账号/原季/等级唯一','领取等级1至30；沿原季经验门槛','前20级物品；后10级仅外观','卡包1包实际3张永久副本','碎片仅原季；魂/卡/外观永久绑定','仅职业魂三职业选一；其他奖励不得选择','仅外观等级引用；物品奖励留空']];
 for(const row of [...approved.main_rewards,...approved.post20])rewards.push([
  `journey-level-${String(row.level).padStart(2,'0')}`,row.level,row.kind,row.quantity,
  row.kind==='EquipmentFragments'?'SeasonalBound':'PermanentBound',row.requires_class_choice??false,row.cosmetic_id??null]);
 const cosmetics=[['cosmetic_id','kind','name_key','description_key'],['string','string','string','string'],
  ['true','true','true','true'],['both','both','both','both'],
  ['具体ID沿用户授权细化；永久绑定且不转货币','头像框/卡背/称号可选；收藏印记展示来源','11语言名称；图片不烘焙文字','11语言描述；外观不增加战斗属性']];
 for(const row of approved.post20)cosmetics.push([row.cosmetic_id,row.display_kind,
  `journey_cosmetic_${row.cosmetic_id.replaceAll('-','_')}_name`,`journey_cosmetic_${row.cosmetic_id.replaceAll('-','_')}_description`]);
 const tables=[{name:'SeasonJourneyRewards',values:rewards,widths:[31,10,26,10,24,23,31]},
  {name:'SeasonCosmetics',values:cosmetics,widths:[32,21,61,70]}];
 for(const table of tables) {
  const sheet=book.worksheets.add(table.name),end=String.fromCharCode(64+table.values[0].length),rows=table.values.length;
  const area=sheet.getRange(`A1:${end}${rows}`);area.values=table.values;
  area.format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  area.format.rowHeight=36;area.format.verticalAlignment='center';area.format.wrapText=true;
  for(let col=0;col<table.widths.length;col++)sheet.getRangeByIndexes(0,col,rows,1).format.columnWidth=table.widths[col];
  sheet.getRange(`A1:${end}1`).format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:40,horizontalAlignment:'center'};
  sheet.getRange(`A2:${end}4`).format.fill='#DCEAF7';
  sheet.getRange(`A5:${end}5`).format={fill:'#F5E5C3',rowHeight:104,wrapText:true};
  for(let col=0;col<table.values[0].length;col++)if(table.values[1][col]==='int64')sheet.getRangeByIndexes(5,col,rows-5,1).setNumberFormat('0');
  sheet.showGridLines=false;sheet.freezePanes.freezeRows(5);
 }
 book.recalculate();
 for(const [sheetName,ranges] of [['SeasonJourneyRewards',['A1:D12','E1:G12','A26:G35']],['SeasonCosmetics',['A1:B15','C1:D15']]]) {
  for(let i=0;i<ranges.length;i++) {
   const png=await book.render({sheetName,range:ranges[i],scale:1.25,format:'png'});
   await fs.writeFile(new URL(`${sheetName}-${i+1}.png`,output),new Uint8Array(await png.arrayBuffer()));
  }
  console.log((await book.inspect({kind:'table',range:sheetName==='SeasonJourneyRewards'?'SeasonJourneyRewards!A6:G10':'SeasonCosmetics!A6:D15',maxChars:2400,tableMaxRows:10,tableMaxCols:7})).ndjson);
 }
 console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:800})).ndjson);
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
 await fs.writeFile(new URL('journey-reward-rows.json',output),JSON.stringify(tables,null,2));
}
