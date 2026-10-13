import React, { useState, useRef, useCallback } from 'react'

/**
 * Renders a GIF as static thumbnail by default; plays (shows animated GIF) on hover or when selected.
 * Uses CSS for transition between static and animated states.
 */
export default function GifStepPreview({
  gifUrl,
  thumbnailUrl: thumbnailUrlProp,
  isSelected = false,
  alt = 'GIF',
  className = '',
  imgClassName = '',
  onError,
  ...imgProps
}) {
  const [thumbnailUrl, setThumbnailUrl] = useState(thumbnailUrlProp || null)
  const [isHover, setIsHover] = useState(false)
  const imgRef = useRef(null)
  const canvasRef = useRef(null)

  const extractFirstFrame = useCallback(() => {
    if (thumbnailUrl || !gifUrl || !imgRef.current || !canvasRef.current) return
    const img = imgRef.current
    const canvas = canvasRef.current
    if (img.naturalWidth === 0 || img.naturalHeight === 0) return
    try {
      const w = img.naturalWidth
      const h = img.naturalHeight
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, 0, 0)
      const dataUrl = canvas.toDataURL('image/png')
      setThumbnailUrl(dataUrl)
    } catch (_) {
      // Fallback: use gif as "thumbnail" (will animate)
      setThumbnailUrl(gifUrl)
    }
  }, [gifUrl, thumbnailUrl])

  const effectiveThumbnail = thumbnailUrlProp ?? thumbnailUrl
  const showAnimated = isHover || isSelected
  const displaySrc = showAnimated ? gifUrl : (effectiveThumbnail || gifUrl)

  return (
    <div
      className={className}
      onMouseEnter={() => setIsHover(true)}
      onMouseLeave={() => setIsHover(false)}
      style={{ position: 'relative', overflow: 'hidden' }}
    >
      <canvas
        ref={canvasRef}
        style={{ position: 'absolute', left: -9999, top: 0, width: 1, height: 1 }}
        aria-hidden
      />
      {!effectiveThumbnail && gifUrl && (
        <img
          ref={imgRef}
          src={gifUrl}
          alt=""
          aria-hidden
          onLoad={extractFirstFrame}
          onError={onError}
          style={{ position: 'absolute', width: 0, height: 0, opacity: 0, pointerEvents: 'none' }}
        />
      )}
      <img
        src={displaySrc}
        alt={alt}
        className={imgClassName}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          transition: 'opacity 0.2s ease',
          opacity: 1,
        }}
        onError={onError}
        {...imgProps}
      />
    </div>
  )
}
