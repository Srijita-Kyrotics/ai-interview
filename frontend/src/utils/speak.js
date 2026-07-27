let preferredVoice = null
let voicesLoaded = false
let audioCtx = null

function getAudioContext() {
  if (audioCtx) return audioCtx
  if (typeof window === 'undefined') return null
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)()
    return audioCtx
  } catch {
    return null
  }
}

function loadVoices() {
  if (voicesLoaded) return
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  const voices = window.speechSynthesis.getVoices()
  if (!voices.length) {
    window.speechSynthesis.onvoiceschanged = () => {
      if (voicesLoaded) return
      const v = window.speechSynthesis.getVoices()
      preferredVoice = v.find(vi => /en.*(US|GB|India)/i.test(vi.name)) || v[0] || null
      voicesLoaded = true
    }
    return
  }
  preferredVoice = voices.find(vi => /en.*(US|GB|India)/i.test(vi.name)) || voices[0] || null
  voicesLoaded = true
}

loadVoices()

export function speak(text, { rate = 1.05, pitch = 1, onEnd, onStart } = {}) {
  if (typeof window === 'undefined' || !window.speechSynthesis) {
    onEnd?.()
    return { cancel: () => {} }
  }

  window.speechSynthesis.cancel()
  loadVoices()

  const utter = new SpeechSynthesisUtterance(text)
  if (preferredVoice) utter.voice = preferredVoice
  utter.rate = rate
  utter.pitch = pitch
  utter.volume = 1

  let cancelled = false
  utter.onstart = () => { if (!cancelled) onStart?.() }
  utter.onend = () => { if (!cancelled) onEnd?.() }
  utter.onerror = (e) => { if (!cancelled && e.error !== 'canceled') onEnd?.() }

  window.speechSynthesis.speak(utter)

  return {
    cancel: () => {
      cancelled = true
      window.speechSynthesis.cancel()
    }
  }
}

export function stopSpeaking() {
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    window.speechSynthesis.cancel()
  }
}

export function playChime() {
  const ctx = getAudioContext()
  if (!ctx) return

  // Resume context if suspended (browser autoplay policy)
  if (ctx.state === 'suspended') {
    ctx.resume()
  }

  const now = ctx.currentTime

  // Two-tone ascending chime (pleasant, not jarring)
  const freqs = [523.25, 659.25] // C5, E5
  const duration = 0.15
  const gap = 0.08

  freqs.forEach((freq, i) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()

    osc.type = 'sine'
    osc.frequency.setValueAtTime(freq, now)
    gain.gain.setValueAtTime(0, now + i * (duration + gap))
    gain.gain.linearRampToValueAtTime(0.15, now + i * (duration + gap) + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.001, now + i * (duration + gap) + duration)

    osc.connect(gain)
    gain.connect(ctx.destination)

    osc.start(now + i * (duration + gap))
    osc.stop(now + i * (duration + gap) + duration + 0.01)
  })
}
