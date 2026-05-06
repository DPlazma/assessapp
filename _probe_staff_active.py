import django
django.setup()
from core.arbor import get_arbor_client
c, e = get_arbor_client()
data = c.graphql('{ Staff { id displayName leavingDate isActiveInSchool isActiveTeachingInSchool } }')
staff = data.get('Staff', [])
total = len(staff)
active = [s for s in staff if s.get('isActiveInSchool')]
no_leave = [s for s in staff if not s.get('leavingDate')]
both = [s for s in staff if s.get('isActiveInSchool') and not s.get('leavingDate')]
teaching = [s for s in staff if s.get('isActiveTeachingInSchool')]
print(f'Total: {total}')
print(f'isActiveInSchool=True: {len(active)}')
print(f'no leavingDate: {len(no_leave)}')
print(f'BOTH active AND no leavingDate: {len(both)}')
print(f'isActiveTeachingInSchool=True: {len(teaching)}')
print()
# Discrepancy: people with no leavingDate but not active
inactive_no_leave = [s for s in staff if not s.get('isActiveInSchool') and not s.get('leavingDate')]
print(f'\nNot active but also no leavingDate (these would have been wrongly included): {len(inactive_no_leave)}')
for s in inactive_no_leave[:8]:
    print(' ', s['id'], s.get('displayName'))
