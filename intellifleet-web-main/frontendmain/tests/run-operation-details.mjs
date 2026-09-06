import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
try {
  const {OperationDetails}=await server.ssrLoadModule('/src/components/OperationDetails.tsx');
  const html=renderToStaticMarkup(React.createElement(OperationDetails,{result:{
    allocation:[{warehouse:'Bengaluru',allocation:5,weight_kg:100,plan:{operational_cost:1234,duration_hours:4}}],
    affected_shipments:[{shipment_id:'NEXT',before_assignment:'T1',after_assignment:'T2'}],
    candidates:[{hub:'Candidate',incremental_cost:null,known_cost_subtotal:10}],
  }}));
  for(const text of ['Warehouse allocations','Bengaluru','1,234','Affected shipments','NEXT','Candidate facilities','Unavailable'])assert.ok(html.includes(text),text);
  const malformed=renderToStaticMarkup(React.createElement(OperationDetails,{result:{allocation:[null,5,{},[]],candidates:'bad'}}));
  assert.ok(malformed.includes('Unavailable'));
  const {useAppStore}=await server.ssrLoadModule('/src/store/appStore.ts');
  useAppStore.getState().applyPlanningMapPlan({affected_shipments:[{shipment_id:'NEXT'}]});
  assert.equal(useAppStore.getState().operationResult.affected_shipments[0].shipment_id,'NEXT');
  useAppStore.getState().clearPlanningVisuals();
  assert.equal(useAppStore.getState().operationResult,null);
  console.log('PASS: structured operation tables, unknown costs, malformed rows and New Chat clearing');
} finally {await server.close();}
