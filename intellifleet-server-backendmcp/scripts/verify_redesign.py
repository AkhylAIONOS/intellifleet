"""Run backend regressions in a temporary DB directory without repository .env files."""
import os,secrets,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.chdir(tempfile.mkdtemp(prefix='unifleet-redesign-tests-'))
os.environ['SECRET_KEY']=secrets.token_hex(32)
os.environ['DEMO_ACCESS_ENABLED']='true'
os.environ['AI_PROVIDER']='local-demo-no-llm'
os.environ['REDIS_URL']='redis://127.0.0.1:6399/15'
sys.path.insert(0,str(root))
sys.dont_write_bytecode=True
import pytest
args=sys.argv[1:] or ['tests']
sys.exit(pytest.main(['-p','no:cacheprovider',*[str(root/a) for a in args]]))
