import { useEffect, useMemo, useRef, useState } from 'react';
import { MessageCircle, Send, X, Check, ThumbsUp, ThumbsDown, Bug, Loader2, History, Plus } from 'lucide-react';
import { getChatSessionMessages, getChatSessions, sendChatFeedback, sendChatMessage } from '../../api/services';

const INITIAL_PROMPT_CHIPS = [
  'Tháng này tôi tiêu nhiều nhất vào đâu?',
  'Tổng quan tài chính của tôi thế nào?',
  'Có khoản nào bất thường không?',
  'Cuối tháng tôi còn khoảng bao nhiêu?',
  'Tài chính của tôi có ổn không?',
  'Tôi muốn tiết kiệm 20 triệu trong 6 tháng thì làm sao?',
  'Tôi có đang vượt ngân sách không?',
  'Tôi nên chia ngân sách tháng này thế nào?',
  'Cho tôi xem giao dịch chưa phân loại',
  'Có những category nào?',
];

function uniquePrompts(prompts, limit = 4) {
  return [...new Set(prompts.filter(Boolean))].slice(0, limit);
}

function buildFollowUpPrompts(message) {
  const response = message?.response || {};
  const intent = response.intent || '';
  const toolName = response.tool_calls?.[0]?.tool_name || '';

  if (response.requires_confirmation) {
    return [];
  }

  if (toolName === 'recommend_budget_plan') {
    return uniquePrompts([
      'Áp dụng kế hoạch đó đi',
      'Danh mục nào nên giảm trước?',
      'Nếu giảm ăn uống 500k thì sao?',
    ]);
  }

  if (toolName === 'get_budget_status' || toolName === 'compare_budget_vs_actual') {
    return uniquePrompts([
      'Danh mục nào rủi ro nhất?',
      'Tôi nên điều chỉnh ngân sách nào?',
      'Gợi ý kế hoạch ngân sách mới',
    ]);
  }

  if (toolName === 'plan_savings_goal') {
    return uniquePrompts([
      'Tạo mục tiêu đó đi',
      'Nếu tôi giảm ăn uống 500k/tháng thì sao?',
      'Mục tiêu này có rủi ro gì?',
    ]);
  }

  if (toolName === 'get_transactions') {
    return uniquePrompts([
      'Lọc các giao dịch lớn nhất',
      'Đổi giao dịch này sang danh mục khác',
      'Có giao dịch nào chưa phân loại nữa không?',
    ]);
  }

  if (toolName === 'get_anomalies') {
    return uniquePrompts([
      'Giải thích giao dịch đáng chú ý nhất',
      'Tôi nên kiểm tra khoản nào trước?',
      'So với kỳ trước thì sao?',
    ]);
  }

  if (toolName === 'get_balance_forecast') {
    return uniquePrompts([
      'Tôi nên giảm khoản nào để an toàn hơn?',
      'Nếu giữ tốc độ này thì rủi ro gì?',
      'Gợi ý ngân sách cho phần còn lại của tháng',
    ]);
  }

  if (toolName === 'get_financial_health_score') {
    return uniquePrompts([
      'Làm sao để cải thiện điểm này?',
      'Điểm yếu lớn nhất là gì?',
      'Gợi ý 3 việc nên làm tuần này',
    ]);
  }

  if (intent === 'SPENDING_BREAKDOWN') {
    return uniquePrompts([
      'Danh mục nào tăng nhiều nhất?',
      'Cho tôi xem các giao dịch liên quan',
      'So với kỳ trước thì sao?',
    ]);
  }

  if (intent === 'CATEGORY_CORRECTION') {
    return uniquePrompts([
      'Ghi nhớ rule này cho lần sau',
      'Cho tôi xem giao dịch chưa phân loại',
      'Có những category nào?',
    ]);
  }

  if (intent === 'PRIVACY_OR_PERMISSION') {
    return uniquePrompts([
      'Bạn nhớ gì về tôi?',
      'Quên sở thích trả lời ngắn gọn đi',
    ]);
  }

  return uniquePrompts([
    'Phân tích kỹ hơn',
    'Gợi ý bước tiếp theo',
    'So với kỳ trước thì sao?',
  ], 3);
}

function createSessionId() {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function createMessage(role, content, extra = {}) {
  return {
    id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    ...extra,
  };
}

function isDebugEnabled() {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get('debug_chat') === '1' || localStorage.getItem('spectra-chat-debug') === '1';
  } catch {
    return false;
  }
}

const ChatMessageBubble = ({ message, debug }) => (
  <div className={`chat-message chat-message-${message.role}`}>
    <div className="chat-bubble">
      {String(message.content || '').split('\n').map((line, index) => (
        <p key={index}>{line || '\u00a0'}</p>
      ))}
    </div>
    {message.role === 'assistant' && (
      <FeedbackButtons message={message} />
    )}
    {debug && message.response && (
      <DebugToolTrace response={message.response} />
    )}
  </div>
);

const FeedbackButtons = ({ message }) => {
  const [sent, setSent] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (rating) => {
    if (busy || sent) return;
    setBusy(true);
    try {
      await sendChatFeedback({
        session_id: message.sessionId,
        message_id: message.id,
        rating,
        intent: message.response?.intent || '',
      });
      setSent(rating);
    } catch {
      setSent('error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat-feedback" aria-label="Đánh giá câu trả lời">
      <button type="button" disabled={busy || Boolean(sent)} onClick={() => submit('up')} title="Hữu ích">
        <ThumbsUp size={14} /> {sent === 'up' ? 'Đã gửi' : ''}
      </button>
      <button type="button" disabled={busy || Boolean(sent)} onClick={() => submit('down')} title="Chưa hữu ích">
        <ThumbsDown size={14} /> {sent === 'down' ? 'Đã gửi' : ''}
      </button>
      {sent === 'error' && <span>Không gửi được feedback</span>}
    </div>
  );
};

const DebugToolTrace = ({ response }) => (
  <details className="chat-debug">
    <summary><Bug size={14} /> Debug</summary>
    <pre>{JSON.stringify({
      intent: response.intent,
      tool_calls: response.tool_calls || [],
      confirmation: response.confirmation || null,
      debug: response.debug || null,
    }, null, 2)}</pre>
  </details>
);

const ConfirmationCard = ({ confirmation, onConfirm, onCancel, busy }) => {
  if (!confirmation) return null;
  return (
    <div className="chat-confirmation">
      <div>
        <strong>Xác nhận thay đổi</strong>
        <p>{confirmation.summary || 'Bạn xác nhận thực hiện thay đổi này không?'}</p>
        <small>Mã xác nhận sẽ hết hạn sau một thời gian ngắn.</small>
      </div>
      <div className="chat-confirmation-actions">
        <button type="button" className="primary-btn" disabled={busy} onClick={() => onConfirm(confirmation.confirmation_id)}>
          <Check size={15} /> Xác nhận
        </button>
        <button type="button" className="ghost-btn" disabled={busy} onClick={() => onCancel(confirmation.confirmation_id)}>
          <X size={15} /> Hủy
        </button>
      </div>
    </div>
  );
};

const SuggestedActions = ({ actions = [], onSend, onConfirm, onCancel, busy }) => {
  if (!actions.length) return null;
  return (
    <div className="chat-suggested-actions">
      {actions.map((action, index) => {
        const label = action.label || action.action || 'Tiếp tục';
        const type = action.type || action.action;
        const handleClick = () => {
          if (type === 'confirm' && action.confirmation_id) {
            onConfirm(action.confirmation_id);
          } else if (type === 'cancel' && action.confirmation_id) {
            onCancel(action.confirmation_id);
          } else if (action.message || action.arguments?.message) {
            onSend(action.message || action.arguments.message);
          } else if (label) {
            onSend(label);
          }
        };
        return (
          <button key={`${label}-${index}`} type="button" disabled={busy} onClick={handleClick}>
            {label}
          </button>
        );
      })}
    </div>
  );
};

const PromptChips = ({ onPick, compact, prompts = INITIAL_PROMPT_CHIPS }) => (
  <div className={`chat-prompt-chips ${compact ? 'chat-prompt-chips-compact' : ''}`}>
    {prompts.map((prompt) => (
      <button key={prompt} type="button" onClick={() => onPick(prompt)}>
        {prompt}
      </button>
    ))}
  </div>
);

function formatSessionTime(value) {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return '';
  }
}

export function ChatPanel({ scope = 'cycle' }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState('');
  const debug = useMemo(() => isDebugEnabled(), []);
  const sessionIdRef = useRef(createSessionId());
  const listRef = useRef(null);
  const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant');
  const followUpPrompts = useMemo(() => buildFollowUpPrompts(latestAssistant), [latestAssistant]);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, loading, open]);

  const appendAssistantResponse = (response) => {
    const nextSessionId = response.session_id || sessionIdRef.current;
    sessionIdRef.current = nextSessionId;
    const extra = {
      response,
      sessionId: nextSessionId,
    };
    if (response.message_id) {
      extra.id = response.message_id;
    }
    setMessages((prev) => [
      ...prev,
      createMessage('assistant', response.answer || 'Mình chưa có câu trả lời.', {
        ...extra,
      }),
    ]);
  };

  const loadSessions = async () => {
    setHistoryLoading(true);
    setError('');
    try {
      const response = await getChatSessions(30);
      setSessions(response.sessions || []);
    } catch (err) {
      setError(err?.message || 'Không tải được lịch sử chat.');
    } finally {
      setHistoryLoading(false);
    }
  };

  const toggleHistory = async () => {
    const nextOpen = !historyOpen;
    setHistoryOpen(nextOpen);
    if (nextOpen) {
      await loadSessions();
    }
  };

  const startNewChat = () => {
    sessionIdRef.current = createSessionId();
    setMessages([]);
    setInput('');
    setError('');
    setHistoryOpen(false);
  };

  const openSession = async (sessionId) => {
    if (!sessionId || loading) return;
    setHistoryLoading(true);
    setError('');
    try {
      const response = await getChatSessionMessages(sessionId, 80);
      sessionIdRef.current = sessionId;
      setMessages(
        (response.messages || [])
          .filter((message) => ['user', 'assistant'].includes(message.role))
          .map((message) => createMessage(message.role, message.content, {
            id: message.id,
            sessionId,
            response: message.role === 'assistant' ? { intent: message.intent || '' } : undefined,
          }))
      );
      setHistoryOpen(false);
    } catch (err) {
      setError(err?.message || 'Không tải được nội dung phiên chat.');
    } finally {
      setHistoryLoading(false);
    }
  };

  const submitPayload = async (payload) => {
    setLoading(true);
    setError('');
    try {
      const response = await sendChatMessage({
        session_id: sessionIdRef.current,
        scope,
        debug,
        ...payload,
      });
      appendAssistantResponse(response);
    } catch (err) {
      const message = err?.message === 'Not authenticated'
        ? 'Bạn cần đăng nhập để dùng chat.'
        : (err?.message || 'Không gửi được tin nhắn. Vui lòng thử lại.');
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async (text = input) => {
    const trimmed = String(text || '').trim();
    if (!trimmed || loading) return;
    setOpen(true);
    setMessages((prev) => [...prev, createMessage('user', trimmed)]);
    setInput('');
    await submitPayload({ message: trimmed });
  };

  const sendConfirmation = async (confirmationId, confirm) => {
    if (!confirmationId || loading) return;
    setMessages((prev) => [
      ...prev,
      createMessage('user', confirm ? 'Xác nhận' : 'Hủy'),
    ]);
    await submitPayload({
      message: confirm ? 'Xác nhận' : 'Hủy',
      confirmation_id: confirmationId,
      confirm,
    });
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    sendMessage();
  };

  return (
    <>
      <button type="button" className="chat-launcher" onClick={() => setOpen(true)} aria-label="Mở trợ lý tài chính">
        <MessageCircle size={22} />
        <span>Trợ lý</span>
      </button>

      {open && (
        <aside className="chat-drawer" aria-label="Trợ lý tài chính">
          <div className="chat-header">
            <div>
              <strong>Trợ lý tài chính</strong>
              <span>Dữ liệu kỳ hiện tại</span>
            </div>
            <button type="button" className="chat-icon-button" onClick={() => setOpen(false)} aria-label="Đóng">
              <X size={18} />
            </button>
          </div>

          <div className="chat-toolbar">
            <button type="button" onClick={toggleHistory} disabled={historyLoading}>
              <History size={15} /> {historyOpen ? 'Ẩn lịch sử' : 'Lịch sử'}
            </button>
            <button type="button" onClick={startNewChat}>
              <Plus size={15} /> Chat mới
            </button>
          </div>

          <div className="chat-messages" ref={listRef}>
            {historyOpen && (
              <div className="chat-history-panel">
                <div className="chat-history-title">
                  <strong>Lịch sử chat</strong>
                  <button type="button" onClick={loadSessions} disabled={historyLoading}>
                    {historyLoading ? 'Đang tải...' : 'Làm mới'}
                  </button>
                </div>
                {sessions.length === 0 && !historyLoading && (
                  <p className="chat-history-empty">Chưa có phiên chat đã lưu.</p>
                )}
                <div className="chat-history-list">
                  {sessions.map((session) => (
                    <button
                      key={session.id}
                      type="button"
                      className={session.id === sessionIdRef.current ? 'active' : ''}
                      onClick={() => openSession(session.id)}
                    >
                      <span>{session.title || 'Phiên chat chưa có tiêu đề'}</span>
                      <small>{formatSessionTime(session.last_message_at || session.updated_at || session.created_at)}</small>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.length === 0 && (
              <div className="chat-empty">
                <p>Hỏi về chi tiêu, dự báo, mục tiêu tiết kiệm hoặc ngân sách.</p>
                <PromptChips onPick={sendMessage} prompts={INITIAL_PROMPT_CHIPS.slice(0, 4)} />
              </div>
            )}
            {messages.map((message) => (
              <ChatMessageBubble key={message.id} message={message} debug={debug} />
            ))}
            {loading && (
              <div className="chat-loading">
                <Loader2 size={16} className="chat-spin" /> Đang xử lý...
              </div>
            )}
            {error && <div className="chat-error">{error}</div>}
          </div>

          {latestAssistant?.response?.requires_confirmation && (
            <ConfirmationCard
              confirmation={latestAssistant.response.confirmation}
              busy={loading}
              onConfirm={(id) => sendConfirmation(id, true)}
              onCancel={(id) => sendConfirmation(id, false)}
            />
          )}

          {latestAssistant?.response?.suggested_actions?.length > 0 && (
            <SuggestedActions
              actions={latestAssistant.response.suggested_actions}
              busy={loading}
              onSend={sendMessage}
              onConfirm={(id) => sendConfirmation(id, true)}
              onCancel={(id) => sendConfirmation(id, false)}
            />
          )}

          {messages.length > 0 && followUpPrompts.length > 0 && (
            <PromptChips onPick={sendMessage} compact prompts={followUpPrompts} />
          )}

          <form className="chat-input-row" onSubmit={handleSubmit}>
            <textarea
              value={input}
              rows={2}
              maxLength={1000}
              placeholder="Nhập câu hỏi..."
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  sendMessage();
                }
              }}
            />
            <button type="submit" className="primary-btn" disabled={loading || !input.trim()} aria-label="Gửi">
              <Send size={17} />
            </button>
          </form>
        </aside>
      )}
    </>
  );
}

export default ChatPanel;
