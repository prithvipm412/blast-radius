'use client';
import ForceGraph2D, {type ForceGraphMethods, type NodeObject, type LinkObject} from 'react-force-graph-2d';
import {useEffect,useRef,useState,useMemo} from 'react';
import type {GraphNode,GraphPath,GraphEdge} from '@/lib/types';
export const colors:Record<string,string>={Service:'#60a5fa',Person:'#a78bfa',Team:'#c4b5fd',Incident:'#fb7185',Decision:'#fbbf24',Doc:'#2dd4bf',Repo:'#94a3b8',File:'#67e8f9',Commit:'#38bdf8',PR:'#34d399',Issue:'#fb923c'};
// Labels for these are always legible on the overview; everything else (Person/PR/Commit/
// File/Doc/Issue/Repo) only labels on hover or when part of the highlighted investigation
// path, to keep a few hundred nodes from becoming an unreadable wall of text.
const ALWAYS_LABELED=new Set(['Service','Team','Incident','Decision']);
const truncate=(s:string)=>s.length>28?s.slice(0,27)+'…':s;
type N=NodeObject<GraphNode>;type L=LinkObject<N,GraphEdge>;
const id=(value:string|number|N|undefined)=>typeof value==='object'?value.id:String(value);
export default function Network({graph,highlight,failing,depths,onSelect,resetKey}:{graph:GraphPath;highlight:GraphPath;failing:string|null;depths:Record<string,number>;onSelect:(n:GraphNode)=>void;resetKey:number}){
 const wrapper=useRef<HTMLDivElement>(null);const fg=useRef<ForceGraphMethods<N,L>>(undefined);const [size,setSize]=useState({width:600,height:600});const [clock,setClock]=useState(0);const start=useRef(Date.now());const [hovered,setHovered]=useState<string|null>(null);
 const positions=useRef(new Map<string,N>());
 const data=useMemo(()=>({nodes:graph.nodes.map(n=>{const node=Object.assign(positions.current.get(n.id)||{},n) as N;positions.current.set(n.id,node);return node;}),links:graph.edges.map(e=>({...e}))}),[graph]);
 const selected=useMemo(()=>new Set(highlight.nodes.map(n=>n.id)),[highlight]);const links=useMemo(()=>new Set(highlight.edges.map(e=>`${e.source}|${e.type}|${e.target}`)),[highlight]);
 useEffect(()=>{const observer=new ResizeObserver(([entry])=>setSize({width:entry.contentRect.width,height:entry.contentRect.height}));if(wrapper.current)observer.observe(wrapper.current);return()=>observer.disconnect();},[]);
 useEffect(()=>{start.current=Date.now();},[depths]);
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),45);return()=>clearInterval(timer);},[]);
 useEffect(()=>{fg.current?.d3Force('charge')?.strength(-220);const timer=setTimeout(()=>fg.current?.zoomToFit(650,75),500);return()=>clearTimeout(timer);},[data,resetKey,size.width]);
 const activeLink=(l:L)=>links.has(`${id(l.source)}|${l.type}|${id(l.target)}`);
 return <div ref={wrapper} className="network-canvas" aria-label="Interactive dependency graph. Select a node to inspect its properties."><ForceGraph2D ref={fg} width={size.width} height={size.height} graphData={data} backgroundColor="transparent" nodeLabel={()=>''} cooldownTicks={100} enableNodeDrag onNodeClick={n=>onSelect(n)} onNodeHover={n=>setHovered(n?n.id as string:null)} linkColor={l=>activeLink(l)?'#60a5fa':selected.size?'#1a2b46':'#294361'} linkWidth={l=>activeLink(l)?1.8:0.7} linkLineDash={l=>l.synthetic?[3,4]:null} linkDirectionalArrowLength={l=>l.type==='DEPENDS_ON'?5:0} linkDirectionalArrowRelPos={0.8} linkDirectionalParticles={l=>activeLink(l)?3:0} linkDirectionalParticleWidth={2} linkDirectionalParticleSpeed={0.006} nodeCanvasObject={(node,ctx,scale)=>{
 const x=node.x||0,y=node.y||0;const isRoot=node.id===failing;const active=selected.has(node.id);const color=isRoot?'#ef4444':colors[node.label]||'#94a3b8';const radius=node.label==='Service'?7:5;const dim=selected.size>0&&!active&&!isRoot;ctx.globalAlpha=dim?0.25:1;
 const hop=depths[node.id];const elapsed=(clock-start.current)/1000;
 if(isRoot||active){ctx.beginPath();ctx.arc(x,y,radius+5,0,2*Math.PI);ctx.fillStyle=color+'18';ctx.fill();}
 if(isRoot||(hop!==undefined&&elapsed>hop*0.5&&elapsed<hop*0.5+3)){const phase=((clock/1400-(hop||0)*0.25)%1+1)%1;ctx.beginPath();ctx.arc(x,y,radius+phase*23,0,2*Math.PI);ctx.strokeStyle=color;ctx.globalAlpha=(1-phase)*0.65;ctx.lineWidth=1/scale;ctx.stroke();ctx.globalAlpha=1;}
 ctx.beginPath();ctx.arc(x,y,radius,0,2*Math.PI);ctx.fillStyle=color;ctx.shadowColor=color;ctx.shadowBlur=active||isRoot?12:0;ctx.fill();ctx.shadowBlur=0;
 if(node.synthetic){ctx.setLineDash([2,2]);ctx.strokeStyle='#dbeafe';ctx.lineWidth=1/scale;ctx.stroke();ctx.setLineDash([]);}
 const showLabel=ALWAYS_LABELED.has(node.label)||active||isRoot||node.id===hovered;
 if(showLabel){ctx.font=`${11/scale}px Inter, sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillStyle=dim?'#50627e':'#c7d6ee';ctx.fillText(truncate(node.name),x,y+radius+6);}
 ctx.globalAlpha=1;
 }} nodePointerAreaPaint={(node,color,ctx)=>{ctx.fillStyle=color;ctx.beginPath();ctx.arc(node.x||0,node.y||0,14,0,Math.PI*2);ctx.fill();}} /></div>;
}
