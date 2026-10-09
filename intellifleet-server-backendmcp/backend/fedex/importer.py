"""Read local XLSX with the standard library. Preserve source cells and warnings."""
import math
import os
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import Schedule

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
HEADERS = {
    'Air': ['Origin City', 'Origin Station', 'Transit GTW', 'Lane', 'Run', 'Mode', 'Flight', 'Handover', 'ETD', 'ETA', 'Retrieval'],
    'Surface': ['Origin City', 'Origin Station', 'Transit Hub/GTW', 'Lane', 'Run', 'Mode', 'Details', 'No of Vechiles', 'Handover at Orgn', 'ETD', 'ETA', 'TT (hours)'],
}


def workbook_path():
    configured = os.environ.get('FEDEX_WORKBOOK_PATH')
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / 'data' / 'client-network-plan.xlsx'


def clean(value):
    return ' '.join(str('' if value is None else value).split())


def time_minutes(value):
    value = clean(value)
    if value in {'', '-', 'NA', 'N/A'}:
        return None
    if ':' in value:
        parts = value.split(':')
        if len(parts) not in (2, 3):
            raise ValueError('Invalid clock time')
        h, m = int(parts[0]), int(parts[1])
        seconds = float(parts[2]) if len(parts) == 3 else 0
        if not (0 <= h < 24 and 0 <= m < 60 and 0 <= seconds < 60):
            raise ValueError('Invalid clock time')
        return round(h * 60 + m + seconds / 60) % 1440
    fraction = float(value)
    if not math.isfinite(fraction) or not 0 <= fraction < 1:
        raise ValueError('Expected Excel time fraction or HH:MM')
    return round(fraction * 1440) % 1440


def normalize_row(sheet, row_number, raw, duration_is_time=True, formulas=None, provenance=None):
    source = {clean(k): str(v) for k, v in raw.items()}
    row = {k: clean(v) for k, v in source.items()}
    warnings = []
    valid = True
    mode = {'air': 'AIR', 'surface': 'SURFACE', 'train': 'RAIL', 'rail': 'RAIL'}.get(row.get('Mode', '').lower())
    if mode is None:
        raise ValueError(f'{sheet} row {row_number}: unsupported Mode {row.get("Mode")}')
    times = {}
    for field, header in [('cutoff_minutes', 'Handover' if sheet == 'Air' else 'Handover at Orgn'),
                          ('etd_minutes', 'ETD'), ('eta_minutes', 'ETA'), ('retrieval_minutes', 'Retrieval')]:
        try:
            times[field] = time_minutes(row.get(header, ''))
        except (ValueError, OverflowError):
            times[field] = None
            warnings.append(f'INVALID_{header}: {row.get(header)}')
            valid = False
    if times['cutoff_minutes'] is None:
        warnings.append('CUTOFF_UNAVAILABLE: eligibility cannot be confirmed')
    if times['etd_minutes'] is None or times['eta_minutes'] is None:
        valid = False
        warnings.append('MISSING_ETD_OR_ETA')
    transit = None
    raw_tt = row.get('TT (hours)', '')
    if raw_tt not in {'', '-'}:
        try:
            if ':' in raw_tt:
                h, m = raw_tt.split(':')
                if int(h) < 0 or not 0 <= int(m) < 60:
                    raise ValueError('Invalid duration')
                transit = int(h) * 60 + int(m)
            else:
                transit = float(raw_tt) * (1440 if duration_is_time else 60)
            if not math.isfinite(transit) or transit < 0:
                raise ValueError('Invalid duration')
        except (ValueError, OverflowError):
            warnings.append('INVALID_TRANSIT_TIME')
            transit = None
            valid = False
    if transit is not None and times['etd_minutes'] is not None and times['eta_minutes'] is not None:
        clock_duration = (times['eta_minutes'] - times['etd_minutes']) % 1440
        if abs(clock_duration - transit) > 1:
            warnings.append(f'TRANSIT_MISMATCH: ETD/ETA imply {clock_duration} minutes; source TT is {transit:g} minutes; source unchanged')
            valid = False
    count = None
    if row.get('No of Vechiles', '') not in {'', '-'}:
        try:
            number = float(row['No of Vechiles'])
            if not number.is_integer() or number < 0:
                raise ValueError('Invalid count')
            count = int(number)
        except (ValueError, OverflowError):
            warnings.append('INVALID_VEHICLE_COUNT')
            valid = False
    origin = row.get('Origin Station', '').upper()
    gateway = row.get('Transit GTW' if sheet == 'Air' else 'Transit Hub/GTW', '').upper()
    if not origin or not gateway:
        valid = False
        warnings.append('MISSING_STATION_OR_GATEWAY')
    warnings.append('CALENDAR_UNKNOWN: schedule template only; operating days not verified')
    lane=row.get('Lane','')
    if lane=='UNSUPPORTED_FORMULA' or lane.startswith('='):
        formula=(formulas or {}).get('Lane',lane)
        if re.fullmatch(r'=?_xlfn\.CONCAT\(B\d+,"-",C\d+\)',formula,re.I) and origin and gateway:
            lane=f'{origin}-{gateway}'
            warnings.append('Lane derived from source station/gateway; original formula retained')
            provenance={**(provenance or {}),'Lane':'DERIVED_FROM_SOURCE_FIELDS'}
        else:
            lane='Lane unavailable'
            warnings.append('Lane formula has no usable cached value; inspect original workbook')
    return Schedule(schedule_id=f'{sheet.lower()}-{row_number}', source_sheet=sheet, source_row=row_number,
                    origin_city=row.get('Origin City', ''), origin_station=origin, gateway=gateway,
                    lane=lane, run=row.get('Run', ''), mode=mode, source_mode=row.get('Mode', ''),
                    service=row.get('Flight' if sheet == 'Air' else 'Details', ''), transit_minutes=transit,
                    vehicle_count=count, source=source, source_formulas=formulas or {},source_value_provenance=provenance or {},warnings=warnings, valid=valid, **times)


def load_schedules(path=None):
    schedules = []
    with zipfile.ZipFile(path or workbook_path()) as book:
        if sum(x.file_size for x in book.infolist()) > 20_000_000:
            raise ValueError('Workbook exceeds the 20 MB uncompressed limit')
        strings = []
        if 'xl/sharedStrings.xml' in book.namelist():
            strings = [''.join(x.itertext()) for x in ET.fromstring(book.read('xl/sharedStrings.xml')).findall('m:si', NS)]
        styles = ET.fromstring(book.read('xl/styles.xml'))
        formats = {int(x.attrib['numFmtId']): x.attrib['formatCode'] for x in styles.findall('m:numFmts/m:numFmt', NS)}
        xfs = [int(x.attrib.get('numFmtId', 0)) for x in styles.findall('m:cellXfs/m:xf', NS)]
        relationships = {x.attrib['Id']: x.attrib['Target'] for x in ET.fromstring(book.read('xl/_rels/workbook.xml.rels'))}
        sheets = ET.fromstring(book.read('xl/workbook.xml')).findall('m:sheets/m:sheet', NS)
        if not set(HEADERS) <= {x.attrib['name'] for x in sheets}:
            raise ValueError('Workbook must contain Air and Surface sheets')
        for sheet in sheets:
            name = sheet.attrib['name']
            if name not in HEADERS:
                continue
            target = relationships[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            headers = None
            for row in ET.fromstring(book.read(target)).findall('m:sheetData/m:row', NS):
                cells, time_columns = {}, set()
                formulas,provenance={},{}
                for cell in row.findall('m:c', NS):
                    col = re.sub(r'\d', '', cell.attrib['r'])
                    value = cell.find('m:v', NS)
                    text = value.text if value is not None else ''.join(cell.find('m:is', NS).itertext()) if cell.find('m:is', NS) is not None else ''
                    if cell.attrib.get('t') == 's':
                        text = strings[int(text)]
                    if cell.find('m:f', NS) is not None:
                        formula=cell.find('m:f',NS)
                        formulas[col]='='+formula.text if formula.text else 'Shared formula '+formula.attrib.get('si','')
                        provenance[col]='WORKBOOK_CACHED_VALUE' if text else 'FORMULA_WITHOUT_CACHE'
                        if not text:text=formulas[col]
                    cells[col] = text or ''
                    fmt = xfs[int(cell.attrib.get('s', 0))]
                    if fmt in {18, 19, 20, 21, 22, 45, 46, 47} or re.search('[hHsS]', formats.get(fmt, '')):
                        time_columns.add(col)
                if not any(clean(v) for v in cells.values()):
                    continue
                if headers is None:
                    headers = {c: clean(v) for c, v in cells.items()}
                    missing = set(HEADERS[name]) - set(headers.values())
                    if missing:
                        raise ValueError(f'{name}: missing columns {sorted(missing)}')
                    continue
                raw = {headers[c]: v for c, v in cells.items() if c in headers}
                if not clean(raw.get('Origin Station')) and not clean(raw.get('Mode')):
                    continue
                duration_is_time = any(headers.get(c) == 'TT (hours)' for c in time_columns)
                schedules.append(normalize_row(name,int(row.attrib['r']),raw,duration_is_time,
                    {headers[c]:v for c,v in formulas.items() if c in headers},
                    {headers[c]:v for c,v in provenance.items() if c in headers}))
    return schedules
