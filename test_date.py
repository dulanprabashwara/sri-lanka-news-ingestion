def _parse_sinhala_date(value: str):
    import re
    from datetime import datetime

    months = {
        "ජනවාරි": 1,
        "පෙබරවාරි": 2,
        "මාර්තු": 3,
        "අප්‍රේල්": 4,
        "මැයි": 5,
        "ජූනි": 6,
        "ජූලි": 7,
        "අගෝස්තු": 8,
        "සැප්තැම්බර්": 9,
        "ඔක්තෝබර්": 10,
        "නොවැම්බර්": 11,
        "දෙසැම්බර්": 12,
    }
    for m_name, m_num in months.items():
        if m_name in value:
            # try to extract year, day, time
            m = re.search(r"(\d{4})\s+" + m_name + r"\s+(\d{1,2})\s+(\d{1,2}):(\d{2})", value)
            if m:
                year, day, hour, minute = map(int, m.groups())
                dt = datetime(year, m_num, day, hour, minute)
                return dt
    return None


print(_parse_sinhala_date("2024 සැප්තැම්බර් 03 12:47"))
