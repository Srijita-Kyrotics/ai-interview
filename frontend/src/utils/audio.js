export function audioBlobToDataUrl(blob) {
  if (!blob) return Promise.resolve('')
  return new Promise((resolve) => {
    try {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result || '')
      reader.onerror = () => resolve('')
      reader.readAsDataURL(blob)
    } catch {
      resolve('')
    }
  })
}

export function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition
}

export function getPreferredAudioMime() {
  if (typeof MediaRecorder === 'undefined') return ''
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) return type
  }
  return ''
}
