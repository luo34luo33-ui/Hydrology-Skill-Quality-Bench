"""Build public interfaces only from frozen source/API files; never read expected/."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.atomic_contracts import VERSION, digest, tree_digest, render
from harness.runner import discover_tasks
from harness.reporter import write_json


def shape(node):
    if isinstance(node, ast.Dict):
        return {k.value: shape(v) for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    if isinstance(node, (ast.List, ast.Tuple)):
        return {'type': 'array', 'items': shape(node.elts[0]) if node.elts else {'type': 'unknown'}}
    if isinstance(node, ast.Constant):
        return {'type': 'null' if node.value is None else
                'boolean' if isinstance(node.value, bool) else
                'number' if isinstance(node.value, (int, float)) else 'string'}
    return {'type': 'computed; see field semantics'}


def source_interfaces(directory: Path) -> dict:
    objects, arrays, fields, dynamic, enums, constants, layers = [], [], set(), set(), {}, {}, []
    enum_keys = {'status', 'method', 'mode', 'unit', 'units', 'flow_unit', 'schema_version',
                 'language', 'alpha_decision', 'outcome', 'review_status', 'result_kind'}
    for p in sorted(directory.rglob('*.py')):
        if p.name.startswith(('make_', 'test_')) or '__pycache__' in p.parts:
            continue
        tree = ast.parse(p.read_text(encoding='utf-8-sig'))
        for assignment in ast.walk(tree):
            if isinstance(assignment, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'STATISTICS' for t in assignment.targets):
                if isinstance(assignment.value, (ast.List, ast.Tuple)) and all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in assignment.value.elts):
                    names = [x.value for x in assignment.value.elts]
                    dynamic.add('^.+_(?:' + '|'.join(re.escape(x) for x in names) + ')$')
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                obj = shape(node)
                if obj and obj not in objects:
                    objects.append(obj)
                fields.update(k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in enum_keys:
                        for child in ast.walk(value):
                            if isinstance(child, ast.Constant) and isinstance(child.value, str) and len(child.value) < 120:
                                enums.setdefault(key.value, set()).add(child.value)
                    if isinstance(key, ast.Constant) and key.value in {'schema_version', 'template', 'template_id', 'figure_type', 'width_px', 'height_px', 'flow_unit', 'method'} and isinstance(value, ast.Constant):
                        constants.setdefault(key.value, set()).add(value.value)
                keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                if {'id', 'source', 'display_transform', 'palette'}.issubset(keys):
                    spec = {k.value: v.value if isinstance(v, ast.Constant) else 'Input-dependent display metadata; preserve source scientific values.'
                            for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
                    if spec not in layers: layers.append(spec)
            elif isinstance(node, (ast.List, ast.Tuple, ast.Set)) and node.elts and all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in node.elts):
                names = [x.value for x in node.elts]
                if all(not x.startswith('--') and len(x) < 80 for x in names):
                    if names not in arrays: arrays.append(names)
                    fields.update(names)
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                fields.add(node.slice.value)
            elif isinstance(node, ast.keyword) and node.arg:
                fields.add(node.arg)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument':
                flags = [x.value for x in node.args if isinstance(x, ast.Constant) and isinstance(x.value, str)]
                if any(flag.endswith('-column') for flag in flags):
                    for keyword in node.keywords:
                        if keyword.arg == 'default' and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                            fields.add(keyword.value.value)
            elif isinstance(node, ast.JoinedStr):
                fixed = ''.join(x.value for x in node.values if isinstance(x, ast.Constant) and isinstance(x.value, str))
                pattern = ''.join(re.escape(x.value) if isinstance(x, ast.Constant) and isinstance(x.value, str) else '.+' for x in node.values)
                if any(x.isalpha() for x in fixed) and ' ' not in pattern and len(pattern) < 100:
                    dynamic.add('^' + pattern + '$')
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
                suffix = node.right.value
                if re.fullmatch(r'_[a-zA-Z0-9_]+', suffix): dynamic.add('^.+ ' .replace(' ', '') + re.escape(suffix) + '$')
    for p in sorted(directory.rglob('*.schema.json')):
        def schema_fields(obj):
            if isinstance(obj, dict):
                fields.update(obj.get('properties', {}).keys())
                for value in obj.values(): schema_fields(value)
            elif isinstance(obj, list):
                for value in obj: schema_fields(value)
        schema_fields(json.loads(p.read_text(encoding='utf-8')))
    return {'object_structures': objects, 'named_field_sets': arrays, 'field_names': sorted(fields),
            'literal_enum_values': {key: sorted(values) for key, values in sorted(enums.items())},
            'static_interface_values': {key: sorted(values, key=str) for key, values in sorted(constants.items())},
            'figure_layer_interfaces': layers,
            'dynamic_field_patterns': sorted(dynamic),
            'passthrough_policy': 'Preserve applicable input columns and configured identifiers. Dynamic output names follow the source interface patterns; tables can carry upstream fields.'}


def presentation_interfaces(ref, public):
    """Source-defined schemas/layout constraints, not implementations or task truth."""
    assets = public / 'programs/visualization-reporting/assets'
    names = {
        'visualize-dem-hydrology-atlas': ['atlas-style-v2.json'],
        'visualize-flood-event-atlas': ['flood-event-style-v2.json'],
        'visualize-hydrobase-atlas': ['atlas-style-v2.json', 'topology-style-v2.json', 'morphometry-style-v2.json'],
        'visualize-model-calibration': ['calibration-atlas-style-v2.json', 'calibration-event-manifest.schema.json'],
        'generate-timeseries-data-processing-report': ['processing-manifest.schema.json', 'processing-report.schema.json', 'report-layout-v2.json'],
        'generate-spatial-data-processing-report': ['spatial-processing-manifest.schema.json', 'processing-report.schema.json', 'report-layout-v2.json'],
        'generate-hydrological-study-report': ['study-manifest.schema.json', 'study-report.schema.json', 'report-layout-v2.json'],
        'review-hydrological-study-report': ['study-report.schema.json', 'processing-report.schema.json', 'study-review.schema.json', 'study-semantic-review.schema.json'],
    }.get(ref.split('/')[-1], [])
    if not names: return {}
    interface = {'schemas_and_layouts': {name: json.loads((assets / name).read_text(encoding='utf-8')) for name in names}}
    if ref.endswith('visualize-dem-hydrology-atlas'):
        interface['pixel_size_rule'] = 'Use the displayed map extent width/height and frame margins l,b,r,t from the template. Canvas aspect = map aspect * (1-b-t)/(1-l-r). The longer canvas side is longest_edge_px; round the other side to the nearest integer pixel. PNG/SVG/metadata dimensions must agree.'
    if ref.endswith('visualize-hydrobase-atlas'):
        interface['pixel_size_rule'] = 'Topology/QC map panel width 9.7 inches, height 9.7 * extent_height/extent_width; canvas adds 0.8 inches horizontally and 0.65 vertically, rescales longest side to 12 inches and rounds each side to 1/200 inch at 200 dpi. Morphometry map width 12 inches, height clamp(3.42 * extent_height/extent_width + 1, template height_range_inches), rounded to 1/200 inch at 200 dpi.'
    return interface


def input_fields(folder: Path, task: dict) -> list[str]:
    import csv
    fields = set()
    def keys(value):
        if isinstance(value, dict):
            fields.update(value)
            for child in value.values(): keys(child)
        elif isinstance(value, list):
            for child in value: keys(child)
        elif isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', value):
            fields.add(value)  # User-supplied column/route identifiers, not reference values.
    for name in task['data_files']:
        p = folder / 'data' / name
        if p.suffix.lower() == '.csv':
            with p.open(encoding='utf-8-sig', newline='') as stream:
                fields.update(next(csv.reader(stream), []))
        elif p.suffix.lower() == '.json':
            keys(json.loads(p.read_text(encoding='utf-8-sig')))
        elif p.suffix.lower() in {'.xlsx', '.xls'}:
            import pandas as pd
            with pd.ExcelFile(p) as book:
                for sheet in book.sheet_names:
                    fields.update(str(x) for x in pd.read_excel(book, sheet_name=sheet, nrows=0).columns)
    return sorted(fields)


def baseflow_details():
    return {
        'method_definition': 'Single forward Eckhardt recursion; initial baseflow equals initial discharge; clamp each result to [0, discharge]. No backward pass.',
        'tables': {'flow_components': ['time', 'discharge_m3_s', 'is_imputed', 'baseflow_m3_s', 'quickflow_m3_s', 'quickflow_fraction']},
        'objects': {'baseflow_metadata': ['schema_version', 'method', 'alpha', 'alpha_decision', 'recession_pair_count', 'bfi_max', 'flow_unit', 'row_count', 'upstream_series_metadata']},
        'semantics': {'quickflow_fraction': 'quickflow/discharge; zero when discharge is zero',
                      'alpha_decision': ['user-provided', 'estimated-90th-quantile-of-recession-ratios'],
                      'recession_pair_count': 'Count used for automatic estimation; zero for explicitly supplied alpha',
                      'method': 'Eckhardt digital filter'},
        'warning_rule': 'Propagate upstream warnings; status is warning if warnings are present, otherwise success. Invalid inputs use the error branch.'}


def main():
    tasks = discover_tasks(ROOT / 'tests')
    if len(tasks) != 183:
        raise ValueError('Expected the frozen 183-task baseline')
    catalog = json.loads((ROOT / 'docs/atomic-skill-catalog.json').read_text(encoding='utf-8'))
    baseline_path = ROOT / 'docs/atomic-three-arm-baseline.json'
    if not baseline_path.exists():
        write_json(baseline_path, {'version': VERSION, 'tasks': {
            x['task']['id']: {'grading': x['task']['grading'], 'required_outputs': x['task']['required_outputs'],
                            'data_files': x['task']['data_files'], 'timeout_seconds': x['task']['timeout_seconds'],
                            'data_sha256': tree_digest(x['task_dir'] / 'data'),
                            'expected_sha256': tree_digest(x['task_dir'] / 'expected')}
            for x in tasks}})
    source = ROOT / 'runtime/public'
    target = ROOT / 'runtime/atomic-public'
    if target.exists(): shutil.rmtree(target)
    target.mkdir(parents=True)
    # Explicit allowlist: no recipes, generators, synthetic example data, or skill prose.
    for p in sorted((source / 'programs').rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts: continue
        if p.name.startswith(('make_', 'test_')) or 'example' in p.name.lower() or p.name.startswith('synthetic_'): continue
        if p.suffix not in {'.py', '.json', '.yaml', '.yml'}: continue
        destination = target / p.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, destination)
    shutil.copyfile(source / 'native_bootstrap.py', target / 'native_bootstrap.py')
    index = json.loads((source / 'programs.json').read_text(encoding='utf-8'))
    write_json(target / 'programs.json', index)
    # Command documentation is separate from the shared contract. Remove composite confirmation service.
    documentation = (source / 'PROGRAM_INTERFACES.md').read_text(encoding='utf-8').split('## User confirmation')[0]
    documentation = documentation.replace('/public/', './public/')
    documentation = documentation.replace('`PROGRAM_DATA_CONTRACTS.json`', '`../PUBLIC_CONTRACT.md`')
    (target / 'PROGRAM_INTERFACES.md').write_text(documentation, encoding='utf-8')
    capability_root = ROOT / 'docs/atomic-public-contracts'
    capabilities = {}
    for ref in sorted(index):
        frozen = ROOT / 'docs/composite-contracts' / ref
        import yaml
        source_contract = yaml.safe_load((frozen / 'data-contract.yaml').read_text(encoding='utf-8')) or {}
        capability = {'version': VERSION, 'interface_id': ref,
                      'source_contract_sha256': digest(frozen / 'data-contract.yaml'),
                      'interface': {k: source_contract[k] for k in ('schema_version', 'inputs', 'outputs', 'parameters', 'warmup_period', 'simulation_period', 'invariants') if k in source_contract},
                      'serialization': source_interfaces(target / 'programs' / ref),
                      'common_result': {'fields': ['schema_version', 'skill', 'status', 'message', 'parameters', 'inputs', 'artifacts', 'checks', 'warnings', 'provenance'],
                                        'status_branches': ['success', 'warning', 'error'],
                                        'artifact_reference': {'path': 'relative to result directory', 'sha256': 'SHA-256 of actual referenced file'},
                                        'skill': ref},
                      'precision': 'Preserve IEEE-754 double precision; write computed CSV numbers with 17 significant digits; never round intermediate calculations.'}
        presentation = presentation_interfaces(ref, target)
        if presentation: capability['presentation_interface'] = presentation
        if ref == 'data-processing/separate-baseflow-eckhardt': capability['details'] = baseflow_details()
        capabilities[ref] = capability
        write_json(capability_root / (ref.replace('/', '--') + '.json'), capability)
        (capability_root / (ref.replace('/', '--') + '.md')).write_text(render(capability), encoding='utf-8')
    for item in tasks:
        task = item['task']
        contract = {'version': VERSION, 'task_id': task['id'], 'capability': capabilities[task['primary_skill']],
                    'inputs': task['data_files'], 'outputs': task['required_outputs'],
                    'input_field_names': input_fields(item['task_dir'], task),
                    'declared_settings': 'Confirmed settings remain in the shared task prompt and input configurations; no invocation commands are duplicated in this contract.',
                    'branch_policy': 'Determine applicable branch from inputs. This document does not preselect outcome or expected numerical results.'}
        write_json(item['task_dir'] / 'public_contract.json', contract)
        task['public_contract'] = 'public_contract.json'
        item['task_path'].write_text(json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    skill_target = ROOT / 'runtime/atomic-skills'
    if skill_target.exists(): shutil.rmtree(skill_target)
    skill_target.mkdir()
    public_hashes = {digest(p): p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
    equivalence, assets_equivalence, omitted = [], [], []
    for skill in sorted((ROOT / 'runtime/skills').iterdir()):
        if not skill.is_dir() or not (skill / 'SKILL.md').is_file(): continue
        for p in sorted(skill.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts: continue
            if p.name.startswith(('make_', 'test_')) or 'example' in p.name.lower() or p.name.startswith('synthetic_'):
                omitted.append(p.relative_to(ROOT / 'runtime/skills').as_posix()); continue
            if p.suffix == '.py':
                shared = public_hashes.get(digest(p))
                if shared is None: raise ValueError('skill contains exclusive scientific code: ' + str(p))
                equivalence.append({'skill_file': p.relative_to(ROOT / 'runtime/skills').as_posix(), 'public_file': shared, 'sha256': digest(p)})
            elif p.suffix in {'.json', '.yaml', '.yml'} and ('assets' in p.parts or p.name.endswith('.schema.json')):
                shared = public_hashes.get(digest(p))
                if shared is None: raise ValueError('skill contains exclusive runtime asset: ' + str(p))
                assets_equivalence.append({'skill_file': p.relative_to(ROOT / 'runtime/skills').as_posix(), 'public_file': shared, 'sha256': digest(p)})
            if p.suffix not in {'.md', '.py', '.json', '.yaml', '.yml'}: continue
            dest = skill_target / p.relative_to(ROOT / 'runtime/skills')
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
    write_json(ROOT / 'docs/atomic-program-equivalence.json', {'scientific_files': equivalence,
               'runtime_assets': assets_equivalence,
               'omitted_generators_and_examples': omitted, 'skills_sha256': tree_digest(skill_target),
               'public_programs_sha256': tree_digest(target)})
    # Do not make readiness claims: a separate host-only audit checks completeness.
    write_json(ROOT / 'docs/atomic-public-build.json', {'version': VERSION, 'tasks': len(tasks), 'capabilities': len(capabilities),
                'public_programs_sha256': tree_digest(target), 'source_inventory': catalog.get('snapshot_date'),
                'oracle_read_by_contract_builder': False, 'formal_ready': False})


if __name__ == '__main__': main()
