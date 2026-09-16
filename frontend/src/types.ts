// 模块职责：定义前端调用企业支持 Agent API 时使用的响应数据类型。

export type ChatResponseType =
  | "answer"
  | "ticket_created"
  | "ticket_status"
  | "clarify";

export type TicketStatus =
  | "OPEN"
  | "IN_PROGRESS"
  | "CLOSED";

export type TicketPriority =
  | "LOW"
  | "MEDIUM"
  | "HIGH";

export interface Source {
  file: string;
  snippet: string;
  score: number;
  chunk_id: string | null;
}

export interface Ticket {
  ticket_id: string;
  title: string;
  description: string;
  category: string;
  priority: TicketPriority;
  status: TicketStatus;
  assignee: string;
  created_at: string;
}

export interface ChatResponse {
  request_id: string;
  type: ChatResponseType;
  answer: string | null;
  sources: Source[];
  ticket: Ticket | null;
  workflow_steps: string[];
  harness_trace?: Array<{ tool_name: string; status: string; risk_level: string; elapsed_ms?: number; authorization_reason?: string }>;
  trace_id?: string | null;
  safety?: { action?: string; risk_level?: string; reason?: string };
  query_rewrite?: { triggered?: boolean; effective_query?: string; reason?: string };
  memory?: { retrieved_count?: number; write?: { action?: string; reason?: string } };
  context?: {
    compression_triggered?: boolean;
    total_budget_tokens?: number;
    recent_turn_count?: number;
    summary_source_turns?: number;
    estimated_reduction_ratio?: number;
    evidence_dropped?: number;
  };
  prompt?: { version?: string; content_hash?: string; channel?: string; rollout_percent?: number };
  timing?: Record<string, number>;
}

export type BadCaseStatus = 'open' | 'triaged' | 'regression_added' | 'resolved'

export type BadCaseCategory = 'retrieval' | 'rewrite' | 'safety' | 'tool' | 'authorization' | 'memory' | 'response' | 'context' | 'prompt' | 'performance'

export interface BadCase {
  bad_case_id: string
  request_id: string
  category: BadCaseCategory
  severity: 'low' | 'medium' | 'high' | 'critical'
  expected_behavior: string
  actual_behavior: string
  status: BadCaseStatus
  reporter_id: string
  regression_case_id: string | null
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export interface AgentOpsMetrics {
  trace_runs: number
  tool_calls: number
  tool_failure_rate: number
  prompt_injection_block_rate: number
  query_rewrite_trigger_rate: number
  context_compression_trigger_rate: number
  context_estimated_reduction_ratio: number
  request_phase_elapsed_ms?: Record<string, { p50: number | null; p95: number | null }>
  bad_cases: Partial<Record<BadCaseStatus, number>>
  open_bad_case_count: number
}
