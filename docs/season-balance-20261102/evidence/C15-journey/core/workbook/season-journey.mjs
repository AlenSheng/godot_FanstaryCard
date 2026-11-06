import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/season-journey/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--before')) {
 console.log((await book.inspect({kind:'table',range:'SeasonProgression!A1:C10',maxChars:1400,tableMaxRows:9,tableMaxCols:5})).ndjson);
 const png=await book.render({sheetName:'SeasonProgression',range:'A1:C10',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before-progression.png',output),new Uint8Array(await png.arrayBuffer()));
} else {
 const tables=[{"name": "SeasonJourneyRules", "values": [["rule_id", "enabled", "outer_xp", "middle_xp", "elite_xp", "boss_xp", "extraction_xp", "catch_up_multiplier", "reference_days", "reference_xp_42", "main_reward_levels", "contract_assignment", "catch_up_sources", "time_zone"], ["string", "bool", "int64", "int64", "int64", "int64", "int64", "int64", "int64", "int64", "int64", "string", "string", "string"], ["true", "true", "true", "true", "true", "true", "true", "true", "true", "true", "true", "true", "true", "true"], ["both", "both", "both", "both", "both", "both", "both", "both", "both", "both", "both", "both", "both", "both"], ["第10章季程经验独立于资源钱包", "仅完整策略启用，不追补无来源历史事件", "实际首次清理外格；不因死亡补造", "实际首次清理中格", "具名精英组清理，不按整个核心层叠加", "首领清理，不同时发精英/普通格经验", "成功撤离一次，不把死亡当撤离", "最多2倍；达到参考经验立即停止", "候选首季参考曲线：前21自然日线性", "42天等于前20级6850；短季按实际20级门槛", "21至30级不放必需战力或难度入场权", "候选：同类先填最早开放未满契约，一事件不填多周", "追赶仅实际清格经验，不翻倍金钻/魂/掉落/契约经验", "自然日00:00，与商店04点分离"], ["season-journey-v1", true, 6, 10, 25, 80, 70, 2, 21, 6850, 20, "oldest-open-incomplete", "cleared_cells", "Asia/Shanghai"]]}, {"name": "SeasonWeeklyContracts", "values": [["contract_id", "completion_kind", "target", "xp_reward"], ["string", "string", "int64", "int64"], ["true", "true", "true", "true"], ["both", "both", "both", "both"], ["账号/原季/原周/契约唯一", "原服务器完成事件；不是登录或死亡次数", "候选运营目标，原文未规定3/5/1", "各300，仅一次；不受追赶倍率影响"], ["weekly-extraction", "Extracted", 3, 300], ["weekly-elite", "Elite", 5, 300], ["weekly-boss", "Boss", 1, 300]]}];
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
  const ranges=table.name==='SeasonJourneyRules'?['A1:G6','H1:N6']:['A1:D8'];
  for(let i=0;i<ranges.length;i++) {
   const png=await book.render({sheetName:table.name,range:ranges[i],scale:1.25,format:'png'});
   await fs.writeFile(new URL(table.name+'-'+(i+1)+'.png',output),new Uint8Array(await png.arrayBuffer()));
  }
 }
 console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:800})).ndjson);
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
 await fs.writeFile(new URL('journey-rows.json',output),JSON.stringify(tables,null,2));
}
