export type PulseLevel = "info" | "warn" | "heal" | "error";

export interface PulseEvent {
  id: number;
  ts: string;
  level: PulseLevel;
  kind: string;
  message: string;
}

type Listener = (e: PulseEvent) => void;

class EventBus {
  private listeners = new Set<Listener>();
  private buffer: PulseEvent[] = [];
  private nextId = 1;

  emit(level: PulseLevel, kind: string, message: string): PulseEvent {
    const event: PulseEvent = { id: this.nextId++, ts: new Date().toISOString(), level, kind, message };
    this.buffer.push(event);
    if (this.buffer.length > 500) this.buffer.shift();
    for (const l of this.listeners) l(event);
    return event;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  recent(n = 50): PulseEvent[] {
    return this.buffer.slice(-n);
  }
}

export const pulse = new EventBus();
