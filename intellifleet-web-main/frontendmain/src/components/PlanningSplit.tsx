import type {ReactNode} from 'react';
import {DockableWorkspace} from './DockableWorkspace';
// Preserve the existing workspace API while sharing one persistent docking system.
export function WorkspaceSplitLayout({left,right,overlay,label='planning'}:{left:ReactNode;right:ReactNode;overlay?:ReactNode;label?:string;storageKey?:string}){
 const storageKey=label==='dashboard'?'unifleet.workspace.dashboard':label==='live operations'?'unifleet.workspace.liveOperations':'unifleet.workspace.planning';
 return <DockableWorkspace primaryContent={left} mapContent={right} overlay={overlay} label={label} storageKey={storageKey}/>;
}
export const PlanningSplit=WorkspaceSplitLayout;
