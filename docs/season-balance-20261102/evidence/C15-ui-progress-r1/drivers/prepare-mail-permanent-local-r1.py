from pathlib import Path

base=Path(__file__).parent;source=(base/'run-journey-claims-local-r3.py').read_text('utf-8')
source=source.replace("out=base/'journey-claims-local-r3'", "out=base/'mail-permanent-local-r1'")
old='FullyQualifiedName~JourneyRewardEncodingTests|FullyQualifiedName~SeasonJourneyEncodingTests|FullyQualifiedName~SeasonShopEncodingTests'
new='FullyQualifiedName~MailClaimContractTests|FullyQualifiedName~MailTemplateEncodingTests|FullyQualifiedName~SystemMailCatalogTests|FullyQualifiedName~JourneyRewardEncodingTests|FullyQualifiedName~SeasonShopEncodingTests'
assert old in source;source=source.replace(old,new).replace('encoding.trx','mail-local.trx')
target=base/'run-mail-permanent-local-r1.py';assert not target.exists();target.write_text(source,encoding='utf-8');compile(source,str(target),'exec')
print(str(target))
