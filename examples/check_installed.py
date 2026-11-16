"""Check the wheel outside the checkout, including every test and CLI report."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()
ENV.pop('PYTHONPATH', None)
MODULES = ['robustlab', 'robustlab.__main__', 'robustlab.core',
           'robustlab.demo', 'robustlab.exact', 'robustlab.box']
FILES = ['examples/model.json', 'examples/data.json']
COMMANDS = [[name] for name in ['demo', 'exact-demo', 'box-demo']]
COMMANDS += [['audit'] + FILES + ['--norm', 'l2', '--epsilon', '0.4']]
COMMANDS += [['exact-audit'] + FILES + ['--norm', 'linf', '--epsilon', '0.1']]
COMMANDS += [['box-audit'] + FILES + ['examples/bounds.json', '--norm', 'l1',
                                    '--epsilon', '0.3']]
COMMANDS += [['fit', 'examples/data.json', '--norm', 'linf', '--epsilon', '0.3',
              '--steps', '100']]


def call(args, cwd, env=ENV):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True)


with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    wheels = work / 'wheels'
    wheels.mkdir()
    call([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '-w', str(wheels),
          str(ROOT)], work)
    built = list(wheels.glob('*.whl'))
    assert len(built) == 1, built
    venv.create(work / 'env', with_pip=True)
    py = str(work / 'env/bin/python')
    call([py, '-m', 'pip', 'install', '--no-deps', str(built[0])], work)
    outside = work / 'outside'
    outside.mkdir()
    for name in ['tests', 'examples', 'assets']:
        shutil.copytree(ROOT / name, outside / name)
    # Only the test fixtures are copied. No package source goes on this path.
    suite = '''
import importlib,importlib.util,json,pathlib,sys,unittest
outside=pathlib.Path.cwd().resolve()
sys.path.insert(0,str(outside))
names=json.loads(sys.argv[1])
source=pathlib.Path(sys.argv[2]).resolve()
prefix=pathlib.Path(sys.prefix).resolve()
for name in names:importlib.import_module(name)
def check():
    for name in names:
        origin=pathlib.Path(importlib.util.find_spec(name).origin).resolve()
        assert origin.is_relative_to(prefix),(name,str(origin))
        assert not origin.is_relative_to(source),(name,str(origin))
        assert 'site-packages' in origin.parts,(name,str(origin))
check()
tests=unittest.defaultTestLoader.discover(str(outside/'tests'))
result=unittest.TextTestRunner(verbosity=2).run(tests)
assert result.testsRun>0 and result.wasSuccessful()
check()
print(json.dumps(dict(tests=result.testsRun,installed_origins=len(names),
                     checked_before_and_after=True)))
'''
    print(call([py, '-I', '-c', suite, json.dumps(MODULES), str(ROOT)], outside))
    for args in COMMANDS:
        # Compare complete parsed reports, not a few headline numbers.
        expected = json.loads(call([sys.executable, '-m', 'robustlab'] + args, ROOT))
        for entry in [[py, '-I', '-m', 'robustlab'], [str(work / 'env/bin/robustlab')]]:
            actual = json.loads(call(entry + args, outside))
            assert actual == expected, (entry, args)
    installed_env = ENV.copy()
    installed_env['PATH'] = str(work / 'env/bin') + os.pathsep + installed_env['PATH']
    for name in ['render_audit.py', 'render_exact.py', 'render_box.py']:
        # These scripts import the installed package; their saved assets are copied.
        print(call([py, str(outside / 'examples' / name), '--check'], outside,
                   installed_env))
    print(json.dumps(dict(complete_reports=len(COMMANDS), entrypoints=2,
                          reproduced_figures=3)))
