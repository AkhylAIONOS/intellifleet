"""Isolated local QA only: temporary SQLite + in-memory Redis, normal auth/LLM."""
import os
from pathlib import Path
import runpy
import sys
import tempfile
from dotenv import load_dotenv

root = Path(__file__).resolve().parents[2] / 'intellifleet-server-backendmcp'
sys.path.insert(0, str(root))
load_dotenv(root / '.env')
os.environ['DEMO_ACCESS_ENABLED'] = 'true'
os.environ['FRONTEND_URL'] = 'http://127.0.0.1:5189'
os.chdir(tempfile.mkdtemp(prefix='unifleet-readiness-'))
from fakeredis.aioredis import FakeRedis
import backend.config.redis as cache
cache.redis_client = FakeRedis(decode_responses=True)
app = runpy.run_path(str(root / 'main.py'))['app']
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=4219, log_level='warning', access_log=False)
