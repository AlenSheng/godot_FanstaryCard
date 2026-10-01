import collections,hashlib,json,pathlib,xml.etree.ElementTree as ET
B=pathlib.Path(__file__).resolve().parent
paths=['b02/evidence/trx/domain.trx','b02/evidence/trx/server.trx','b02/evidence/trx-original/server-original.trx','b02/evidence/diagnostic/pooling-false.trx','b02/evidence/diagnostic/pooling-true.trx','a05/evidence/A05-FOCUSED/a05.trx','a05/evidence/A05-CAUSAL/causal.trx','a05/evidence/A05-SERVER295/server295.trx']
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
results=[]
for name in paths:
    p=B/name
    if not p.exists():continue
    r=ET.parse(p).getroot();entries=r.findall('.//t:UnitTestResult',ns)
    counts=collections.Counter(x.attrib['outcome'] for x in entries)
    counters=r.find('.//t:Counters',ns).attrib
    assert int(counters['total'])==len(entries)
    failures=[]
    for x in entries:
        if x.attrib['outcome']=='Failed':
            msg=x.find('.//t:Message',ns);stack=x.find('.//t:StackTrace',ns)
            failures.append(dict(test_name=x.attrib['testName'],message=(msg.text or '') if msg is not None else None,stack=(stack.text or '') if stack is not None else None))
    results.append(dict(path=name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),counters=counters,entry_outcomes=dict(counts),failed_tests=failures))
(B/'SUITES.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps([dict(path=x['path'],outcomes=x['entry_outcomes'],failures=[f['test_name'] for f in x['failed_tests']]) for x in results]))
