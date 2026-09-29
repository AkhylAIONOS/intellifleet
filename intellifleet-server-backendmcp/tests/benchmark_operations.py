"""Isolated V2 import + unified batch benchmark; never modifies the user's DB."""
import asyncio
import io
import json
import os
import sqlite3
import tempfile
import time
from starlette.datastructures import UploadFile
from backend.operations.data import DATA_DIR
from backend.operations import service, routes
from backend.fedex.telemetry import Runtime
from backend.database.database import init_db
from backend.planning.database import migrate_planning_schema
from backend.routes.upload.network_upload import upload_network


def main():
    previous=os.getcwd()
    with tempfile.TemporaryDirectory(prefix='unifleet-operations-benchmark-') as directory:
        os.chdir(directory)
        try:
            init_db();migrate_planning_schema()
            with sqlite3.connect('users.db') as c:
                c.execute("INSERT INTO users(id,first_name,last_name,email,password,verified) VALUES(1,'Test','User','benchmark@example.invalid','x',1)")
            asyncio.run(upload_network(*[UploadFile(io.BytesIO((DATA_DIR/f'{name}.csv').read_bytes()),filename=f'{name}.csv') for name in ('warehouse','vehicle','routes')],{'user_id':1}))
            for count in (10,50,100):
                now=[0.0];runtime=Runtime(clock=lambda:now[0]);service.runtime=runtime
                started=time.perf_counter();service.start_demo(1,count,42);creation=(time.perf_counter()-started)*1000
                started=time.perf_counter()
                for _ in range(40):now[0]+=.25;runtime.tick()
                elapsed=time.perf_counter()-started
                started=time.perf_counter();payload=service.movements(1);batch=(time.perf_counter()-started)*1000
                print(json.dumps({'entities':count,'create_ms':round(creation,2),'snapshots_per_second':round(runtime.updates/elapsed),
                    'batch_snapshot_ms':round(batch,2),'payload_bytes':len(json.dumps(payload)),
                    'errors':runtime.errors,'dropped_updates':count*40-runtime.updates,
                    'scope':'Python V2 loaded-network runtime; excludes browser rendering and network transport'}))
        finally:os.chdir(previous)

if __name__=='__main__':main()
