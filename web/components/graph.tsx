'use client';
import ForceGraph2D, {type ForceGraphMethods, type NodeObject, type LinkObject} from 'react-force-graph-2d';
import {useEffect,useRef,useState,useMemo} from 'react';
import type {GraphNode,GraphPath,GraphEdge} from '@/lib/types';
export const colors:Record<string,string>={Service:'#60a5fa',Person:'#a78bfa',Team:'#c4b5fd',Incident:'#fb7185',Decision:'#fbbf24',Doc:'#2dd4bf',Repo:'#94a3b8',File:'#67e8f9',Commit:'#38bdf8',PR:'#34d399',Issue:'#fb923c'};
// Service (there are only ~12) and Incident/Decision (the backend already caps incidents to
// 5 and decisions are naturally few) are always legible. Everything else - Person/Team/PR/
// Commit/File/Doc/Issue/Repo - labels only on hover, or when `emphasize` marks it as the
// failing service, an owner, a top-3 expert, etc. (computed by the caller from trace results).
const ALWAYS_LABELED=new Set(['Service','Incident','Decision']);
const truncate=(s:string)=>s.length>28?s.slice(0,27)+'…':s;
type N=NodeObject<GraphNode>;type L=LinkObject<N,GraphEdge>;
const id=(value:string|number|N|undefined)=>typeof value==='object'?value.id:String(value);
type Box=[number,number,number,number];
const overlaps=(a:Box,b:Box)=>a[0]<b[2]&&a[2]>b[0]&&a[1]<b[3]&&a[3]>b[1];
export default function Network({graph,highlight,failing,depths,emphasize,busy,onSelect,resetKey}:{graph:GraphPath;highlight:GraphPath;failing:string|null;depths:Record<string,number>;emphasize:Set<string>;busy:boolean;onSelect:(n:GraphNode)=>void;resetKey:number}){
 const wrapper=useRef<HTMLDivElement>(null);const fg=useRef<ForceGraphMethods<N,L>>(undefined);const [size,setSize]=useState({width:600,height:600});const [clock,setClock]=useState(0);const start=useRef(Date.now());const [hovered,setHovered]=useState<string|null>(null);
 const positions=useRef(new Map<string,N>());const labelBoxes=useRef<Box[]>([]);
 const data=useMemo(()=>({nodes:graph.nodes.map(n=>{const node=Object.assign(positions.current.get(n.id)||{},n) as N;positions.current.set(n.id,node);return node;}),links:graph.edges.map(e=>({...e}))}),[graph]);
 const selected=useMemo(()=>new Set(highlight.nodes.map(n=>n.id)),[highlight]);const links=useMemo(()=>new Set(highlight.edges.map(e=>`${e.source}|${e.type}|${e.target}`)),[highlight]);
 // PageRank-sized services: critical_services() stores a `criticality` score on Service
 // nodes (absent until it's run at least once). Scale relative to whatever's on screen now,
 // since the raw PageRank values are tiny and only meaningful by comparison.
 const criticalityRange=useMemo(()=>{
  const values=graph.nodes.filter(n=>n.label==='Service'&&typeof n.criticality==='number').map(n=>n.criticality as number);
  return values.length?{min:Math.min(...values),max:Math.max(...values)}:null;
 },[graph]);
 const radiusFor=(node:N)=>{
  if(node.label!=='Service')return 5;
  if(!criticalityRange||typeof node.criticality!=='number')return 7;
  const {min,max}=criticalityRange;
  const t=max>min?(node.criticality-min)/(max-min):0.5;
  return 6+t*6;
 };
 useEffect(()=>{const observer=new ResizeObserver(([entry])=>setSize({width:entry.contentRect.width,height:entry.contentRect.height}));if(wrapper.current)observer.observe(wrapper.current);return()=>observer.disconnect();},[]);
 useEffect(()=>{start.current=Date.now();},[depths]);
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),45);return()=>clearInterval(timer);},[]);
 // While an investigation is streaming, node-by-node tool_result additions would otherwise
 // re-trigger zoomToFit several times in a row (once per tool call). Only fit once busy
 // goes false - on initial load, node-click exploration, the "fit to view" button
 // (resetKey), and once after the investigation finishes.
 useEffect(()=>{fg.current?.d3Force('charge')?.strength(-220);if(busy)return;const timer=setTimeout(()=>fg.current?.zoomToFit(650,80),500);return()=>clearTimeout(timer);},[data,resetKey,size.width,busy]);
 const activeLink=(l:L)=>links.has(`${id(l.source)}|${l.type}|${id(l.target)}`);
 return <div ref={wrapper} className="network-canvas" aria-label="Interactive dependency graph. Select a node to inspect its properties."><ForceGraph2D ref={fg} width={size.width} height={size.height} graphData={data} backgroundColor="transparent" nodeLabel={()=>''} cooldownTicks={100} enableNodeDrag onNodeClick={n=>onSelect(n)} onNodeHover={n=>setHovered(n?n.id as string:null)} onRenderFramePre={()=>{labelBoxes.current=[];}} linkColor={l=>activeLink(l)?'#60a5fa':selected.size?'#2a4571':'#3d6090'} linkWidth={l=>activeLink(l)?1.8:0.9} linkLineDash={l=>l.synthetic?[3,4]:null} linkDirectionalArrowLength={l=>l.type==='DEPENDS_ON'?5:0} linkDirectionalArrowRelPos={0.8} linkDirectionalParticles={l=>activeLink(l)?3:0} linkDirectionalParticleWidth={2} linkDirectionalParticleSpeed={0.006} nodeCanvasObject={(node,ctx,scale)=>{
 const x=node.x||0,y=node.y||0;const isRoot=node.id===failing;const active=selected.has(node.id);const color=isRoot?'#ef4444':colors[node.label]||'#94a3b8';const radius=radiusFor(node);const dim=selected.size>0&&!active&&!isRoot;ctx.globalAlpha=dim?0.25:1;
 const hop=depths[node.id];const elapsed=(clock-start.current)/1000;
 if(isRoot||active){ctx.beginPath();ctx.arc(x,y,radius+5,0,2*Math.PI);ctx.fillStyle=color+'18';ctx.fill();}
 if(isRoot||(hop!==undefined&&elapsed>hop*0.5&&elapsed<hop*0.5+3)){const phase=((clock/1400-(hop||0)*0.25)%1+1)%1;ctx.beginPath();ctx.arc(x,y,radius+phase*23,0,2*Math.PI);ctx.strokeStyle=color;ctx.globalAlpha=(1-phase)*0.65;ctx.lineWidth=1/scale;ctx.stroke();ctx.globalAlpha=1;}
 ctx.beginPath();ctx.arc(x,y,radius,0,2*Math.PI);ctx.fillStyle=color;ctx.shadowColor=color;ctx.shadowBlur=active||isRoot?12:0;ctx.fill();ctx.shadowBlur=0;
 if(node.synthetic){ctx.setLineDash([2,2]);ctx.strokeStyle='#dbeafe';ctx.lineWidth=1/scale;ctx.stroke();ctx.setLineDash([]);}
 const wants=ALWAYS_LABELED.has(node.label)||isRoot||emphasize.has(node.id)||node.id===hovered;
 if(wants){
  const text=truncate(node.name);const fontSize=11/scale;ctx.font=`${fontSize}px Inter, sans-serif`;
  const w=ctx.measureText(text).width;const top=y+radius+6;const box:Box=[x-w/2-1,top-1,x+w/2+1,top+fontSize+1];
  if(!labelBoxes.current.some(b=>overlaps(b,box))){
   labelBoxes.current.push(box);
   ctx.textAlign='center';ctx.textBaseline='top';ctx.fillStyle=dim?'#50627e':'#c7d6ee';ctx.fillText(text,x,top);
  }
 }
 ctx.globalAlpha=1;
 }} nodePointerAreaPaint={(node,color,ctx)=>{ctx.fillStyle=color;ctx.beginPath();ctx.arc(node.x||0,node.y||0,14,0,Math.PI*2);ctx.fill();}} /></div>;
}
