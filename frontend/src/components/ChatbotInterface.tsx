import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  Bot,
  History,
  LockKeyhole,
  Maximize2,
  MessageCircle,
  Minimize2,
  Plus,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  User,
  X,
} from 'lucide-react';
import { askAdvisor } from '../api/services';

type ChartPoint = {
  label?: string;
  category?: string;
  value?: number;
  amount?: number;
};

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  chart?: ChartPoint[];
};

type AdvisorResponse = {
  answer: string;
  chart?: ChartPoint[];
};

type ChatSession = {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
};

const starterMessages: ChatMessage[] = [
  {
    id: 'welcome',
    role: 'assistant',
    content:
      'Chào cậu, tớ là Fin. Cứ hỏi tớ chuyện tiền nong như hỏi một người bạn biết đọc ngân sách nhé. Muốn thử luôn thì hỏi: **Tôi có thể mua đôi giày 2 triệu hôm nay không?**',
  },
];

const quickPrompts = [
  'Dạo này tôi thấy mình nghèo đi nhanh quá',
  'Tôi có thể mua đôi giày 2 triệu hôm nay không?',
  'Tháng này khoản nào đang làm tôi hao tiền nhất?',
];
const CHAT_STORAGE_KEY = 'spectra-fin-chat-history';
const CHAT_SESSIONS_STORAGE_KEY = 'spectra-fin-chat-sessions';
const ACTIVE_SESSION_STORAGE_KEY = 'spectra-fin-active-session';
const MAX_STORED_MESSAGES = 40;
const MAX_STORED_SESSIONS = 12;

const createSession = (): ChatSession => {
  const now = Date.now();
  return {
    id: crypto.randomUUID(),
    title: 'Cuộc trò chuyện mới',
    messages: starterMessages,
    createdAt: now,
    updatedAt: now,
  };
};

const hasUserContent = (session: ChatSession) =>
  session.messages.some((message) => message.role === 'user' && message.content.trim());

const titleFromContent = (content: string) => {
  const cleaned = content
    .replace(/\*\*/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned) return 'Cuộc trò chuyện mới';
  return cleaned.length > 46 ? `${cleaned.slice(0, 43)}...` : cleaned;
};

const titleForMessages = (messages: ChatMessage[]) => {
  const firstUserMessage = messages.find((message) => message.role === 'user');
  return firstUserMessage ? titleFromContent(firstUserMessage.content) : 'Cuộc trò chuyện mới';
};

function loadStoredMessages(): ChatMessage[] {
  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return starterMessages;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) return starterMessages;
    return parsed
      .filter((message) => (
        message &&
        (message.role === 'user' || message.role === 'assistant') &&
        typeof message.content === 'string'
      ))
      .slice(-MAX_STORED_MESSAGES);
  } catch {
    return starterMessages;
  }
}

function loadStoredSessions(): { sessions: ChatSession[]; activeSessionId: string } {
  try {
    const raw = window.localStorage.getItem(CHAT_SESSIONS_STORAGE_KEY);
    const activeId = window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY) || '';
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        const sessions = parsed
          .filter((session) => session && typeof session.id === 'string' && Array.isArray(session.messages))
          .map((session) => ({
            id: session.id,
            title: session.title || titleForMessages(session.messages),
            messages: session.messages.slice(-MAX_STORED_MESSAGES),
            createdAt: Number(session.createdAt || Date.now()),
            updatedAt: Number(session.updatedAt || Date.now()),
          }))
          .sort((a, b) => b.updatedAt - a.updatedAt)
          .slice(0, MAX_STORED_SESSIONS);
        if (sessions.length > 0) {
          return {
            sessions,
            activeSessionId: sessions.some((session) => session.id === activeId) ? activeId : sessions[0].id,
          };
        }
      }
    }

    const migratedMessages = loadStoredMessages();
    if (migratedMessages.some((message) => message.role === 'user')) {
      const now = Date.now();
      const migratedSession = {
        id: crypto.randomUUID(),
        title: titleForMessages(migratedMessages),
        messages: migratedMessages,
        createdAt: now,
        updatedAt: now,
      };
      return { sessions: [migratedSession], activeSessionId: migratedSession.id };
    }
  } catch {}

  const firstSession = createSession();
  return { sessions: [firstSession], activeSessionId: firstSession.id };
}

const cn = (...classes: Array<string | false | null | undefined>) =>
  classes.filter(Boolean).join(' ');

function Button({
  children,
  className,
  variant = 'default',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'secondary' | 'ghost';
}) {
  return (
    <button
      className={cn(
        'advisor-btn',
        variant === 'secondary' && 'advisor-btn-secondary',
        variant === 'ghost' && 'advisor-btn-ghost',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function Card({ children, className }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('advisor-card', className)}>{children}</div>;
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

function Markdown({ content }: { content: string }) {
  return (
    <div className="advisor-markdown">
      {content.split(/\n{2,}/).map((block, blockIndex) => {
        const trimmed = block.trim();
        if (!trimmed) return null;

        if (/^\[[^\]]+\]$/.test(trimmed)) {
          return <h3 key={blockIndex}>{trimmed}</h3>;
        }

        if (trimmed.includes('\n- ')) {
          const [lead, ...items] = trimmed.split(/\n-\s+/);
          return (
            <div key={blockIndex}>
              {lead && <p>{renderInlineMarkdown(lead)}</p>}
              <ul>
                {items.map((item, itemIndex) => (
                  <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
                ))}
              </ul>
            </div>
          );
        }

        return <p key={blockIndex}>{renderInlineMarkdown(trimmed)}</p>;
      })}
    </div>
  );
}

function MiniChart({ data }: { data: ChartPoint[] }) {
  const normalized = data
    .map((item) => ({
      label: item.label || item.category || 'Khác',
      value: Number(item.value ?? item.amount ?? 0),
    }))
    .filter((item) => item.value > 0);
  const max = Math.max(...normalized.map((item) => item.value), 1);

  if (normalized.length === 0) return null;

  return (
    <div className="advisor-mini-chart" aria-label="Mini spending chart">
      <div className="advisor-mini-chart-title">
        <BarChart3 size={15} />
        Nhóm chi nổi bật
      </div>
      <div className="advisor-bars">
        {normalized.slice(0, 5).map((item) => {
          const pct = Math.max((item.value / max) * 100, 4);
          return (
            <div className="advisor-bar-row" key={item.label}>
              <span className="advisor-bar-label">{item.label}</span>
              <span className="advisor-bar-track">
                <span className="advisor-bar-fill" style={{ width: `${pct}%` }} />
              </span>
              <span className="advisor-bar-value">
                {new Intl.NumberFormat('vi-VN', { notation: 'compact' }).format(item.value)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="advisor-message advisor-message-assistant">
      <div className="advisor-avatar advisor-avatar-ai">
        <Bot size={17} />
      </div>
      <div className="advisor-message-body">
        <div className="advisor-message-label">
          <span>Fin</span>
          <small>Đang trả lời</small>
        </div>
        <div className="advisor-bubble advisor-skeleton-wrap">
          <div className="advisor-typing">
            <span />
            <span />
            <span />
          </div>
          <div className="advisor-skeleton advisor-skeleton-wide" />
          <div className="advisor-skeleton advisor-skeleton-mid" />
        </div>
      </div>
    </div>
  );
}

function AdvisorChatPanel({
  compact = false,
  expanded = false,
  onClose,
  onToggleExpand,
}: {
  compact?: boolean;
  expanded?: boolean;
  onClose?: () => void;
  onToggleExpand?: () => void;
}) {
  const initialSessions = useMemo(() => loadStoredSessions(), []);
  const [sessions, setSessions] = useState<ChatSession[]>(initialSessions.sessions);
  const [activeSessionId, setActiveSessionId] = useState(initialSessions.activeSessionId);
  const [showHistory, setShowHistory] = useState(false);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const policyText = useMemo(
    () =>
      'Fin chỉ dùng dữ liệu ngân sách và giao dịch theo phiên đăng nhập. Câu trả lời không hiển thị tên thật, số tài khoản đầy đủ hoặc địa chỉ.',
    [],
  );
  const activeSession = sessions.find((session) => session.id === activeSessionId) || sessions[0];
  const messages = activeSession?.messages || starterMessages;
  const canSend = input.trim().length > 0 && !isLoading;

  const scrollToBottom = () => {
    window.setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  };

  useEffect(() => {
    scrollToBottom();
  }, [expanded]);

  useEffect(() => {
    try {
      const persisted = sessions
        .filter((session) => hasUserContent(session) || session.id === activeSessionId)
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .slice(0, MAX_STORED_SESSIONS);
      window.localStorage.setItem(CHAT_SESSIONS_STORAGE_KEY, JSON.stringify(persisted));
      window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeSessionId);
    } catch {}
  }, [sessions, activeSessionId]);

  const updateActiveSessionMessages = (updater: (messages: ChatMessage[]) => ChatMessage[]) => {
    setSessions((currentSessions) => {
      const now = Date.now();
      return currentSessions
        .map((session) => {
          if (session.id !== activeSessionId) return session;
          const nextMessages = updater(session.messages).slice(-MAX_STORED_MESSAGES);
          return {
            ...session,
            messages: nextMessages,
            title: titleForMessages(nextMessages),
            updatedAt: now,
          };
        })
        .sort((a, b) => b.updatedAt - a.updatedAt);
    });
  };

  const createNewSession = () => {
    const nextSession = createSession();
    setSessions((currentSessions) => [nextSession, ...currentSessions].slice(0, MAX_STORED_SESSIONS));
    setActiveSessionId(nextSession.id);
    setInput('');
    setShowHistory(false);
  };

  const deleteSession = (sessionId: string) => {
    setSessions((currentSessions) => {
      const remaining = currentSessions.filter((session) => session.id !== sessionId);
      if (remaining.length === 0) {
        const replacement = createSession();
        setActiveSessionId(replacement.id);
        return [replacement];
      }
      if (sessionId === activeSessionId) {
        setActiveSessionId(remaining[0].id);
      }
      return remaining;
    });
  };

  const openSession = (sessionId: string) => {
    setActiveSessionId(sessionId);
    setShowHistory(false);
  };

  const submitQuestion = async (question: string) => {
    if (!question.trim() || isLoading) return;

    const trimmedQuestion = question.trim();
    const history = messages
      .filter((message) => message.id !== 'welcome')
      .slice(-6)
      .map((message) => ({ role: message.role, content: message.content }));

    updateActiveSessionMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', content: trimmedQuestion },
    ]);
    setInput('');
    setIsLoading(true);
    scrollToBottom();

    try {
      const result = (await askAdvisor(trimmedQuestion, history)) as AdvisorResponse;
      updateActiveSessionMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: result.answer,
          chart: result.chart || [],
        },
      ]);
    } catch {
      updateActiveSessionMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content:
            'Tớ chưa kết nối được với phần phân tích ngay lúc này. Cậu thử lại sau một chút nhé, rồi mình xem tiếp xem khoản nào đang làm ví cậu mệt nhất được không?',
        },
      ]);
    } finally {
      setIsLoading(false);
      scrollToBottom();
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await submitQuestion(input);
  };

  const clearHistory = () => {
    updateActiveSessionMessages(() => starterMessages);
    setInput('');
    try {
      window.localStorage.removeItem(CHAT_STORAGE_KEY);
    } catch {}
  };

  const chatCard = (
    <Card className="advisor-chat-card">
      <div className="advisor-chat-scroll">
        {messages.map((message) => {
          const isUserMessage = message.role === 'user';
          return (
            <div
              className={cn(
                'advisor-message',
                isUserMessage ? 'advisor-message-user' : 'advisor-message-assistant',
              )}
              key={message.id}
            >
              <div
                className={cn(
                  'advisor-avatar',
                  isUserMessage ? 'advisor-avatar-user' : 'advisor-avatar-ai',
                )}
                aria-hidden="true"
              >
                {isUserMessage ? <User size={17} /> : <Bot size={17} />}
              </div>
              <div className="advisor-message-body">
                <div className="advisor-message-label">
                  <span>{isUserMessage ? 'Bạn' : 'Fin'}</span>
                  <small>{isUserMessage ? 'Tin nhắn của bạn' : 'Trả lời của Fin'}</small>
                </div>
                <div className="advisor-bubble">
                  <Markdown content={message.content} />
                  {message.chart && <MiniChart data={message.chart} />}
                </div>
              </div>
            </div>
          );
        })}
        {isLoading && <LoadingSkeleton />}
        <div ref={bottomRef} />
      </div>

      <div className="advisor-quick-prompts">
        {quickPrompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => submitQuestion(prompt)}
            disabled={isLoading}
          >
            {prompt}
          </button>
        ))}
      </div>

      <form className="advisor-composer" onSubmit={handleSubmit}>
        <textarea
          aria-label="Ask Fin"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Kể Fin nghe chuyện tiền nong của cậu..."
          rows={2}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void submitQuestion(input);
            }
          }}
        />
        <Button type="submit" disabled={!canSend} title="Gửi">
          <Send size={17} />
          Gửi
        </Button>
      </form>
    </Card>
  );
  const sessionsWithContent = sessions.filter((session) => hasUserContent(session));
  const sessionHistoryPanel = (
    <aside className="advisor-session-panel" aria-label="Lịch sử chat Fin">
      <div className="advisor-session-panel-head">
        <strong>Lịch sử phiên</strong>
        <button type="button" onClick={createNewSession}>
          <Plus size={14} />
          Mới
        </button>
      </div>
      {sessionsWithContent.length === 0 ? (
        <p className="advisor-session-empty">Chưa có phiên nào có nội dung.</p>
      ) : (
        <div className="advisor-session-list">
          {sessionsWithContent.map((session) => (
            <button
              type="button"
              className={cn('advisor-session-item', session.id === activeSessionId && 'active')}
              key={session.id}
              onClick={() => openSession(session.id)}
            >
              <span>{session.title}</span>
              <small>{new Date(session.updatedAt).toLocaleDateString('vi-VN')}</small>
              <Trash2
                size={14}
                onClick={(event) => {
                  event.stopPropagation();
                  deleteSession(session.id);
                }}
              />
            </button>
          ))}
        </div>
      )}
    </aside>
  );
  const chatWorkspace = (
    <div className={cn('advisor-chat-workspace', showHistory && 'advisor-chat-workspace-with-history')}>
      {showHistory && sessionHistoryPanel}
      <div className="advisor-chat-main">{chatCard}</div>
    </div>
  );

  if (compact) {
    return (
      <div
        className={cn('advisor-floating-panel', expanded && 'advisor-floating-panel-expanded')}
        role="dialog"
        aria-label="Fin financial chat"
      >
        <div className="advisor-floating-glow" />
        <div className="advisor-floating-header">
          <div className="advisor-floating-title">
            <div className="advisor-fin-mark">
              <Sparkles size={18} />
            </div>
            <div>
              <div className="advisor-eyebrow">Fin đang nghe</div>
              <strong>Người bạn tài chính của cậu</strong>
            </div>
          </div>
          <div className="advisor-floating-actions">
            <Button
              type="button"
              variant="ghost"
              className="advisor-icon-btn"
              onClick={() => setShowHistory((current) => !current)}
              title="Lịch sử"
            >
              <History size={16} />
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="advisor-icon-btn"
              onClick={createNewSession}
              title="Phiên mới"
            >
              <Plus size={16} />
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="advisor-icon-btn"
              onClick={clearHistory}
              title="Clear History"
            >
              <RotateCcw size={16} />
            </Button>
            <Button type="button" variant="ghost" className="advisor-icon-btn" title={policyText}>
              <ShieldCheck size={16} />
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="advisor-icon-btn advisor-resize-btn"
              onClick={onToggleExpand}
              title={expanded ? 'Thu nhỏ' : 'Phóng to'}
            >
              {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
              <span>{expanded ? 'Thu nhỏ' : 'Phóng to'}</span>
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="advisor-icon-btn"
              onClick={onClose}
              title="Đóng"
            >
              <X size={17} />
            </Button>
          </div>
        </div>
        <div className="advisor-floating-policy">
          <LockKeyhole size={14} />
          <span>{policyText}</span>
        </div>
        {chatWorkspace}
      </div>
    );
  }

  return (
    <section className="advisor-shell">
      <div className="advisor-header">
        <div>
          <div className="advisor-eyebrow">
            <Sparkles size={15} />
            Fin Financial Friend
          </div>
          <h1>Chat tài chính cá nhân</h1>
          <p>Hỏi trực tiếp trên dữ liệu ngân sách, dự báo chi tiêu và giao dịch hiện tại.</p>
        </div>
        <div className="advisor-header-actions">
          <Button type="button" variant="secondary" onClick={() => setShowHistory((current) => !current)} title="Lịch sử">
            <History size={16} />
            Lịch sử
          </Button>
          <Button type="button" variant="secondary" onClick={createNewSession} title="Phiên mới">
            <Plus size={16} />
            Phiên mới
          </Button>
          <Button type="button" variant="secondary" onClick={clearHistory} title="Clear History">
            <RotateCcw size={16} />
            Clear History
          </Button>
          <Button type="button" variant="secondary" title={policyText}>
            <ShieldCheck size={16} />
            Security Policy
          </Button>
        </div>
      </div>

      <Card className="advisor-policy">
        <LockKeyhole size={17} />
        <span>{policyText}</span>
      </Card>
      {chatWorkspace}
    </section>
  );
}

export function FloatingAdvisorWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const openWidget = () => {
    setIsOpen(true);
  };

  const closeWidget = () => {
    setIsOpen(false);
    setIsExpanded(false);
  };

  return (
    <div className={cn('advisor-floating-root', isExpanded && 'advisor-floating-root-expanded')}>
      {isOpen && (
        <AdvisorChatPanel
          compact
          expanded={isExpanded}
          onClose={closeWidget}
          onToggleExpand={() => setIsExpanded((current) => !current)}
        />
      )}
      <button
        className={cn('advisor-floating-button', isOpen && 'advisor-floating-button-open')}
        type="button"
        onClick={isOpen ? closeWidget : openWidget}
        aria-label={isOpen ? 'Close Fin' : 'Open Fin'}
      >
        <span className="advisor-floating-button-shine" />
        {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
        <strong>{isOpen ? 'Đóng' : 'Fin'}</strong>
      </button>
    </div>
  );
}

export default function ChatbotInterface() {
  return <AdvisorChatPanel />;
}
