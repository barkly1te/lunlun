export type MessageState = "done" | "streaming" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  state: MessageState;
}

export interface StreamEvent {
  type:
    | "session"
    | "status"
    | "assistant_delta"
    | "thinking_delta"
    | "final"
    | "error"
    | "done";
  session_id?: string;
  delta?: string;
  message?: string;
  phase?: string;
}
