import { useCallback, useEffect, useRef, useState } from 'react'
import { getAuthToken } from '../api'

const RECONNECT_DELAY = 2000
const MAX_RECONNECTS = 5

export function useInterviewWebSocket({ sessionId, roundKey, onMessage, onCodeReview, onComplete, onError, onThinking }) {
  const [status, setStatus] = useState('disconnected')
  const [codeReview, setCodeReview] = useState(null)
  const [isThinking, setIsThinking] = useState(false)
  const wsRef = useRef(null)
  const reconnects = useRef(0)
  const intentionalClose = useRef(false)
  const latestCode = useRef('')
  const latestLanguage = useRef('javascript')
  const codeThrottle = useRef(null)

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return
    intentionalClose.current = false

    const token = getAuthToken()
    if (!token || !sessionId || !roundKey) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/api/ws/interview?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(sessionId)}&round_key=${encodeURIComponent(roundKey)}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
      reconnects.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'thinking') {
          setIsThinking(true)
          onThinking?.(true)
        } else if (data.type === 'ai_message') {
          setIsThinking(false)
          onThinking?.(false)
          onMessage?.(data)
        } else if (data.type === 'code_review') {
          setIsThinking(false)
          onThinking?.(false)
          setCodeReview(data)
          onCodeReview?.(data)
        } else if (data.type === 'interview_complete') {
          setIsThinking(false)
          onComplete?.()
        } else if (data.type === 'error') {
          setIsThinking(false)
          onError?.(data.message)
        } else if (data.type === 'interview_ended') {
          setIsThinking(false)
          onComplete?.()
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onerror = () => {
      onError?.('Connection error')
    }

    ws.onclose = () => {
      setStatus('disconnected')
      setIsThinking(false)
      wsRef.current = null
      if (!intentionalClose.current && reconnects.current < MAX_RECONNECTS) {
        reconnects.current++
        setTimeout(connect, RECONNECT_DELAY)
      }
    }
  }, [sessionId, roundKey, onMessage, onCodeReview, onComplete, onError, onThinking])

  useEffect(() => {
    connect()
    return () => {
      intentionalClose.current = true
      wsRef.current?.close()
    }
  }, [connect])

  const sendMessage = useCallback((text) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'message', text }))
    }
  }, [])

  const sendCodeUpdate = useCallback((code, language) => {
    latestCode.current = code
    latestLanguage.current = language
    if (codeThrottle.current) return
    codeThrottle.current = setTimeout(() => {
      codeThrottle.current = null
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'code_update',
          code: latestCode.current,
          language: latestLanguage.current,
        }))
      }
    }, 500)
  }, [])

  const requestCodeReview = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'review_code',
        code: latestCode.current,
        language: latestLanguage.current,
      }))
    }
  }, [])

  const endInterview = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_interview' }))
    }
  }, [])

  const disconnect = useCallback(() => {
    intentionalClose.current = true
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  return {
    status,
    isThinking,
    codeReview,
    sendMessage,
    sendCodeUpdate,
    requestCodeReview,
    endInterview,
    disconnect,
    reconnect: connect,
  }
}
