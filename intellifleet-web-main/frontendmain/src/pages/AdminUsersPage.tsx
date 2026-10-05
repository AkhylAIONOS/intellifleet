import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {authApi} from '../api/auth';

export function AdminUsersPage(){
 const [users,setUsers]=useState<Awaited<ReturnType<typeof authApi.users>>['users']>([]);
 const [error,setError]=useState(''),[loading,setLoading]=useState(true);
 useEffect(()=>{let active=true;authApi.users().then(data=>{if(active)setUsers(data.users);}).catch(err=>{if(active)setError(err.response?.status===403?'Unauthorized':'User list is temporarily unavailable.');}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[]);
 return <main className="dashboard-container"><h1>UniFleet users</h1><Link to="/dashboard">Dashboard</Link>
  {loading?<p>Loading users…</p>:error?<p role="alert">{error}</p>:<table><thead><tr>{['Name','Email','First Login','Last Login','Login Count'].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{users.map(user=><tr key={user.email}><td>{user.name}</td><td>{user.email}</td><td>{user.first_login_at}</td><td>{user.last_login_at}</td><td>{user.login_count}</td></tr>)}</tbody></table>}
 </main>;
}
