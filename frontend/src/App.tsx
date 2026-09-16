import { type FormEvent, useState } from 'react'
import { createBadCase, exportBadCase, fetchAgentOpsMetrics, fetchBadCases, streamChatMessage, updateBadCaseStatus } from './api'
import type { AgentOpsMetrics, BadCase, BadCaseCategory, BadCaseStatus, ChatResponse, TicketStatus } from './types'
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

const badCaseStatusLabels: Record<BadCaseStatus, string> = {
  open: '待分诊',
  triaged: '已分诊',
  regression_added: '已入回归',
  resolved: '已解决',
}

function App() {
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState('')
  const [rateLimitInfo, setRateLimitInfo] = useState('')
  const [isGovernanceOpen, setIsGovernanceOpen] = useState(false)
  const [governanceLoading, setGovernanceLoading] = useState(false)
  const [governanceError, setGovernanceError] = useState('')
  const [agentOps, setAgentOps] = useState<AgentOpsMetrics | null>(null)
  const [badCases, setBadCases] = useState<BadCase[]>([])
  const [reportTraceId, setReportTraceId] = useState<string | null>(null)
  const [reportCategory, setReportCategory] = useState<BadCaseCategory>('retrieval')
  const [expectedBehavior, setExpectedBehavior] = useState('应返回可核验的企业支持处理路径与来源。')
  const [actualBehavior, setActualBehavior] = useState('实际结果需要人工复盘并记录为回归案例。')
  const [exportedCaseId, setExportedCaseId] = useState('')
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

  async function refreshGovernance() {
    setGovernanceLoading(true)
    setGovernanceError('')
    try {
      const [metrics, cases] = await Promise.all([fetchAgentOpsMetrics(), fetchBadCases()])
      setAgentOps(metrics)
      setBadCases(cases)
    } catch (requestError) {
      setGovernanceError(requestError instanceof Error ? requestError.message : '无法加载治理数据。')
    } finally {
      setGovernanceLoading(false)
    }
  }

  function openGovernance() {
    setIsGovernanceOpen(true)
    void refreshGovernance()
  }

  function openBadCaseForm(traceId: string) {
    setReportTraceId(traceId)
    setExportedCaseId('')
    openGovernance()
  }

  async function submitBadCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!reportTraceId) return
    setGovernanceLoading(true)
    setGovernanceError('')
    try {
      await createBadCase({
        request_id: reportTraceId,
        category: reportCategory,
        severity: 'medium',
        expected_behavior: expectedBehavior,
        actual_behavior: actualBehavior,
      })
      setReportTraceId(null)
      await refreshGovernance()
    } catch (requestError) {
      setGovernanceError(requestError instanceof Error ? requestError.message : '无法创建 Bad Case。')
    } finally {
      setGovernanceLoading(false)
    }
  }

  async function advanceBadCase(badCaseId: string, status: BadCaseStatus) {
    setGovernanceLoading(true)
    setGovernanceError('')
    try {
      await updateBadCaseStatus(badCaseId, status)
      await refreshGovernance()
    } catch (requestError) {
      setGovernanceError(requestError instanceof Error ? requestError.message : '无法更新 Bad Case。')
    } finally {
      setGovernanceLoading(false)
    }
  }

  async function handleExport(badCaseId: string) {
    setGovernanceLoading(true)
    setGovernanceError('')
    try {
      const exported = await exportBadCase(badCaseId)
      setExportedCaseId(exported.case_id)
    } catch (requestError) {
      setGovernanceError(requestError instanceof Error ? requestError.message : '当前状态不允许导出。')
    } finally {
      setGovernanceLoading(false)
    }
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
          <div className="header-actions">
            <button className="governance-button" type="button" onClick={openGovernance}>治理面板</button>
            <span className="environment-badge">Development</span>
          </div>
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
                {message.response && <ResponseDetails response={message.response} onReportBadCase={openBadCaseForm} />}
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
      {isGovernanceOpen && (
        <GovernancePanel
          agentOps={agentOps}
          badCases={badCases}
          error={governanceError}
          exportedCaseId={exportedCaseId}
          isLoading={governanceLoading}
          onAdvance={advanceBadCase}
          onClose={() => setIsGovernanceOpen(false)}
          onExport={handleExport}
          onRefresh={refreshGovernance}
          onSubmit={submitBadCase}
          reportActualBehavior={actualBehavior}
          reportCategory={reportCategory}
          reportExpectedBehavior={expectedBehavior}
          reportTraceId={reportTraceId}
          setReportActualBehavior={setActualBehavior}
          setReportCategory={setReportCategory}
          setReportExpectedBehavior={setExpectedBehavior}
        />
      )}
    </main>
  )
}

function ResponseDetails({ response, onReportBadCase }: { response: ChatResponse; onReportBadCase: (traceId: string) => void }) {
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

      <section className="detail-section trace-timeline">
        <p className="detail-label">EXECUTION TIMELINE</p>
        <div className="timeline-list">
          <span className={`timeline-event ${response.safety?.action === 'block' ? 'blocked' : ''}`}>
            Guard · {response.safety?.action ?? 'allow'}
          </span>
          <span className="timeline-event">
            Rewrite · {response.query_rewrite?.triggered ? 'applied' : 'passthrough'}
          </span>
          <span className="timeline-event">Retrieval · {response.sources.length} sources</span>
          {(response.harness_trace ?? []).map((step, index) => (
            <span className={`timeline-event ${step.status !== 'completed' ? 'blocked' : ''}`} key={`${step.tool_name}-${index}`}>
              Tool · {step.tool_name} · {step.status}
            </span>
          ))}
          <span className="timeline-event">Memory · {response.memory?.write?.action ?? 'skip'}</span>
          <span className="timeline-event">
            Context · {response.context?.compression_triggered ? 'compressed' : 'within budget'}
            {response.context?.estimated_reduction_ratio ? ` · -${(response.context.estimated_reduction_ratio * 100).toFixed(1)}%` : ''}
          </span>
          <span className="timeline-event">
            Prompt · {response.prompt?.version ?? 'unresolved'} · {response.prompt?.channel ?? 'active'}
          </span>
          {response.timing?.total_ms !== undefined && (
            <span className="timeline-event">E2E · {response.timing.total_ms.toFixed(1)}ms</span>
          )}
        </div>
        {response.trace_id && <code className="trace-id">Trace {response.trace_id}</code>}
        {response.trace_id && (
          <button className="report-bad-case-button" type="button" onClick={() => onReportBadCase(response.trace_id!)}>
            标记为 Bad Case
          </button>
        )}
      </section>
    </div>
  )
}

type GovernancePanelProps = {
  agentOps: AgentOpsMetrics | null
  badCases: BadCase[]
  error: string
  exportedCaseId: string
  isLoading: boolean
  reportTraceId: string | null
  reportCategory: BadCaseCategory
  reportExpectedBehavior: string
  reportActualBehavior: string
  onClose: () => void
  onRefresh: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onAdvance: (badCaseId: string, status: BadCaseStatus) => void
  onExport: (badCaseId: string) => void
  setReportCategory: (category: BadCaseCategory) => void
  setReportExpectedBehavior: (value: string) => void
  setReportActualBehavior: (value: string) => void
}

function GovernancePanel(props: GovernancePanelProps) {
  return (
    <aside className="governance-panel" aria-label="Agent 治理面板">
      <header className="governance-header">
        <div>
          <p className="eyebrow">TRACE TO REGRESSION</p>
          <h2>质量治理面板</h2>
        </div>
        <button className="panel-close-button" type="button" onClick={props.onClose}>关闭</button>
      </header>

      <section className="governance-metrics">
        <div><span>Trace</span><strong>{props.agentOps?.trace_runs ?? '-'}</strong></div>
        <div><span>未解决</span><strong>{props.agentOps?.open_bad_case_count ?? '-'}</strong></div>
        <div><span>工具失败率</span><strong>{props.agentOps ? `${(props.agentOps.tool_failure_rate * 100).toFixed(1)}%` : '-'}</strong></div>
        <div><span>Context 压缩率</span><strong>{props.agentOps ? `${(props.agentOps.context_compression_trigger_rate * 100).toFixed(1)}%` : '-'}</strong></div>
        <div><span>E2E P95</span><strong>{props.agentOps?.request_phase_elapsed_ms?.total_ms?.p95 !== undefined && props.agentOps.request_phase_elapsed_ms.total_ms.p95 !== null ? `${props.agentOps.request_phase_elapsed_ms.total_ms.p95.toFixed(1)}ms` : '-'}</strong></div>
      </section>

      {props.reportTraceId && (
        <form className="bad-case-form" onSubmit={props.onSubmit}>
          <p className="detail-label">从当前 TRACE 创建 BAD CASE</p>
          <code>{props.reportTraceId}</code>
          <label>失败类别
            <select value={props.reportCategory} onChange={(event) => props.setReportCategory(event.target.value as BadCaseCategory)}>
              <option value="retrieval">retrieval</option><option value="rewrite">rewrite</option><option value="safety">safety</option>
              <option value="tool">tool</option><option value="authorization">authorization</option><option value="memory">memory</option><option value="response">response</option>
              <option value="context">context</option><option value="prompt">prompt</option><option value="performance">performance</option>
            </select>
          </label>
          <label>预期行为<textarea required minLength={5} value={props.reportExpectedBehavior} onChange={(event) => props.setReportExpectedBehavior(event.target.value)} /></label>
          <label>实际行为<textarea required minLength={5} value={props.reportActualBehavior} onChange={(event) => props.setReportActualBehavior(event.target.value)} /></label>
          <button className="panel-primary-button" disabled={props.isLoading} type="submit">纳入 Bad Case</button>
        </form>
      )}

      <div className="governance-list-header">
        <p className="detail-label">BAD CASE 生命周期</p>
        <button className="panel-text-button" disabled={props.isLoading} type="button" onClick={props.onRefresh}>刷新</button>
      </div>
      {props.error && <p className="governance-error" role="alert">{props.error}</p>}
      {props.exportedCaseId && <p className="export-success">已导出 Eval Case：{props.exportedCaseId}</p>}
      <div className="bad-case-list">
        {props.badCases.length === 0 && <p className="empty-governance">暂无 Bad Case。完成一次对话后可从 Trace 创建案例。</p>}
        {props.badCases.map((badCase) => (
          <article className="bad-case-card" key={badCase.bad_case_id}>
            <div className="bad-case-card-header"><strong>{badCase.category}</strong><span className={`bad-case-status ${badCase.status}`}>{badCaseStatusLabels[badCase.status]}</span></div>
            <p>{badCase.expected_behavior}</p>
            <code>{badCase.request_id}</code>
            <div className="bad-case-actions">
              {badCase.status === 'open' && <button type="button" onClick={() => props.onAdvance(badCase.bad_case_id, 'triaged')}>分诊</button>}
              {badCase.status === 'triaged' && <button type="button" onClick={() => props.onAdvance(badCase.bad_case_id, 'regression_added')}>加入回归</button>}
              {badCase.status === 'regression_added' && <button type="button" onClick={() => props.onAdvance(badCase.bad_case_id, 'resolved')}>标记解决</button>}
              {(badCase.status === 'regression_added' || badCase.status === 'resolved') && <button type="button" onClick={() => props.onExport(badCase.bad_case_id)}>导出</button>}
            </div>
          </article>
        ))}
      </div>
    </aside>
  )
}

export default App
