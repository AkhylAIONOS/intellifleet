"""Check numeric and lifecycle invariants in captured real Azure results."""
import json
from pathlib import Path
rows=json.loads(Path('tests/ps30_live_results.json').read_text())['records']
checks=[]
for row in rows:
    body=row.get('body',{})
    data=((body.get('actions') or [{}])[0].get('data') or {})
    plan=data.get('recommended_plan') or data.get('recovery_plan')
    if plan:
        assert 0<=plan['risk_score']<=1
        assert plan['operational_cost']>=0
        assert all(v.get('assigned_load_kg',0)<=v['capacity'] for v in plan['vehicles'])
        checks.append('plan invariants: '+row['prompt'])
    if data.get('planning_operation')=='warehouse_capacity' and 'Bengaluru South Hub' in row['prompt']:
        assert [w['warehouse'] for w in data['warehouses']]==['IF Bengaluru South Hub']
        checks.append('PS16 exact warehouse scope')
    if data.get('status')=='draft' and data.get('baseline'):
        assert row['context']['selected_plan']['plan_id']==data['baseline']['recommended_plan']['plan_id']
        checks.append('draft retains baseline: '+row['prompt'])
    if data.get('status')=='applied':
        assert row['context']['selected_plan']==data['approved_plan']
        checks.append('PS29 apply updates active plan')
    if data.get('status')=='discarded':
        prior=rows[rows.index(row)-1]
        assert row['context']['selected_plan']==prior['context']['selected_plan']
        checks.append('PS29 discard retains baseline')
assert 'PS16 exact warehouse scope' in checks
assert 'PS29 apply updates active plan' in checks and 'PS29 discard retains baseline' in checks
Path('tests/ps30_live_invariants.json').write_text(json.dumps({'passed_checks':len(checks),'checks':checks,'scope':'Numeric and lifecycle checks only; not complete PS acceptance.'},indent=2))
print(f'PASS: {len(checks)} captured live numeric/context checks; not a 30/30 claim')
