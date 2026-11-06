import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/standard-shop/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(repo+'/config/FantasyCard_Config.xlsx'));
if(process.argv.includes('--before')) {
 console.log((await book.inspect({kind:'table',range:'ShopCardPrices!A1:D9',maxChars:1600,tableMaxRows:9,tableMaxCols:4})).ndjson);
 const png=await book.render({sheetName:'ShopCardPrices',range:'A1:D9',scale:1.25,format:'png'});
 await fs.writeFile(new URL('before-card-prices.png',output),new Uint8Array(await png.arrayBuffer()));
} else {
 const tables=[{name:'SeasonShopRules',values:[
  ['rule_id','enabled','time_zone','reset_hour','pack_cards','white_weight','green_weight','blue_weight','purple_weight','class_soul_daily_limit','paid_bag_cap'],
  ['string','bool','string','int64','int64','int64','int64','int64','int64','int64','int64'],
  Array(11).fill('true'),Array(11).fill('both'),
  ['GDD 0.3 / 6.2；设计第17章普通金币商店','只对已发布的新季配置启用；保留旧路径','账号业务日时区','业务日从本地04:00开始','每包实际副本数；不保证新解锁','质量权重；全图鉴仍可开包','质量权重；允许已持有与同包重复','质量权重；不含橙','质量权重；不含职业紫或橙','牧/法/盾三选一共用日额','高级和顶级未使用包合计上限'],
  ['season-gold-shop-v1',true,'Asia/Shanghai',4,3,50,30,15,5,1,3]
 ]},{name:'SeasonShopProducts',values:[
  ['product_id','kind','amount','price_gold','daily_limit','quota_group','hero_class'],
  ['string','string','int64','int64','int64','string','string'],
  ['true','true','true','true','true','true','false'],Array(7).fill('both'),
  ['GDD 6.2固定货架；单卡沿用ShopCardPrices','服务端按既有资产类型发放','每份数量；Cards为真实卡副本','每份金币；本季钱包扣费','0为无日限；不绕过仓储上限','同账号同业务日跨季/配置不重置','仅ClassSoul填写目标职业'],
  ['card_pack','Cards',3,250,5,'card_pack',''],
  ['warrior_soul','WarriorSoul',20,180,3,'warrior_soul',''],
  ['equipment_fragments','EquipmentFragments',20,120,3,'equipment_fragments',''],
  ['priest_soul','ClassSoul',12,400,1,'class_soul','Priest'],
  ['mage_soul','ClassSoul',12,400,1,'class_soul','Mage'],
  ['guardian_soul','ClassSoul',12,400,1,'class_soul','Guardian'],
  ['health_potion','HealthPotion',1,100,4,'health_potion',''],
  ['advanced_bag','AdvancedBag',1,800,0,'advanced_bag',''],
  ['top_bag','TopBag',1,2200,0,'top_bag','']
 ]}];
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
  console.log((await book.inspect({kind:'table',range:table.name+'!A6:'+end+table.values.length,maxChars:2000,tableMaxRows:9,tableMaxCols:11})).ndjson);
  const ranges=table.name==='SeasonShopRules'?['A1:F6','G1:K6']:['A1:G14'];
  for(let i=0;i<ranges.length;i++) {
   const png=await book.render({sheetName:table.name,range:ranges[i],scale:1.25,format:'png'});
   await fs.writeFile(new URL(table.name+'-'+(i+1)+'.png',output),new Uint8Array(await png.arrayBuffer()));
  }
 }
 console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},maxChars:800})).ndjson);
 await(await SpreadsheetFile.exportXlsx(book)).save(fileURLToPath(new URL('FantasyCard_Config.xlsx',output)));
 await fs.writeFile(new URL('shop-rows.json',output),JSON.stringify(tables,null,2));
}
