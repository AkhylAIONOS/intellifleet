"""Launch root FastAPI against a NEW temporary database, with local demo auth.

Does not load repository .env files, connect to Azure, or use the existing DB.
Run with the project's existing virtualenv Python. Bind loopback only.
"""
import os
from pathlib import Path
import secrets
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    runtime = tempfile.mkdtemp(prefix='unifleet-fedex-local-')
    os.chdir(runtime)
    sys.path.insert(0, str(root))
    # Fresh, process-local signing material; never printed or persisted.
    os.environ['SECRET_KEY'] = secrets.token_hex(32)
    os.environ['DEMO_ACCESS_ENABLED'] = 'true'
    os.environ['FRONTEND_URL'] = 'http://127.0.0.1:5178'
    os.environ['BACKEND_URL'] = 'http://127.0.0.1:4208'
    os.environ['AI_PROVIDER'] = 'local-demo-no-llm'
    # Chat is outside this offline launcher; do not use the production Redis URL.
    os.environ['REDIS_URL'] = 'redis://127.0.0.1:6399/15'
    print(f'Isolated local demo data: {runtime}', flush=True)
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=4208, workers=1, log_level='warning')


if __name__ == '__main__':
    main()
