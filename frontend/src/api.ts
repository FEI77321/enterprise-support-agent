// 模块职责：封装企业支持 Agent 的 HTTP 调用，并将聊天响应转换为前端类型。

import type { ChatResponse } from './types'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export async function sendChatMessage(message: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message }),
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null)
    const detail = errorBody?.detail
    const errorMessage =
      typeof detail === 'string'
        ? detail
        : `请求失败，状态码：${response.status}`

    throw new Error(errorMessage)
  }

  return (await response.json()) as ChatResponse
}

export type ChatStreamEvent =
  | { event: 'meta'; data: { request_id: string } }
  | { event: 'rate_limit'; data: { limit: number; remaining: number; resetAfterSeconds: number } }
  | { event: 'status'; data: { message: string } }
  | { event: 'message_delta'; data: { delta: string } }
  | { event: 'workflow'; data: { steps: string[] } }
  | { event: 'error'; data: { code: string; detail: string } }
  | { event: 'complete'; data: ChatResponse }

export async function streamChatMessage(
  message: string,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message }),
  })

  if (!response.ok || !response.body) {
    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After')
      throw new Error(
        retryAfter
          ? `请求过于频繁，请在 ${retryAfter} 秒后重试。`
          : '请求过于频繁，请稍后重试。',
      )
    }
    const errorBody = await response.json().catch(() => null)
    const detail = errorBody?.detail
    throw new Error(
      typeof detail === 'string'
        ? detail
        : `请求失败，状态码：${response.status}`,
    )
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completeResponse: ChatResponse | undefined

  const limit = Number(response.headers.get('X-RateLimit-Limit'))
  const remaining = Number(response.headers.get('X-RateLimit-Remaining'))
  const resetAfterSeconds = Number(response.headers.get('X-RateLimit-Reset'))
  if (Number.isFinite(limit) && Number.isFinite(remaining) && Number.isFinite(resetAfterSeconds)) {
    onEvent({
      event: 'rate_limit',
      data: { limit, remaining, resetAfterSeconds },
    })
  }

  function consumeEvent(rawEvent: string) {
    const eventName = rawEvent.match(/^event: (.+)$/m)?.[1]
    const dataText = rawEvent
      .split('\n')
      .filter((line) => line.startsWith('data: '))
      .map((line) => line.slice(6))
      .join('\n')

    if (!eventName || !dataText) {
      return
    }

    const event = {
      event: eventName,
      data: JSON.parse(dataText),
    } as ChatStreamEvent
    onEvent(event)

    if (event.event === 'error') {
      throw new Error(event.data.detail)
    }
    if (event.event === 'complete') {
      completeResponse = event.data
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })

    let separatorIndex = buffer.indexOf('\n\n')
    while (separatorIndex >= 0) {
      consumeEvent(buffer.slice(0, separatorIndex))
      buffer = buffer.slice(separatorIndex + 2)
      separatorIndex = buffer.indexOf('\n\n')
    }

    if (done) {
      break
    }
  }

  if (!completeResponse) {
    throw new Error('流式响应未返回完成事件。')
  }

  return completeResponse
}
