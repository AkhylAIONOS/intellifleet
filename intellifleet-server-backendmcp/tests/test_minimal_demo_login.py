import sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.routes import auth
from backend.database.database import init_db


def test_demo_identity_session_and_private_list(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);init_db()
    with sqlite3.connect('users.db') as c:
        c.execute("INSERT INTO users(first_name,last_name,email,password) VALUES('Legacy','User','legacy@example.com','existing-hash')")
    monkeypatch.setattr(auth.settings,'DEMO_ACCESS_ENABLED',True)
    monkeypatch.setattr(auth.settings,'UNIFLEET_ADMIN_EMAILS',' ADMIN@EXAMPLE.COM , other@example.com ')
    app=FastAPI();app.include_router(auth.router)
    client=TestClient(app)
    assert client.post('/auth/demo-access').status_code==422
    assert client.post('/auth/demo-access',json={'email':'invalid'}).status_code==422
    assert client.post('/auth/demo-access',json={'email':'new@example.com'}).status_code==400
    first=client.post('/auth/demo-access',json={'name':'Test User','email':' TEST@EXAMPLE.COM '}).json()['data']
    assert first['user']['name']=='Test User' and first['user']['email']=='test@example.com'
    token=first['token'];headers={'Authorization':'Bearer '+token}
    assert client.get('/auth/users').status_code==401
    assert client.get('/auth/users',headers=headers).status_code==403
    repeated=client.post('/auth/demo-access',json={'email':'test@example.com','name':'Wrong replacement'}).json()['data']
    assert repeated['user']==first['user']
    second=client.post('/auth/demo-access',json={'email':'second@example.com','name':'Second User'}).json()['data']
    assert second['user']['id']!=first['user']['id']
    with sqlite3.connect('users.db') as c:
        row=c.execute('SELECT first_login_at,last_login_at,login_count FROM users WHERE email=?',('test@example.com',)).fetchone()
        assert row[0] and row[1]>row[0] and row[2]==2
        assert c.execute('SELECT count(*) FROM users WHERE lower(email)=?',('test@example.com',)).fetchone()[0]==1
        assert c.execute('SELECT password FROM users WHERE email=?',('legacy@example.com',)).fetchone()[0]=='existing-hash'
    admin=client.post('/auth/demo-access',json={'email':'admin@example.com','name':'Admin'}).json()['data']
    response=client.get('/auth/users',headers={'Authorization':'Bearer '+admin['token']})
    assert response.status_code==200
    users=response.json()['users']
    assert users[0]['email']=='admin@example.com'
    assert {'test@example.com','second@example.com'}<={u['email'] for u in users}
    assert all(set(u)=={'name','email','first_login_at','last_login_at','login_count'} for u in users)
    # Admin authorization comes from the database identity, not a claimed token email.
    forged_claim=auth.create_access_token({'user_id':first['user']['id'],'email':'admin@example.com'})
    assert client.get('/auth/users',headers={'Authorization':'Bearer '+forged_claim}).status_code==403
    monkeypatch.setattr(auth.settings,'UNIFLEET_ADMIN_EMAILS','')
    assert client.get('/auth/users',headers={'Authorization':'Bearer '+admin['token']}).status_code==403
    monkeypatch.setattr(auth.settings,'DEMO_ACCESS_ENABLED',False)
    assert client.post('/auth/demo-access',json={'email':'test@example.com'}).status_code==403
