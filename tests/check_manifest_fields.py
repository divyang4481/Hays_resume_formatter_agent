import json, sys
sys.path.insert(0, '.')
from src.shared.repository import repo

m = repo.get_manifest('f694b36c-1f5e-4c04-bbdc-ff717e5cbcf8')
if m:
    for f in m.get('fields', []):
        name = f.get('name', '')
        sbi = f.get('source_block_ids', [])
        ft = f.get('field_type', '')
        rc = f.get('render_contract', {})
        strategy = rc.get('render_strategy', '-')
        token = f.get('template_token', '')
        print(f"{name}: type={ft} sbi_count={len(sbi)} strategy={strategy} token={repr(token[:40])}")
