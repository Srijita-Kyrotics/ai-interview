const COMMON_FRACTIONS = new Map([
  ['1/2', '\u00bd'],
  ['1/4', '\u00bc'],
  ['3/4', '\u00be'],
  ['1/3', '\u2153'],
  ['2/3', '\u2154'],
  ['1/5', '\u2155'],
  ['2/5', '\u2156'],
  ['3/5', '\u2157'],
  ['4/5', '\u2158'],
  ['1/6', '\u2159'],
  ['5/6', '\u215a'],
  ['1/8', '\u215b'],
  ['3/8', '\u215c'],
  ['5/8', '\u215d'],
  ['7/8', '\u215e'],
])

const BRACKET_FRACTION_RE = /\(\s*([A-Za-z0-9.]+)\s*\)\s*\/\s*\(\s*([A-Za-z0-9.]+)\s*\)/g
const SUP_SUB_FRACTION_RE = /\^\(\s*([A-Za-z0-9.]+)\s*\)\s*\/\s*_\(\s*([A-Za-z0-9.]+)\s*\)/g
const LATEX_FRAC_RE = /\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g

export function formatQuestionText(input) {
  if (input == null) return ''
  const raw = String(input)
  const decoded = decodeHtmlEntities(raw)
  const stripped = stripHtmlPreserveMath(decoded)
  const latex = normalizeLatex(stripped)
  return normalizeSpacingAndFractions(latex)
}

function stripHtmlPreserveMath(text) {
  if (typeof window === 'undefined' || typeof DOMParser === 'undefined' || !/[<&]/.test(text)) {
    return text
  }

  const parser = new DOMParser()
  const doc = parser.parseFromString(`<div>${text}</div>`, 'text/html')
  return serializeNode(doc.body.firstElementChild || doc.body)
}

function serializeNode(node) {
  if (!node) return ''

  const parts = []
  node.childNodes.forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) {
      parts.push(child.textContent || '')
      return
    }

    if (child.nodeType !== Node.ELEMENT_NODE) return

    const el = child
    const tag = el.tagName.toLowerCase()

    if (tag === 'br') {
      parts.push('\n')
      return
    }

    if (tag === 'img') {
      const alt = el.getAttribute('alt') || el.getAttribute('title') || el.getAttribute('aria-label') || ''
      if (alt) {
        parts.push(alt)
        return
      }

      const src = el.getAttribute('src') || ''
      parts.push(imageNameToFallback(src))
      return
    }

    if (tag === 'math') {
      parts.push(serializeMathMl(el))
      return
    }

    if (tag === 'sup') {
      parts.push(`^(${serializeNode(el)})`)
      return
    }

    if (tag === 'sub') {
      parts.push(`_(${serializeNode(el)})`)
      return
    }

    if (tag === 'table' && el.classList.contains('ga-tbl-answer')) {
      parts.push(serializeFractionTable(el))
      return
    }

    parts.push(serializeNode(el))
  })

  return parts.join('')
}

function serializeMathMl(el) {
  const frac = el.querySelector('mfrac')
  if (frac) {
    const children = frac.children
    if (children.length >= 2) {
      return `(${serializeNode(children[0])})/(${serializeNode(children[1])})`
    }
  }

  return el.textContent || ''
}

function serializeFractionTable(table) {
  const rows = table.querySelectorAll('tr')
  if (rows.length < 2) return table.textContent || ''

  const numCells = rows[0].querySelectorAll('td')
  const denCells = rows[1].querySelectorAll('td')
  const parts = []
  let denIdx = 0

  numCells.forEach((cell) => {
    if (cell.getAttribute('rowspan')) {
      const text = cell.textContent?.trim()
      if (text) parts.push(text)
      return
    }

    const num = cell.textContent?.trim() || ''
    let den = ''
    if (denIdx < denCells.length) {
      den = denCells[denIdx].textContent?.trim() || ''
      denIdx += 1
    }

    if (num || den) parts.push(den ? `(${num})/(${den})` : num)
  })

  return parts.join(' ')
}

function imageNameToFallback(src) {
  const name = (src || '').split('/').pop() || ''
  if (/sym-tfr|fraction|frac/i.test(name)) return '/'
  return ''
}

function normalizeLatex(text) {
  return text
    .replace(/^\s*\$\$(.*)\$\$\s*$/s, '$1')
    .replace(/^\\\((.*)\\\)$/s, '$1')
    .replace(/^\\\[(.*)\\\]$/s, '$1')
    .replace(LATEX_FRAC_RE, (_, n, d) => {
      const num = n.trim()
      const den = d.trim()
      if (/^[0-9]+$/.test(num) && /^[0-9]+$/.test(den)) return `${num}/${den}`
      return `(${num})/(${den})`
    })
}

function normalizeSpacingAndFractions(text) {
  let out = text
    .replace(/<[^>]+>/g, ' ')
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\s+,/g, ',')
    .replace(/\s+\./g, '.')
    .replace(/\(\s+/g, '(')
    .replace(/\s+\)/g, ')')
    .trim()

  out = out.replace(SUP_SUB_FRACTION_RE, (_, n, d) => `${n}/${d}`)
  out = out.replace(BRACKET_FRACTION_RE, (_, n, d) => COMMON_FRACTIONS.get(`${n}/${d}`) || `${n}/${d}`)

  return out
}

function decodeHtmlEntities(text) {
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    const textarea = document.createElement('textarea')
    textarea.innerHTML = text
    return textarea.value
  }

  return text
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}
