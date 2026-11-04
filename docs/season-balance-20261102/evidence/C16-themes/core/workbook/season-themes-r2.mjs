import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/season-themes-r2/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--before')) {
 console.log((await book.inspect({kind:'table',range:'SeasonLootPreference!A1:E6',maxChars:1400,tableMaxRows:9,tableMaxCols:5})).ndjson);
 const png=await book.render({sheetName:'SeasonLootPreference',range:'A1:E6',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before-loot-theme.png',output),new Uint8Array(await png.arrayBuffer()));
} else {
 const tables=[{"name": "SeasonThemeRules", "values": [["rule_id", "enabled", "selected_theme", "preferred_weight", "other_weight", "group_weight_mode", "global_damage_bp", "layout", "spawn_singles"], ["string", "bool", "string", "int64", "int64", "string", "int64", "string", "bool"], ["true", "true", "true", "true", "true", "true", "true", "true", "true"], ["both", "both", "both", "both", "both", "both", "both", "both", "both"], ["第9章元素主题策略", "新完整组启用；旧包无组保持原图", "首季复用火；切换须同版更新寻宝默认元素", "元素偏好输入40%，按完整组再归一", "其它元素各15%，不是每只怪独立抽样", "原组基准×成员权重均值，再归一；实测单怪占比另记", "固定10000，不加额外全局伤害倍率", "复用既有6×6结构，不发明五张大图尺寸或人数", "出生点只取原单怪组，宝箱另走原独立流"], ["season-theme-v1", true, "Fire", 4000, 1500, "member-mean-normalized", 10000, "chaos-6x6", true]]}, {"name": "SeasonThemes", "values": [["theme_id", "element", "name_key", "strategy_id", "phase1_primary", "phase1_secondary", "phase2_primary", "phase2_secondary", "regeneration_budget_bp", "regeneration_step_bp", "phase1_shield", "phase2_shield", "setup_kind", "setup_value"], ["string", "string", "string", "string", "string", "string", "string", "string", "int64", "int64", "int64", "int64", "string", "int64"], ["true", "true", "true", "true", "true", "true", "true", "true", "true", "true", "true", "true", "true", "true"], ["both", "both", "both", "both", "both", "both", "both", "both", "both", "both", "both", "both", "both", "both"], ["原主题身份", "主元素不改变永久上限", "沿用基础卷五图命名；显示本地化键", "具名机制，可用真实意图测试", "一阶段主攻/主抗", "一阶段副元素", "二阶段主攻/主抗", "二阶段副元素", "木一场至多回复基础最大HP的5%；难度后原最大HP为基准", "木每步最多2%，可打断；跨阶段/重启共用剩余额度", "沿原Shield槽；土12，其余10，木改再生", "沿原Shield槽；土10，其余8，木改再生", "火/木/土/水蓄力，金可预读强化；前摇不缩", "强化2；蓄力0。无新大额全局伤害倍率"], ["Fire", "Fire", "season_theme_fire", "ember-windows", "Fire", "Wood", "Metal", "Earth", 0, 0, 10, 8, "Charge", 0], ["Wood", "Wood", "season_theme_wood", "thorn-regrowth", "Wood", "Water", "Water", "Wood", 500, 200, 0, 0, "Charge", 0], ["Earth", "Earth", "season_theme_earth", "stone-cycle", "Earth", "Metal", "Metal", "Earth", 0, 0, 12, 10, "Charge", 0], ["Metal", "Metal", "season_theme_metal", "metal-telegraph", "Metal", "Fire", "Fire", "Metal", 0, 0, 10, 8, "Empower", 2], ["Water", "Water", "season_theme_water", "tide-shift", "Water", "Metal", "Wood", "Water", 0, 0, 10, 8, "Charge", 0]]}, {"name": "SeasonThemeGroups", "values": [["group_id", "tier", "member_elements", "spawn_allowed", "base_weight"], ["string", "string", "string", "bool", "int64"], ["true", "true", "true", "true", "true"], ["both", "both", "both", "both", "both"], ["引用既有19组，不拆双怪", "outer/middle/elite沿原位置分类", "成员顺序与原PVE工厂一致，以|分隔", "仅O1至O5原单怪组可出生", "原组基准100，乘成员偏好均值后归一"], ["O1", "outer", "Fire", true, 100], ["O2", "outer", "Wood", true, 100], ["O3", "outer", "Water", true, 100], ["O4", "outer", "Earth", true, 100], ["O5", "outer", "Metal", true, 100], ["O6", "outer", "Fire|Fire", false, 100], ["O7", "outer", "Metal|Wood", false, 100], ["O8", "outer", "Water|Earth", false, 100], ["M1", "middle", "Fire|Fire", false, 100], ["M2", "middle", "Water|Earth", false, 100], ["M3", "middle", "Metal|Wood", false, 100], ["M4", "middle", "Water|Water", false, 100], ["M5", "middle", "Fire|Earth", false, 100], ["E1", "elite", "Metal", false, 100], ["E2", "elite", "Fire", false, 100], ["E3", "elite", "Water", false, 100], ["E4", "elite", "Earth", false, 100], ["E5", "elite", "Wood", false, 100], ["E6", "elite", "Metal|Fire", false, 100]]}];
 for(const table of tables) {
  const sheet=book.worksheets.add(table.name),end=String.fromCharCode(64+table.values[0].length),rows=table.values.length;
  const area=sheet.getRange('A1:'+end+rows);area.values=table.values;
  area.format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  area.format.columnWidth=27;area.format.rowHeight=25;area.format.verticalAlignment='center';
  sheet.getRange('A1:'+end+'1').format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:38,horizontalAlignment:'center'};
  sheet.getRange('A2:'+end+'4').format.fill='#DCEAF7';
  sheet.getRange('A5:'+end+'5').format={fill:'#F5E5C3',rowHeight:116,wrapText:true};
  for(let col=0;col<table.values[0].length;col++)if(table.values[1][col]==='int64')sheet.getRangeByIndexes(5,col,rows-5,1).setNumberFormat('0');
  if(table.name==='SeasonThemes')sheet.getRange('C6:H10').format.horizontalAlignment='center';
  for(let col=0;col<table.values[0].length;col++)if(table.values[1][col]==='string')sheet.getRangeByIndexes(5,col,rows-5,1).format.horizontalAlignment='center';
  sheet.showGridLines=false;sheet.freezePanes.freezeRows(5);
 }
 book.recalculate();
 for(const table of tables) {
  const ranges=table.name==='SeasonThemeRules'?['A1:E6','F1:I6']:table.name==='SeasonThemes'?['A1:G10','H1:N10']:['A1:E14','A15:E24'];
  for(let i=0;i<ranges.length;i++) {
   const png=await book.render({sheetName:table.name,range:ranges[i],scale:1.25,format:'png'});
   await fs.writeFile(new URL(table.name+'-'+(i+1)+'.png',output),new Uint8Array(await png.arrayBuffer()));
  }
 }
 console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:800})).ndjson);
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
 await fs.writeFile(new URL('theme-rows.json',output),JSON.stringify(tables,null,2));
}
