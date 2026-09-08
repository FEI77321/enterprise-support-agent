import { type FormEvent, useState } from 'react'
import { streamChatMessage } from './api'
import type { ChatResponse, TicketStatus } from './types'
import './App.css'

type ChatMessage = {
  id: string
  role: 'assistant' | 'user'
  text: string
  response?: ChatResponse
  streamingStatus?: string
}

const suggestedQuestions = [
  'VPN 720 错误怎么办',
  '账号被锁了怎么办',
  '出差费用怎么走流程',
  '病假申请需要什么材料',
]

const responseTypeLabels: Record<ChatResponse['type'], string> = {
  answer: '知识库回答',
  ticket_created: '已创建工单',
  ticket_status: '工单状态',
  clarify: '需要补充信息',
}

const ticketStatusLabels: Record<TicketStatus, string> = {
  OPEN: '待处理',
  IN_PROGRESS: '处理中',
  CLOSED: '已关闭',
}

function App() {
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState('')
  const [rateLimitInfo, setRateLimitInfo] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: '你好，我可以协助处理 VPN、账号登录、报销和请假等企业支持问题。',
    },
  ])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = input.trim()

    if (!message || isSending) {
      return
    }

    setError('')
    setInput('')
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: `user-${Date.now()}`,
        role: 'user',
        text: message,
      },
    ])
    const assistantMessageId = `assistant-${Date.now()}`
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: assistantMessageId,
        role: 'assistant',
        text: '',
        streamingStatus: '正在连接企业支持服务...',
      },
    ])
    setIsSending(true)

    try {
      const response = await streamChatMessage(message, (event) => {
        if (event.event === 'rate_limit') {
          setRateLimitInfo(
            `当前额度：${event.data.remaining}/${event.data.limit}，约 ${event.data.resetAfterSeconds} 秒后重置。`,
          )
        }

        if (event.event === 'status') {
          setMessages((currentMessages) => currentMessages.map((currentMessage) => (
            currentMessage.id === assistantMessageId
              ? { ...currentMessage, streamingStatus: event.data.message }
              : currentMessage
          )))
        }

        if (event.event === 'message_delta') {
          setMessages((currentMessages) => currentMessages.map((currentMessage) => (
            currentMessage.id === assistantMessageId
              ? {
                  ...currentMessage,
                  text: currentMessage.text + event.data.delta,
                  streamingStatus: undefined,
                }
              : currentMessage
          )))
        }
      })
      setMessages((currentMessages) => [
        ...currentMessages.map((currentMessage) => (
          currentMessage.id === assistantMessageId
            ? {
                ...currentMessage,
                text: response.answer ?? currentMessage.text,
                response,
                streamingStatus: undefined,
              }
            : currentMessage
        )),
      ])
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '无法连接企业支持服务，请检查后端是否已启动。',
      )
    } finally {
      setIsSending(false)
    }
  }

  function startNewSession() {
    setError('')
    setRateLimitInfo('')
    setInput('')
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        text: '已开始新会话。请输入需要协助的企业支持问题。',
      },
    ])
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">EA</div>
          <div>
            <p className="eyebrow">INTERNAL SUPPORT</p>
            <h1>Enterprise Agent</h1>
          </div>
        </div>

        <button className="new-session-button" type="button" onClick={startNewSession}>
          New session
        </button>

        <section className="sidebar-section" aria-labelledby="suggested-title">
          <p id="suggested-title" className="section-label">SUGGESTED QUESTIONS</p>
          <div className="suggestion-list">
            {suggestedQuestions.map((question) => (
              <button
                className="suggestion-button"
                key={question}
                type="button"
                onClick={() => setInput(question)}
              >
                {question}
              </button>
            ))}
          </div>
        </section>

        <div className="sidebar-footer">
          <span className="status-dot" aria-hidden="true" />
          Knowledge service online
        </div>
      </aside>

      <section className="workspace" aria-label="企业支持聊天工作台">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">KNOWLEDGE-ASSISTED SUPPORT</p>
            <h2>企业支持工作台</h2>
          </div>
          <span className="environment-badge">Development</span>
        </header>

        <div className="conversation" aria-live="polite">
          {messages.map((message) => (
            <article className={`message-row ${message.role}`} key={message.id}>
              <div className="message-meta">
                {message.role === 'assistant' ? 'Enterprise Agent' : 'You'}
              </div>
              <div className="message-body">
                {message.streamingStatus && (
                  <p className="message-text">{message.streamingStatus}</p>
                )}
                {message.text && <p className="message-text">{message.text}</p>}
                {message.response && <ResponseDetails response={message.response} />}
              </div>
            </article>
          ))}
        </div>

        <div className="composer-area">
          {error && <p className="request-error" role="alert">{error}</p>}
          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              aria-label="企业支持问题"
              disabled={isSending}
              onChange={(event) => setInput(event.target.value)}
              placeholder="例如：VPN 720 错误怎么办"
              rows={2}
              value={input}
            />
            <button className="send-button" disabled={!input.trim() || isSending} type="submit">
              {isSending ? 'Sending...' : 'Send'}
            </button>
          </form>
          <p className="composer-hint">
            {rateLimitInfo || '企业支持范围：VPN、账号登录、报销、请假及工单查询。'}
          </p>
        </div>
      </section>
    </main>
  )
}

function ResponseDetails({ response }: { response: ChatResponse }) {
  return (
    <div className="response-details">
      <div className="response-summary">
        <span className="response-type">{responseTypeLabels[response.type]}</span>
        <span className="request-id">Request {response.request_id.slice(0, 8)}</span>
      </div>

      {response.sources.length > 0 && (
        <section className="detail-section">
          <p className="detail-label">SOURCES</p>
          <div className="source-list">
            {response.sources.map((source) => (
              <div className="source-item" key={`${source.file}-${source.chunk_id}`}>
                <div className="source-header">
                  <strong>{source.file}</strong>
                  <span>score {source.score}</span>
                </div>
                <p>{source.snippet}</p>
                {source.chunk_id && <code>{source.chunk_id}</code>}
              </div>
            ))}
          </div>
        </section>
      )}

      {response.ticket && (
        <section className="detail-section ticket-detail">
          <p className="detail-label">TICKET</p>
          <div className="ticket-grid">
            <span>编号</span><strong>{response.ticket.ticket_id}</strong>
            <span>状态</span><strong>{ticketStatusLabels[response.ticket.status]}</strong>
            <span>优先级</span><strong>{response.ticket.priority}</strong>
            <span>处理组</span><strong>{response.ticket.assignee}</strong>
          </div>
        </section>
      )}

      {response.workflow_steps.length > 0 && (
        <section className="detail-section">
          <p className="detail-label">WORKFLOW</p>
          <div className="workflow-list">
            {response.workflow_steps.map((step) => (
              <span className="workflow-step" key={step}>{step}</span>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

export default App
