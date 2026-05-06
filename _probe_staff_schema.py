import django
django.setup()
from core.arbor import get_arbor_client
c, e = get_arbor_client()
q = '{ __type(name: "Staff") { name fields { name type { name kind ofType { name kind } } } } }'
data = c.graphql(q)
t = data.get('__type') or {}
print('Staff type fields:')
for f in (t.get('fields') or []):
    ty = f.get('type') or {}
    tn = ty.get('name') or (ty.get('ofType') or {}).get('name') or ty.get('kind')
    print(' ', f['name'], '->', tn)
