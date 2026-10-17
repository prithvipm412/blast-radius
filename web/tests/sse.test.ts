import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseSSE} from '../lib/sse';
import {mockStream} from '../lib/mock';
import type {StreamEvent} from '../lib/types';
function bytes(text:string,size=1){const data=new TextEncoder().encode(text);return new ReadableStream<Uint8Array>({start(c){for(let i=0;i<data.length;i+=size)c.enqueue(data.slice(i,i+size));c.close();}});}
test('POST SSE handles split UTF-8, CRLF, comments, partial and final answers',async()=>{const events:StreamEvent[]=[];await parseSSE(bytes(': keepalive\r\ndata: {"type":"answer","text":"Hi →","done":false}\r\n\r\ndata: {"type":"answer","text":"Hi → there","done":true}'),e=>events.push(e));assert.equal(events.length,2);assert.equal(events[1].type,'answer');if(events[1].type==='answer')assert.equal(events[1].text,'Hi → there');});
test('terminal stream errors are delivered',async()=>{const events:StreamEvent[]=[];await parseSSE(bytes('data: {"type":"error","message":"unknown service"}\n'),e=>events.push(e));assert.equal(events[0].type,'error');});
test('truncated streams fail rather than silently succeeding',async()=>{await assert.rejects(()=>parseSSE(bytes('data: {"type":"answer","text":"partial","done":false}\n'),()=>{}),/before the agent finished/);});
test('malformed JSON fails',async()=>{await assert.rejects(()=>parseSSE(bytes('data: nope\n'),()=>{}));});
test('mock cart alert streams all tools, incoming blast radius, draft and final answer',async()=>{const events:StreamEvent[]=[];await mockStream('alert',{service:'cartservice'},e=>events.push(e),new AbortController().signal);const calls=events.filter(e=>e.type==='tool_call');assert.equal(calls.length,6);const results=events.filter(e=>e.type==='tool_result');assert.equal(results.length,6);const blast=results.find(e=>e.tool==='blast_radius');assert.deepEqual(blast?.result.data.affected.map(n=>n.name).sort(),['checkoutservice','frontend']);const issue=results.find(e=>e.tool==='create_incident_issue');assert.equal(issue?.result.data.dry_run,true);assert.equal(issue?.result.data.url,'draft');const final=events.at(-1);assert.equal(final?.type,'answer');if(final?.type==='answer')assert.equal(final.done,true);});
