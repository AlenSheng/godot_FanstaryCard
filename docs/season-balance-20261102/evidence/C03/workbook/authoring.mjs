import fs from 'node:fs/promises';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';
const repo='C:/Users/SHENGJIAHAO/.codex/worktrees/sync-release-targets/godot_FanstaryCard';
const output=new URL('outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/loans/',import.meta.url);
await fs.mkdir(output,{recursive:true});
const book=await SpreadsheetFile.importXlsx(await FileBlob.load(`${repo}/config/FantasyCard_Config.xlsx`));
if(process.argv.includes('--inspect')) {
  const before=await book.render({sheetName:'SeasonDifficulty',range:'A1:F8',scale:1.25,format:'png'});
  await fs.writeFile(new URL('before.png',output),new Uint8Array(await before.arrayBuffer()));
  console.log((await book.inspect({kind:'table',range:'SeasonDifficulty!A1:F7',maxChars:1000,tableMaxRows:7,tableMaxCols:6})).ndjson);
} else {
  const values=[['id','template_id','hero_class','slot_index','card_id'],['string','string','string','int64','string'],
    ['true','true','true','true','true'],['both','both','both','both','both'],
    ['稳定行主键','本季固定借用模板','职业','0至19，按序编组','正式卡牌ID；不生成永久副本']];
  for(const [hero,prefix]of[['Priest','PRI'],['Mage','MAG'],['Guardian','GUA']]) {
    const template=`loan-${hero.toLowerCase()}`;
    for(let slot=0;slot<20;slot++) values.push([`${template}:${slot}`,template,hero,slot,slot<13?`C${String(slot+1).padStart(2,'0')}`:`${prefix}-${String(slot-12).padStart(2,'0')}`]);
  }
  const sheet=book.worksheets.add('SeasonBorrowedDecks');
  sheet.getRange('A1:E65').values=values;
  sheet.getRange('A1:E65').format.font={name:'Microsoft YaHei',size:10,color:'#17324D'};
  sheet.getRange('A1:E65').format.verticalAlignment='center';
  sheet.getRange('A1:E65').format.rowHeight=24;
  sheet.getRange('A1:E1').format={fill:'#1F4E78',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},rowHeight:34,horizontalAlignment:'center'};
  sheet.getRange('A2:E4').format.fill='#DCEAF7';
  sheet.getRange('A5:E5').format={fill:'#F5E5C3',rowHeight:38,wrapText:true};
  for(const [range,width]of[['A1:A65',29],['B1:B65',26],['C1:C65',20],['D1:D65',22],['E1:E65',35]])sheet.getRange(range).format.columnWidth=width;
  sheet.getRange('D6:D65').setNumberFormat('0');
  sheet.showGridLines=false;sheet.freezePanes.freezeRows(5);
  book.recalculate();
  console.log((await book.inspect({kind:'table',range:'SeasonBorrowedDecks!A1:E9',maxChars:1500,tableMaxRows:9,tableMaxCols:5})).ndjson);
  console.log((await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
  for(const [name,range]of[['all-templates','A1:E65']]) {
    const png=await book.render({sheetName:sheet.name,range,scale:1.25,format:'png'});
    await fs.writeFile(new URL(`${name}.png`,output),new Uint8Array(await png.arrayBuffer()));
  }
  await(await SpreadsheetFile.exportXlsx(book)).save(new URL('FantasyCard_Config.xlsx',output).pathname.replace(/^\//,''));
  await fs.writeFile(new URL('loan-rows.json',output),JSON.stringify(values));
  console.log('Added one required template sheet; original workbook unchanged pending preservation checks.');
}
