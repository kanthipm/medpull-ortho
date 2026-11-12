import type { Ref } from 'react'

/** A clip, played in place: controls, inline on a phone, metadata only until
 *  pressed so a dialog does not pull the whole file down on open. A phone's
 *  clip is portrait, so the box is dark and the picture sits inside it.
 *  `autoPlay` is the library preview's quiet loop: muted, so it may start. */
export default function ClipPlayer({
  src,
  poster,
  label,
  autoPlay = false,
  className = '',
  videoRef,
}: {
  src: string
  poster?: string | null
  label: string
  autoPlay?: boolean
  className?: string
  /** For a reader that needs the moment the clip is on (comments pinned to
   *  a time), or to send it back to one. */
  videoRef?: Ref<HTMLVideoElement>
}) {
  return (
    <video
      ref={videoRef}
      controls
      playsInline
      preload="metadata"
      src={src}
      poster={poster ?? undefined}
      aria-label={label}
      muted={autoPlay}
      loop={autoPlay}
      autoPlay={autoPlay}
      className={`w-full rounded-control bg-ink object-contain ${className}`}
    />
  )
}
