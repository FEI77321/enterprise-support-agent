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
}