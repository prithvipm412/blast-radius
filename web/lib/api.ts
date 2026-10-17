import {mockGraph,mockStats,mockStream} from './mock';
import {parseSSE} from './sse';
import type {GraphPath,Stats,StreamEvent,AskRequest,AlertRequest,SyncResponse} from './types';
export const MOCK=process.env.NEXT_PUBLIC_MOCK==='1';
const BASE=(process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000').replace(/\/$/,'');
async function check(response:Response){if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{}throw new Error(typeof detail==='string'?detail:`API request failed (${response.status})`);}return response;}
export async function getGraph(signal?:AbortSignal):Promise<GraphPath>{return MOCK?structuredClone(mockGraph):(await check(await fetch(`${BASE}/api/graph`,{signal}))).json();}
export async function getStats(signal?:AbortSignal):Promise<Stats>{return MOCK?mockStats:(await check(await fetch(`${BASE}/api/stats`,{signal}))).json();}
export async function syncGraph():Promise<SyncResponse>{if(MOCK)return {status:'ok',started_at:new Date().toISOString(),finished_at:new Date().toISOString()};return (await check(await fetch(`${BASE}/api/sync`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}))).json();}
export async function stream(endpoint:'ask'|'alert',body:AskRequest|AlertRequest,onEvent:(e:StreamEvent)=>void,signal:AbortSignal){if(MOCK)return mockStream(endpoint,body,onEvent,signal);const response=await check(await fetch(`${BASE}/api/${endpoint}`,{method:'POST',headers:{'Content-Type':'application/json',Accept:'text/event-stream'},body:JSON.stringify(body),signal}));if(!response.body)throw new Error('The API returned an empty stream.');await parseSSE(response.body,onEvent);}
