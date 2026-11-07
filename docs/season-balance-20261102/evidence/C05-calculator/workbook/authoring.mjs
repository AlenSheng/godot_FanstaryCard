import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/equipment/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(`${repo}/config/FantasyCard_Config.xlsx`));
const equipment=book.worksheets.getItem('SeasonEquipment');
if(process.argv.includes('--inspect')) {
  console.log((await book.inspect({kind:'table',range:'SeasonEquipment!A1:L10',maxChars:1800,tableMaxRows:10,tableMaxCols:12})).ndjson);
  const png=await book.render({sheetName:'SeasonEquipment',range:'A1:G10',scale:1.25,format:'png'});
  await fs.writeFile(new URL('before.png',output),new Uint8Array(await png.arrayBuffer()));
}else {
  const version='season-equipment-v1';
  equipment.getRange('M1:M10').values=[['stats_version'],['string'],['true'],['both'],['新季数值版本；旧包不变'],...[0,1,2,3,4].map(()=>[version])];
  equipment.getRange('A11:M11').values=[['red',.32,.18,.04,.01,.12,.006,6,9,15,120,240,version]];
  equipment.getRange('M1:M11').format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  equipment.getRange('M1:M11').format.columnWidth=31;
  equipment.getRange('M1:M11').format.verticalAlignment='center';
  equipment.getRange('M1:M1').format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center'};
  equipment.getRange('M2:M4').format.fill='#DCEAF7';
  equipment.getRange('M5:M5').format={fill:'#F5E5C3',wrapText:true};
  equipment.getRange('A11:L11').format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  equipment.getRange('A11:M11').format.rowHeight=24;
  equipment.getRange('B11:G11').setNumberFormat('0.####');
  equipment.getRange('H11:L11').setNumberFormat('0');
  const values=[
    ['stats_version','resistance_cap','draw_floor_seconds','draw_ceiling_seconds','inferno_bonus','rapid_draw_reduction','rapid_draw_floor_seconds','chain_draw_chance','opening_draw_count','golden_cicada_bonus'],
    ['string','double','double','double','double','double','double','double','int64','double'],
    Array(10).fill('true'),Array(10).fill('both'),
    ['新季属性版本主键','各元素独立抗性上限','普通自然抽牌秒下限','自然抽牌秒上限','红焚元同主元素加成','红疾抽额外间隔减幅','疾抽自然秒下限','普通到点抽牌追加1张概率，不递归','拾遗每次新战斗额外抽牌','红鞋金蝉逃脱加成；总帽仍70%'],
    [version,.6,1.8,6,.15,.04,1.8,.1,1,.15]
  ];
  const sheet=book.worksheets.add('SeasonEquipmentRules');sheet.getRange('A1:J6').values=values;
  sheet.getRange('A1:J6').format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  sheet.getRange('A1:J6').format.rowHeight=25;sheet.getRange('A1:J6').format.columnWidth=26;
  sheet.getRange('A1:J6').format.verticalAlignment='center';
  sheet.getRange('A1:J1').format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},rowHeight:38,wrapText:true,horizontalAlignment:'center'};
  sheet.getRange('A2:J4').format.fill='#DCEAF7';sheet.getRange('A5:J5').format={fill:'#F5E5C3',rowHeight:54,wrapText:true};
  sheet.getRange('A1:A6').format.columnWidth=31;
  for(const col of ['B','E','F','H','J'])sheet.getRange(`${col}6:${col}6`).setNumberFormat('0.00%');
  for(const col of ['C','D','G'])sheet.getRange(`${col}6:${col}6`).setNumberFormat('0.000');
  sheet.getRange('I6:I6').setNumberFormat('0');sheet.showGridLines=false;sheet.freezePanes.freezeRows(5);
  book.recalculate();
  console.log((await book.inspect({kind:'table',range:'SeasonEquipment!A6:M11',maxChars:2000,tableMaxRows:6,tableMaxCols:13})).ndjson);
  console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
  for(const [name,sheetName,range]of [['attributes','SeasonEquipment','A1:G11'],['equipment-version','SeasonEquipment','H1:M11'],['rules-left','SeasonEquipmentRules','A1:E6'],['rules-right','SeasonEquipmentRules','F1:J6']]) {
    const png=await book.render({sheetName,range,scale:1.25,format:'png'});await fs.writeFile(new URL(`${name}.png`,output),new Uint8Array(await png.arrayBuffer()));
  }
  await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
  await fs.writeFile(new URL('rules-rows.json',output),JSON.stringify(values));
}
