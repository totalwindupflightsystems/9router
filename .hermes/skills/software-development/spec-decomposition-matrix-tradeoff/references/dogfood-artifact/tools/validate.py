#!/usr/bin/env python3
import json,re,sys
from pathlib import Path
base=Path(__file__).resolve().parents[1]
errors=[]
data=json.loads((base/'registers.json').read_text())
schema=json.loads((base/'matrix.schema.json').read_text())
try:
 import jsonschema
 for e in sorted(jsonschema.Draft7Validator(schema).iter_errors(data),key=lambda x:list(x.path)):
  errors.append('schema '+'.'.join(map(str,e.path))+': '+e.message)
except ImportError:
 print('WARN jsonschema unavailable; structural checks continue')
required_arrays={'decisions','tradeoffs','escalations','unknowns','assumptions','contradictions','core_checks'}
missing=required_arrays-set(data)
if missing: errors.append('missing arrays: '+','.join(sorted(missing)))
ids={}
for group in required_arrays:
 for row in data.get(group,[]):
  rid=row.get('id')
  if not rid: errors.append(f'{group} row missing id'); continue
  if rid in ids: errors.append(f'duplicate id {rid}')
  ids[rid]=group
decisions={d['id']:d for d in data['decisions']}
assumptions={a['id'] for a in data['assumptions']}
cores={c['id'] for c in data['core_checks']}
contradictions={c['id'] for c in data['contradictions']}
escalations={e['id'] for e in data['escalations']}
for d in data['decisions']:
 did=d['id']
 if len(d.get('alternatives_considered',[]))<2: errors.append(f'{did} fewer than 2 alternatives')
 b=d.get('breaks','')
 if not b: errors.append(f'{did} empty breaks')
 if b.strip().lower().startswith('none') and 'checked against' not in b.lower(): errors.append(f'{did} unqualified breaks:none')
 if 'depends_on' not in d: errors.append(f'{did} missing depends_on')
 if not d.get('reversal_cost'): errors.append(f'{did} missing reversal_cost')
 for x in d.get('depends_on',[]):
  if x not in decisions: errors.append(f'{did} dangling depends_on {x}')
 for x in d.get('assumptions',[]):
  if x not in assumptions: errors.append(f'{did} dangling assumption {x}')
 for x in d.get('contradicts',[]):
  if x not in contradictions: errors.append(f'{did} dangling contradiction {x}')
 if d.get('core_check') not in cores: errors.append(f"{did} dangling core_check {d.get('core_check')}")
for t in data['tradeoffs']:
 if len(t.get('candidates',[]))<2: errors.append(f"{t['id']} fewer than 2 candidates")
 if t.get('recommendation')=='escalate' and t.get('escalation_id') not in escalations: errors.append(f"{t['id']} dangling escalation")
 for c in t.get('candidates',[]):
  for x in c.get('assumptions',[]):
   if x not in assumptions: errors.append(f"{t['id']} dangling candidate assumption {x}")
for u in data['unknowns']:
 for k in ['owner','deadline_or_trigger','containment_default','evidence_to_close']:
  if not u.get(k): errors.append(f"{u['id']} missing {k}")
 for x in u.get('decisions_affected',[]):
  if x not in decisions: errors.append(f"{u['id']} dangling decision {x}")
for c in data['contradictions']:
 if c['status']!='OPEN' and (not c.get('resolution') or not c.get('resolved_date_or_trigger')): errors.append(f"{c['id']} closed without resolution fields")
 for x in c.get('affected_decisions',[]):
  if x not in decisions: errors.append(f"{c['id']} dangling affected decision {x}")
index=(base/'_index.md').read_text() if (base/'_index.md').exists() else ''
for c in data['contradictions']:
 if c['status']=='OPEN' and c['id'] not in index: errors.append(f"{c['id']} open but absent from index")
decision_md=(base/'03-decisions.md').read_text()
for d in data['decisions']:
 if d['classification']=='BEFORE-BUILD' and not re.search(r'^\| '+re.escape(d['id'])+r' \|',decision_md,re.M): errors.append(f"{d['id']} absent from invariant-test map")
files=list((base/'02-domains').glob('4.*.md'))
nums={p.name[:4] for p in files}
expected={f'4.{i:02d}' for i in range(1,45)}
if nums!=expected: errors.append(f'domain coverage missing={sorted(expected-nums)} extra={sorted(nums-expected)}')
if len(files)!=44: errors.append(f'expected exactly 44 canonical domain files, found {len(files)}')
for p in files:
 text=p.read_text()
 if 'status: NOT-REACHED' in text:
  for k in ['reason:','owner:','trigger:','containment_default:']:
   if k not in text: errors.append(f'{p.name} NOT-REACHED missing {k}')
 else:
  for k in ['Battery and cascade','Decisions and break-check result','Core check','Required output','terminating ring 5']:
   if k.lower() not in text.lower(): errors.append(f'{p.name} cascaded missing {k}')
print(json.dumps({'status':'PASS' if not errors else 'FAIL','counts':{k:len(data[k]) for k in sorted(required_arrays)},'canonical_domain_files':len(files),'errors':errors},indent=2))
sys.exit(1 if errors else 0)
