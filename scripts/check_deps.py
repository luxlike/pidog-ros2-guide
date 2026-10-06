"""List python modules imported by pidog / robot_hat that are NOT installed.

Run inside the container (note: -i, not -it, when piping):
    docker exec -i pidog python3 - < scripts/check_deps.py

Expected output when everything is installed:  missing: []
Optional modules such as `vilib` (camera) can be ignored for the driver.
"""
import ast
import importlib.util
import pathlib
import sysconfig

roots = {
    pathlib.Path(p)
    for p in (
        '/usr/local/lib/python3.14/dist-packages',
        sysconfig.get_paths()['purelib'],
    )
}
mods = set()
for root in roots:
    for pkg in ('pidog', 'robot_hat'):
        base = root / pkg
        if not base.exists():
            continue
        for f in base.rglob('*.py'):
            tree = ast.parse(f.read_text(errors='ignore'))
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    mods.update(a.name.split('.')[0] for a in n.names)
                elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                    mods.add(n.module.split('.')[0])

print('missing:', sorted(m for m in mods if importlib.util.find_spec(m) is None))
