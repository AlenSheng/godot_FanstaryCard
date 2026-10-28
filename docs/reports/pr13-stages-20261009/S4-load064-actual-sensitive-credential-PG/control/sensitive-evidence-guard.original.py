import hashlib
import json
from pathlib import Path
import pr13_public_evidence

root=Path('/control/owned-sensitive-candidates')
rows=[]
for name,expected in [('actual-session-token.json','Sensitive field in public evidence: token'),
                      ('actual-realtime-ticket.json','Sensitive field in public evidence: ticketbody')]:
    p=root/name;data=p.read_bytes()
    entry={'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    failures=[]
    for call in [lambda:pr13_public_evidence.inspect_public(p),
                 lambda:pr13_public_evidence.validated_files(root,[entry])]:
        try:
            call()
        except ValueError as error:
            assert str(error)==expected
            failures.append(str(error))
        else:
            raise AssertionError('Actual credential was admitted to public evidence')
    assert p.read_bytes()==data
    rows.append({**entry,'actual_rejection_messages':failures,'original_sensitive_candidate_preserved':True})
sanitized=Path('/output/public-review-sanitized.original.json')
safe={'ok':True,'actual_sensitive_candidates_rejected':rows,
      'production_credentials_used':False,'generated_ephemeral_test_credentials_only':True}
sanitized.write_bytes((json.dumps(safe,indent=2)+'\n').encode())
pr13_public_evidence.inspect_public(sanitized)
assert pr13_public_evidence.validated_files(sanitized.parent,[{'path':sanitized.name,
    'bytes':sanitized.stat().st_size,'sha256':hashlib.sha256(sanitized.read_bytes()).hexdigest()}])==[sanitized]
print(json.dumps({'ok':True,'actual_sensitive_candidates_rejected':rows,
    'sanitized_metadata_public_review_passed':True,'raw_values_written_to_public_report':False,
    'raw_private_candidates_unchanged':True}))
