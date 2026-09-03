import re
text = 'ශ්‍රී 2024 සැප්තැම්බර් 03'
m_name = 'සැප්තැම්බර්'
m = re.search(r'(\d{4})\s+' + m_name + r'\s+(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?', text)
print('Match:', m.groups() if m else None)
