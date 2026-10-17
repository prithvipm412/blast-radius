export type NodeLabel = 'Service' | 'Person' | 'Team' | 'Repo' | 'File' | 'Commit' | 'PR' | 'Issue' | 'Incident' | 'Decision' | 'Doc';
export type EdgeType = 'DEPENDS_ON' | 'OWNS' | 'MEMBER_OF' | 'AUTHORED' | 'TOUCHED' | 'CONTAINS' | 'CAUSED' | 'AFFECTED' | 'RESOLVED_BY' | 'DECIDED' | 'CITES' | 'MENTIONS';
export interface GraphNode { id: string; label: NodeLabel; name: string; synthetic: boolean; source_url?: string; [property: string]: unknown }
export interface GraphEdge { source: string; target: string; type: EdgeType; synthetic: boolean; source_url?: string | null; [property: string]: unknown }
export interface GraphPath { nodes: GraphNode[]; edges: GraphEdge[] }
export interface ToolData {
 search_entities: { matches: GraphNode[] };
 blast_radius: { root: string; affected: {id:string;name:string;depth:number;synthetic:boolean}[] };
 failure_path: { exists:boolean;hops:number|null;path_ids:string[] };
 find_owners: { team:{id:string;name:string};members:{id:string;name:string;github_login:string|null}[] };
 find_experts: { experts:{id:string;name:string;pr_count:number;last_touched:string}[] };
 similar_incidents: { incidents:{id:string;name:string;severity:string;started_at:string;relation:string}[] };
 trace_decision: { decisions:{id:string;name:string;status:string;decided_at:string;cites_prs:string[]}[] };
 critical_services: { ranked:{id:string;name:string;score:number}[] };
 single_points_of_failure: { ranked:{id:string;name:string;score:number}[] };
 team_clusters: { clusters:{cluster_id:number;services:string[];dominant_team:string}[] };
 create_incident_issue: { issue_id:string;dry_run:boolean;url:string;incident_id:string;title:string };
}
export type ToolName = keyof ToolData;
export interface ToolResult<T extends ToolName = ToolName> { data:ToolData[T];cypher:string;params:Record<string,unknown>;path:GraphPath }
export type StreamEvent = {type:'tool_call';tool:ToolName;args:Record<string,unknown>} | { [T in ToolName]: {type:'tool_result';tool:T;result:ToolResult<T>} }[ToolName] | {type:'answer';text:string;done:boolean} | {type:'error';message:string};
export interface Stats { nodes_by_label:Record<string,number>;edges_by_type:Record<string,number>;synthetic_node_count:number;real_node_count:number;last_synced_at:string }
export interface AskRequest {question:string;mode?:'graph'|'rag'}
export interface AlertRequest {service:string}
export interface SyncResponse {status:'ok';started_at:string;finished_at:string}
export interface TraceStep {tool:ToolName;args:Record<string,unknown>;started:number;duration?:number;result?:ToolResult}
