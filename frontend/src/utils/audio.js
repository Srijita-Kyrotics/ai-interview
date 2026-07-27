export function audioBlobToDataUrl(blob) {
  if (!blob) return Promise.resolve('')
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result || '')
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

export function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition
}
