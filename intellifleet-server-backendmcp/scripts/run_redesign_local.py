"""Isolated local UniFleet redesign: temporary DB and in-memory Redis, no .env.
Optional --configured-ai uses AI configuration already passed in the environment.
"""
import argparse
import os
from pathlib import Path
import secrets
import sys
import tempfile

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=4218)
    parser.add_argument('--frontend-port',type=int,default=5188)
    parser.add_argument('--configured-ai',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    os.chdir(tempfile.mkdtemp(prefix='unifleet-redesign-local-'))
    sys.path.insert(0,str(root))
    os.environ['SECRET_KEY']=secrets.token_hex(32)
    os.environ['DEMO_ACCESS_ENABLED']='true'
    os.environ['FRONTEND_URL']=f'http://127.0.0.1:{args.frontend_port}'
    os.environ['BACKEND_URL']=f'http://127.0.0.1:{args.port}'
    if not args.configured_ai:os.environ['AI_PROVIDER']='local-demo-no-llm'
    os.environ['FEDEX_ALERT_DELIVERY_ENABLED']='false'
    os.environ['FEDEX_SCAN_INGEST_TOKEN']=''
    os.environ['REDIS_URL']='redis://127.0.0.1:6399/15'
    import fakeredis.aioredis
    import backend.config.redis as redis_module
    redis_module.redis_client=fakeredis.aioredis.FakeRedis(decode_responses=True)
    import uvicorn
    print(f'Local redesign: http://127.0.0.1:{args.port} · temporary data and disabled email delivery',flush=True)
    uvicorn.run('main:app',host='127.0.0.1',port=args.port,workers=1,log_level='warning')

if __name__=='__main__':main()
