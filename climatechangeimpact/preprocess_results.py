"""Run this ONCE locally to bundle every regions/<country>/<region>/results.json
into a single all_results.json file that the interactive notebook can fetch.

Usage (from the directory that contains `regions/`):
    python preprocess_results.py

Output: all_results.json next to this script.
"""
import json
from pathlib import Path


def parse_rp(value):
    if isinstance(value, (int, float)):
        return float(value), 0.0
    s = str(value)
    if '\u00b1' in s:
        a, b = s.split('\u00b1')
        return float(a.strip()), float(b.strip())
    return float(s.strip()), 0.0


def get_scenario_label(key):
    k = key.lower()
    if 'modelled discharge' in k or ('cmip' in k and 'ssp' not in k):
        return 'CMIP6 hist', 0
    if k == 'era5':
        return 'ERA5', 1
    if 'destine' in k and ('hist' in k or 'historical' in k):
        return 'DestinE hist', 2
    if 'ssp126' in k: return 'SSP1-2.6', 3
    if 'ssp245' in k: return 'SSP2-4.5', 4
    if 'ssp370' in k: return 'SSP3-7.0', 5
    if 'ssp585' in k: return 'SSP5-8.5', 6
    if 'destine' in k: return 'DestinE future', 7
    return None, 99


def dominant_kg(kg_dict):
    return max(kg_dict, key=kg_dict.get)


REQUIRED = {'return_periods_HBV', 'koppen_geiger',
            'catchment_area_km2', 'calibration_HBV'}

base = Path('regions')
rows = []
n_files = n_skipped = 0

for results_file in sorted(base.rglob('results.json')):
    n_files += 1
    country = results_file.parts[-3]
    region  = results_file.parts[-2]
    with open(results_file) as f:
        data = json.load(f)

    if not REQUIRED <= data.keys():
        n_skipped += 1; continue
    if 'observed_reference' not in data['return_periods_HBV']:
        n_skipped += 1; continue

    kg_dom   = dominant_kg(data['koppen_geiger'])
    kg_group = kg_dom[0]
    calib    = data.get('calibration_HBV', {}) or {}
    rp_dict  = data['return_periods_HBV']
    obs      = rp_dict['observed_reference']
    q100     = float(obs.get('q100_mm_d', 0.0))
    area     = float(data['catchment_area_km2'])

    for key, vals in rp_dict.items():
        if key == 'observed_reference':
            continue
        if not isinstance(vals, dict):
            continue
        rp_val = vals.get('rp_at_obs_q100')
        if rp_val is None:
            continue
        label, order = get_scenario_label(key)
        if label is None:
            continue
        mean, std = parse_rp(rp_val)
        rows.append({
            'country': country,
            'region':  region,
            'caravan_id':         data.get('caravan_id', ''),
            'catchment_area_km2': area,
            'kg_dominant':        kg_dom,
            'kg_group':           kg_group,
            'scenario_label':     label,
            'order':              order,
            'rp_mean':            mean,
            'rp_std':             std,
            'q100_mm_d':          q100,
            'q100_m3s':           q100 * area / 86.4,
            'KGE':                calib.get('KGE'),
            'NSE':                calib.get('NSE'),
            'Nelder_Mead':        calib.get('Nelder-Mead'),
        })

out = Path('all_results.json')
with open(out, 'w') as f:
    json.dump(rows, f, separators=(',', ':'))   # compact

n_regions  = len({(r['country'], r['region']) for r in rows})
size_kb    = out.stat().st_size / 1024
print(f'Scanned   : {n_files} results.json files')
print(f'Skipped   : {n_skipped}')
print(f'Regions   : {n_regions}')
print(f'Rows      : {len(rows)}')
print(f'Output    : {out} ({size_kb:.1f} KB)')
