import { formatQuestionText } from './questionFormat'

const parenCleanRe = /\(([a-zA-Z0-9]+)\)\/([a-zA-Z0-9]+)/g
const mixedFractionRe = /\(([a-zA-Z0-9]+)\)\s*\(\(([^()]+?)\/([^()]+?)\)\)/g
const spacedFractionRe = /\(\s*([a-zA-Z0-9.]+)\s*\)\s*\/\s*\(\s*([a-zA-Z0-9.]+)\s*\)/g
const supSubFractionRe = /\^\(\s*([a-zA-Z0-9.]+)\s*\)\s*\/\s*_\(\s*([a-zA-Z0-9.]+)\s*\)/g

function cleanParens(str) {
  return (str || '')
    .replace(/\^\(\)/g, '')
    .replace(mixedFractionRe, '$1 $2/$3')
    .replace(spacedFractionRe, '$1/$2')
    .replace(supSubFractionRe, '$1/$2')
    .replace(parenCleanRe, '$1/$2')
    .replace(/\(\s*([a-zA-Z0-9]+)\s*\)/g, '$1')
}

function findHighlighted(sentence, options, correct) {
  const words = sentence.split(/\s+/)
  if (!words.length || !correct) return null

  const skip = new Set(['the', 'a', 'an', 'is', 'was', 'were', 'are', 'been', 'being', 'be',
    'in', 'on', 'at', 'to', 'for', 'of', 'by', 'with', 'from', 'as', 'into', 'through',
    'it', 'its', 'they', 'them', 'he', 'she', 'his', 'her', 'their', 'this', 'that',
    'and', 'or', 'but', 'not', 'no', 'so', 'if', 'than', 'then'])

  let bestStart = words.length, bestEnd = 0
  const candidates = [correct, ...options.filter(o => o !== 'No correction required')]
  for (const cand of candidates) {
    const candWords = cand.toLowerCase().split(/\s+/)
    for (const cw of candWords) {
      if (skip.has(cw) || cw.length < 2) continue
      for (let i = 0; i < words.length; i++) {
        const w = words[i].replace(/[^a-zA-Z]/g, '').toLowerCase()
        if (w === cw || (w.length >= 3 && cw.length >= 3 && (w.startsWith(cw) || cw.startsWith(w)))) {
          if (i < bestStart) bestStart = i
          if (i + 1 > bestEnd) bestEnd = i + 1
          break
        }
      }
    }
  }

  if (bestEnd === 0) return null
  return { start: bestStart, end: bestEnd }
}

function processAptitudeText(questions) {
  return questions.map(q => {
    if (q.options) {
      q.options = q.options.map(opt => formatQuestionText(cleanParens(opt)))
    }
    q.question = formatQuestionText(cleanParens(q.question || ''))
    const text = q.question

    if (text.includes('highlighted')) {
      const lines = text.split('\n')
      const instruction = lines[0]
      const sentence = lines.slice(1).join(' ').trim()
      if (sentence) {
        const hl = findHighlighted(sentence, q.options || [], q.correct || '')
        if (hl) {
          const wordArr = sentence.split(/\s+/)
          const before = wordArr.slice(0, hl.start).join(' ')
          const mid = wordArr.slice(hl.start, hl.end).join(' ')
          const after = wordArr.slice(hl.end).join(' ')
          const sep = before && after ? ' ' : ''
          q.question = instruction + '\n' + before + (before ? ' ' : '') + '«hl»' + mid + '«/hl»' + (after ? ' ' : '') + after
          return q
        }
      }
    }

    const match = text.match(/^(.*?)\n([A-Z][A-Z\s-]{1,})$/)
    if (match) {
      const word = match[2].trim()
      q.question = match[1] + '\n«b»' + word + '«/b»'
    }

    return q
  })
}

export { processAptitudeText }
