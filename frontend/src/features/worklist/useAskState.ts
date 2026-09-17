import { useState } from 'react'
import { useAsk, type AskResult } from '../../api/queries'

/** Shared state for the worklist's ask field (in the page head, on the sky)
 *  and its answer card (below the head, on the canvas). The page owns it so
 *  the two can live in different places and the answer can filter the list. */
export function useAskState() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<AskResult | null>(null)
  const ask = useAsk()
  const pending = ask.isPending

  const submit = (q: string) => {
    const trimmed = q.trim()
    if (trimmed.length < 3 || pending) return
    setQuestion(trimmed)
    ask.mutate(trimmed, { onSuccess: setResult })
  }

  const clear = () => {
    setQuestion('')
    setResult(null)
    ask.reset()
  }

  return { question, setQuestion, result, pending, submit, clear }
}

export type AskState = ReturnType<typeof useAskState>
