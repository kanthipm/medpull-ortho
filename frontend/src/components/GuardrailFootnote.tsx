/** The clinical guardrail line, as a 12/400 secondary `.meta` paragraph
 *  (--muted 5.393 / 4.906 on panel, 5.025 / 5.243 on canvas). */
export default function GuardrailFootnote({ className = '' }: { className?: string }) {
  return (
    <p className={`meta ${className}`}>
      Monitoring signals for clinician review — not a diagnosis.
    </p>
  )
}
