export function scoreClass(score) {
  if (score >= 70) return 'score-good'
  if (score >= 50) return 'score-mid'
  return 'score-low'
}
