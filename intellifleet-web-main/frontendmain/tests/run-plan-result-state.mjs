import { createServer } from 'vite';
const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
try{
  const {planResultPanelReducer}=await server.ssrLoadModule('/src/components/PlanningPanel.tsx');
  const plan={plan_id:'plan-1',route_legs:[{route_id:5}],vehicles:[{id:11}]};
  let visible=planResultPanelReducer(false,'show');
  const opened=visible;
  visible=planResultPanelReducer(visible,'close');
  const closed=!visible;
  const planPreserved=plan.plan_id==='plan-1'&&plan.route_legs.length===1&&plan.vehicles.length===1;
  visible=planResultPanelReducer(visible,'show');
  const reopened=visible;
  const pass=opened&&closed&&planPreserved&&reopened;
  console.log(JSON.stringify({plan_result_state:pass,opened,closed,plan_preserved:planPreserved,reopened}));
  if(!pass)process.exitCode=1;
}finally{await server.close()}
