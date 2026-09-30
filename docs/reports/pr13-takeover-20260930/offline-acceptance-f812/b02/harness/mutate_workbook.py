import pathlib, sys, zipfile, xml.etree.ElementTree as ET
p=pathlib.Path(sys.argv[1]);ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(p) as z:
    files={name:z.read(name) for name in z.namelist()}
    workbook=ET.fromstring(files['xl/workbook.xml'])
    sheet=next(x for x in workbook.find('m:sheets',ns) if x.attrib['name']=='NumericalRules')
    rid=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
    rels=ET.fromstring(files['xl/_rels/workbook.xml.rels'])
    target=next(x.attrib['Target'] for x in rels if x.attrib['Id']==rid)
    target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
    xml=ET.fromstring(files[target])
    for addr in ['B6','C6']:
        cell=xml.find(f'.//m:c[@r="{addr}"]',ns)
        assert cell is not None and cell.attrib.get('t')=='b',addr
        cell.find('m:v',ns).text='1'
    files[target]=ET.tostring(xml,encoding='utf-8',xml_declaration=True)
with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
    for name,data in files.items():z.writestr(name,data)
