export default function GuardrailFootnote({ className = '' }: { className?: string }) {
  return (
    <p className={`text-[12px] text-muted ${className}`}>
      Monitoring signals for clinician review — not a diagnosis.
    </p>
  )
}
