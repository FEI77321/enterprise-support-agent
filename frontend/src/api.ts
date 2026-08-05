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
