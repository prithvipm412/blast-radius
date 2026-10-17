import type { StreamEvent } from './types';
/** The contract sends one JSON event per data: line; chunks need not align with lines. */
export async function parseSSE(stream:ReadableStream<Uint8Array>, onEvent:(event:StreamEvent)=>void) {
 const reader=stream.getReader(); const decoder=new TextDecoder(); let buffer=''; let terminal=false;
 function line(raw:string){const value=raw.replace(/\r$/,'');if(!value.startsWith('data:'))return;const json=value.slice(5).trim();if(!json)return;const event=JSON.parse(json) as StreamEvent;onEvent(event);if(event.type==='error'||(event.type==='answer'&&event.done))terminal=true;}
 try {while(true){const {value,done}=await reader.read();buffer+=done?decoder.decode():decoder.decode(value,{stream:true});let index;while((index=buffer.indexOf('\n'))>=0){line(buffer.slice(0,index));buffer=buffer.slice(index+1);}if(done){if(buffer.trim())line(buffer);break;}}if(!terminal)throw new Error('The connection ended before the agent finished. Please retry.');} finally {reader.releaseLock();}
}
