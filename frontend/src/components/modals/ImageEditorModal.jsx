import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fabric } from 'fabric'

function setCanvasSize(fc, width, height) {
  if (typeof fc?.setDimensions === 'function') {
    fc.setDimensions({ width, height })
    return
  }
  if (typeof fc?.setWidth === 'function') fc.setWidth(width)
  if (typeof fc?.setHeight === 'function') fc.setHeight(height)
}

function sendToBack(fc, obj) {
  if (!fc || !obj) return
  if (typeof fc.sendToBack === 'function') return fc.sendToBack(obj)
  if (typeof fc.sendObjectToBack === 'function') return fc.sendObjectToBack(obj)
}

async function fabricImageFromUrl(url) {
  return await new Promise((resolve, reject) => {
    try {
      fabric.Image.fromURL(
        url,
        (img) => {
          if (!img) reject(new Error('Failed to load image'))
          else resolve(img)
        },
        { crossOrigin: null }
      )
    } catch (e) {
      reject(e)
    }
  })
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n))
}

async function loadImage(src) {
  return await new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    // Only set CORS for remote URLs; blob/data URLs don't need it and some browsers can be picky.
    try {
      const s = (src || '').toString()
      if (s.startsWith('http://') || s.startsWith('https://')) img.crossOrigin = 'anonymous'
    } catch {
      // ignore
    }
    img.src = src
  })
}

async function cropImageToBlob(imageSrc, croppedAreaPixels) {
  const img = await loadImage(imageSrc)
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('canvas ctx unavailable')

  // Ensure integers
  const x = Math.round(croppedAreaPixels.x)
  const y = Math.round(croppedAreaPixels.y)
  const w = Math.round(croppedAreaPixels.width)
  const h = Math.round(croppedAreaPixels.height)

  canvas.width = Math.max(1, w)
  canvas.height = Math.max(1, h)

  ctx.drawImage(img, x, y, w, h, 0, 0, w, h)

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!blob) throw new Error('Failed to create PNG blob')
  return blob
}

function IconButton({ children, active, ...props }) {
  return (
    <button
      type="button"
      className={`w-full rounded-md border px-2 py-1.5 text-xs font-medium leading-tight disabled:opacity-50 ${active ? 'ring-1 ring-emerald-400' : ''}`}
      style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--card-border)', color: 'var(--text)' }}
      {...props}
    >
      {children}
    </button>
  )
}

function ToolButton({ icon, active, label, ...props }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      className={`grid h-10 w-10 place-items-center rounded-md border transition-colors disabled:opacity-50 ${active ? 'ring-1 ring-emerald-400' : ''}`}
      style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--card-border)', color: 'var(--text)' }}
      {...props}
    >
      {icon}
    </button>
  )
}

function Icon({ children }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  )
}

const Icons = {
  annotate: <Icon><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></Icon>,
  crop: <Icon><path d="M6 2v14a2 2 0 0 0 2 2h14" /><path d="M2 6h14a2 2 0 0 1 2 2v14" /></Icon>,
  select: <Icon><path d="M4 4l7 16 2-6 6-2Z" /></Icon>,
  arrow: <Icon><path d="M5 19l14-14" /><path d="M9 5h10v10" /></Icon>,
  pen: <Icon><path d="M12 19l7-7" /><path d="M12 19H5l7-7" /><path d="M17 5l2 2" /></Icon>,
  text: <Icon><path d="M4 6h16" /><path d="M10 6v14" /><path d="M14 6v14" /></Icon>,
  undo: <Icon><path d="M3 7v6h6" /><path d="M21 17a8 8 0 0 0-14-5L3 13" /></Icon>,
  redo: <Icon><path d="M21 7v6h-6" /><path d="M3 17a8 8 0 0 1 14-5l4 1" /></Icon>,
  check: <Icon><path d="M20 6 9 17l-5-5" /></Icon>,
  options: <Icon><path d="M4 21v-7" /><path d="M4 10V3" /><path d="M12 21v-9" /><path d="M12 8V3" /><path d="M20 21v-5" /><path d="M20 12V3" /><path d="M2 14h4" /><path d="M10 10h4" /><path d="M18 16h4" /></Icon>,
  cancel: <Icon><path d="M18 6 6 18" /><path d="M6 6l12 12" /></Icon>,
  save: <Icon><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" /><path d="M17 21v-8H7v8" /><path d="M7 3v5h8" /></Icon>,
  rect: <Icon><rect x="5" y="5" width="14" height="14" rx="2" /></Icon>,
  circle: <Icon><circle cx="12" cy="12" r="7" /></Icon>,
  trash: <Icon><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M7 6l1 14h8l1-14" /></Icon>,
  clear: <Icon><path d="M3 21h18" /><path d="M7 17l10-10" /><path d="M9 5h6" /></Icon>,
}

export default function ImageEditorModal({ open, onClose, step, onSave }) {
  const [showAdvanced, setShowAdvanced] = useState(false)

  const undoStackRef = useRef([])
  const redoStackRef = useRef([])
  const isRestoringRef = useRef(false)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)

  const cropPendingRectRef = useRef(null)
  const [cropPending, setCropPending] = useState(null) // {x,y,width,height} | null

  // Working image URL (object URL or original step.url)
  const [workingUrl, setWorkingUrl] = useState('')
  const workingUrlRef = useRef('')
  const createdObjectUrlsRef = useRef(new Set())
  const skipNextRebuildRef = useRef(false)
  const [imageLoadError, setImageLoadError] = useState('')
  const [annotateMediaLoaded, setAnnotateMediaLoaded] = useState(false)

  const [tool, setTool] = useState('none') // none|select|draw|rect|arrow|text|crop|circle
  const [strokeColor, setStrokeColor] = useState('#ef4444') // red-500
  const [strokeWidth, setStrokeWidth] = useState(6)

  // Fabric
  const canvasElRef = useRef(null)
  const fabricCanvasRef = useRef(null)
  const baseImageObjRef = useRef(null)
  const annotateWrapperRef = useRef(null)
  const annotateStageRef = useRef(null)
  const isDrawingRectRef = useRef(false)
  const rectObjRef = useRef(null)
  const isDrawingCircleRef = useRef(false)
  const circleObjRef = useRef(null)
  const isDrawingTextBoxRef = useRef(false)
  const textGuideRectRef = useRef(null)
  const textBoxStartRef = useRef({ x: 0, y: 0 })
  const dragStartRef = useRef({ x: 0, y: 0 })
  const arrowStateRef = useRef({ drawing: false, x0: 0, y0: 0, line: null, head: null })

  const originalUrl = step?.url || ''

  function setWorkingUrlSafe(nextUrl) {
    setWorkingUrl(nextUrl)
    workingUrlRef.current = nextUrl
  }

  const canSave = useMemo(() => {
    return !!step && !!workingUrl
  }, [step, workingUrl])

  // Setup working URL when opening
  useEffect(() => {
    if (!open) return
    if (!step) return
    setImageLoadError('')
    setAnnotateMediaLoaded(false)
    setShowAdvanced(false)

    // Prefer generating a fresh object URL from the blob to avoid stale/revoked URLs.
    let u = originalUrl
    try {
      if (step?.blob instanceof Blob) {
        u = URL.createObjectURL(step.blob)
        createdObjectUrlsRef.current.add(u)
      }
    } catch {
      // fallback to originalUrl
    }
    setWorkingUrlSafe(u)
    setTool('none')
    setCropPending(null)
    cropPendingRectRef.current = null
    undoStackRef.current = []
    redoStackRef.current = []
    setCanUndo(false)
    setCanRedo(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, step?.id])

  // Revoke working blob URL when closing the modal
  useEffect(() => {
    if (open) return
    // Revoke any object URLs we created during this editing session
    try {
      for (const url of createdObjectUrlsRef.current) {
        try { URL.revokeObjectURL(url) } catch {}
      }
    } catch {
      // ignore
    }
    createdObjectUrlsRef.current = new Set()

    // Keep refs in sync
    workingUrlRef.current = ''
  }, [open, originalUrl])

  // Cleanup object URL if we created one
  useEffect(() => {
    return () => {
      try {
        for (const url of createdObjectUrlsRef.current) {
          try { URL.revokeObjectURL(url) } catch {}
        }
      } catch {
        // ignore
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [originalUrl])

  // Initialize / rebuild fabric canvas when workingUrl/layout changes
  useEffect(() => {
    if (!open) return
    if (skipNextRebuildRef.current) {
      skipNextRebuildRef.current = false
      return
    }
    const el = canvasElRef.current
    if (!el) return

    setAnnotateMediaLoaded(false)
    setImageLoadError('')

    // Dispose previous
    if (fabricCanvasRef.current) {
      try { fabricCanvasRef.current.dispose() } catch {}
      fabricCanvasRef.current = null
      baseImageObjRef.current = null
    }

    const fc = new fabric.Canvas(el, {
      selection: true,
      preserveObjectStacking: true,
    })
    fabricCanvasRef.current = fc

    // IMPORTANT: do NOT reset history here.
    // Cropping changes workingUrl and rebuilds the canvas; we want undo to be able to go back.

    // Help ensure pointer events work reliably across browsers/devices
    try {
      // Make sure fabric-created wrapper fills our container
      if (fc.wrapperEl) {
        fc.wrapperEl.style.position = 'absolute'
        fc.wrapperEl.style.inset = '0'
        fc.wrapperEl.style.width = '100%'
        fc.wrapperEl.style.height = '100%'
      }

      if (fc.upperCanvasEl) {
        fc.upperCanvasEl.style.position = 'absolute'
        fc.upperCanvasEl.style.inset = '0'
        fc.upperCanvasEl.style.width = '100%'
        fc.upperCanvasEl.style.height = '100%'
        fc.upperCanvasEl.style.touchAction = 'none'
        fc.upperCanvasEl.style.userSelect = 'none'
        fc.upperCanvasEl.style.pointerEvents = 'auto'
      }
      if (fc.lowerCanvasEl) {
        fc.lowerCanvasEl.style.position = 'absolute'
        fc.lowerCanvasEl.style.inset = '0'
        fc.lowerCanvasEl.style.width = '100%'
        fc.lowerCanvasEl.style.height = '100%'
        fc.lowerCanvasEl.style.pointerEvents = 'none'
      }
    } catch {
      // ignore
    }

    let cancelled = false

    ;(async () => {
      try {
        let fimg
        try {
          fimg = await fabricImageFromUrl(workingUrl)
        } catch {
          const imgEl = await loadImage(workingUrl)
          fimg = new fabric.Image(imgEl)
        }
        if (cancelled) return

        const imgW = Number(fimg.width) || 1
        const imgH = Number(fimg.height) || 1

        // Make canvas match the visible wrapper so pointer events always land on Fabric.
        // Then fit/center the image inside the canvas.
        const container = annotateWrapperRef.current || annotateStageRef.current
        const cw0 = container?.clientWidth || 0
        const ch0 = container?.clientHeight || 0
        const canvasW = Math.max(320, cw0 || 1280)
        const canvasH = Math.max(240, ch0 || 760)

        setCanvasSize(fc, canvasW, canvasH)

        // Allow some upscaling, but keep reasonable
        const scale = Math.min(canvasW / imgW, canvasH / imgH, 2)
        const drawnW = imgW * scale
        const drawnH = imgH * scale
        const offsetX = Math.max(0, Math.round((canvasW - drawnW) / 2))
        const offsetY = Math.max(0, Math.round((canvasH - drawnH) / 2))

        fimg.set({
          left: offsetX,
          top: offsetY,
          originX: 'left',
          originY: 'top',
          selectable: false,
          evented: false,
          scaleX: scale,
          scaleY: scale,
        })
        baseImageObjRef.current = { obj: fimg, scale, imgW, imgH, offsetX, offsetY }
        fc.add(fimg)
        sendToBack(fc, fimg)
        fc.renderAll()
        // Ensure pointer math matches final layout
        requestAnimationFrame(() => {
          try { fc.calcOffset() } catch {}
        })
        setAnnotateMediaLoaded(true)

        // Initial history snapshot (push if we already have history, e.g. after a crop)
        try {
          const snap = JSON.stringify(fc.toDatalessJSON(['selectable', 'evented']))
          if (!undoStackRef.current || undoStackRef.current.length === 0) {
            undoStackRef.current = [snap]
          } else {
            const cur = undoStackRef.current
            if (cur[cur.length - 1] !== snap) cur.push(snap)
          }
          redoStackRef.current = []
          setCanUndo((undoStackRef.current?.length || 0) > 1)
          setCanRedo(false)
        } catch {
          // ignore
        }
      } catch (e) {
        const msg = (e && (e.message || e.toString())) ? (e.message || e.toString()) : ''
        setImageLoadError(msg ? `Não foi possível carregar a imagem para edição. (${msg})` : 'Não foi possível carregar a imagem para edição.')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [open, workingUrl])

  // Keep fabric offsets updated when scrolling/resizing
  useEffect(() => {
    if (!open) return
    const fc = fabricCanvasRef.current
    if (!fc) return

    const recalc = () => {
      try { fc.calcOffset() } catch {}
    }

    window.addEventListener('resize', recalc)
    // capture scroll from any ancestor containers
    window.addEventListener('scroll', recalc, true)
    const wrapper = annotateWrapperRef.current
    if (wrapper) wrapper.addEventListener('scroll', recalc)

    return () => {
      window.removeEventListener('resize', recalc)
      window.removeEventListener('scroll', recalc, true)
      if (wrapper) wrapper.removeEventListener('scroll', recalc)
    }
  }, [open])

  const pushHistory = useCallback(() => {
    const fc = fabricCanvasRef.current
    if (!fc) return
    if (isRestoringRef.current) return
    try {
      const snap = JSON.stringify(fc.toDatalessJSON(['selectable', 'evented']))
      const cur = undoStackRef.current
      if (cur.length && cur[cur.length - 1] === snap) return
      cur.push(snap)
      if (cur.length > 50) cur.shift()
      redoStackRef.current = []
      setCanUndo(cur.length > 1)
      setCanRedo(false)
    } catch {
      // ignore
    }
  }, [])

  const restoreFromJson = useCallback((json) => {
    const fc = fabricCanvasRef.current
    if (!fc) return
    isRestoringRef.current = true
    fc.loadFromJSON(json, () => {
      try {
        // Re-apply base image rules (first image is treated as base)
        const imgs = (fc.getObjects() || []).filter((o) => o?.type === 'image')
        const baseImg = imgs[0]
        if (baseImg) {
          baseImg.set({ selectable: false, evented: false })
          sendToBack(fc, baseImg)
          baseImageObjRef.current = {
            obj: baseImg,
            imgW: Number(baseImg.width) || 1,
            imgH: Number(baseImg.height) || 1,
            scale: Number(baseImg.scaleX) || 1,
            offsetX: Number(baseImg.left) || 0,
            offsetY: Number(baseImg.top) || 0,
          }

          // Keep workingUrl in sync with restored base image
          try {
            const src = typeof baseImg.getSrc === 'function'
              ? baseImg.getSrc()
              : (baseImg._originalElement?.src || '')
            if (src) {
              skipNextRebuildRef.current = true
              setWorkingUrlSafe(src)
            }
          } catch {
            // ignore
          }
        }

        // Enforce selection policy (avoid default selection when tool isn't 'select')
        fc.selection = tool === 'select'
        fc.forEachObject((obj) => {
          if (obj === baseImageObjRef.current?.obj) return
          obj.selectable = tool === 'select'
          obj.evented = tool === 'select'
        })
      } catch {
        // ignore
      }

      try { fc.renderAll() } catch {}
      isRestoringRef.current = false
      setCanUndo((undoStackRef.current?.length || 0) > 1)
      setCanRedo((redoStackRef.current?.length || 0) > 0)
    })
  }, [tool])

  const handleUndo = useCallback(() => {
    const cur = undoStackRef.current
    if (!cur || cur.length <= 1) return
    const popped = cur.pop()
    if (popped) redoStackRef.current.push(popped)
    const prev = cur[cur.length - 1]
    if (prev) restoreFromJson(prev)
    setCanUndo(cur.length > 1)
    setCanRedo(redoStackRef.current.length > 0)
  }, [restoreFromJson])

  const handleRedo = useCallback(() => {
    const redo = redoStackRef.current
    if (!redo || redo.length === 0) return
    const next = redo.pop()
    if (!next) return
    undoStackRef.current.push(next)
    restoreFromJson(next)
    setCanUndo((undoStackRef.current?.length || 0) > 1)
    setCanRedo(redo.length > 0)
  }, [restoreFromJson])

  const isTypingTarget = useCallback((evt) => {
    const t = evt?.target
    if (!t) return false
    const tag = (t.tagName || '').toLowerCase()
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
    if (t.isContentEditable) return true
    return false
  }, [])

  const isEditingFabricText = useCallback(() => {
    const fc = fabricCanvasRef.current
    if (!fc) return false
    try {
      const active = fc.getActiveObject?.()
      return !!active?.isEditing
    } catch {
      return false
    }
  }, [])

  // Keyboard shortcuts inside the editor
  useEffect(() => {
    if (!open) return

    const onKeyDown = (e) => {
      if (!e) return

      // ESC: if editing text, exit editing; otherwise close modal
      if (e.key === 'Escape') {
        // If Fabric text is being edited, ESC should only exit editing.
        const fc = fabricCanvasRef.current
        let exited = false
        try {
          const active = fc?.getActiveObject?.()
          if (active?.isEditing && typeof active.exitEditing === 'function') {
            e.preventDefault()
            e.stopPropagation()
            active.exitEditing()
            try { fc?.discardActiveObject?.() } catch {}
            try { fc?.requestRenderAll?.() } catch {}
            exited = true
          }
        } catch {
          // ignore
        }
        if (exited) return

        e.preventDefault()
        e.stopPropagation()
        onClose?.()
        return
      }

      // Avoid hijacking typing (inputs, textarea, contenteditable) and fabric text editing
      const typing = isTypingTarget(e) || isEditingFabricText()

      // Undo/redo
      if (!typing && (e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault()
        e.stopPropagation()
        if (e.shiftKey) handleRedo()
        else handleUndo()
        return
      }
      if (!typing && (e.ctrlKey || e.metaKey) && (e.key === 'y' || e.key === 'Y')) {
        e.preventDefault()
        e.stopPropagation()
        handleRedo()
        return
      }

      // Delete selected
      if (!typing && (e.key === 'Delete' || e.key === 'Backspace')) {
        const fc = fabricCanvasRef.current
        const hasSelection = !!fc?.getActiveObject?.() || (fc?.getActiveObjects?.()?.length || 0) > 0
        if (hasSelection) {
          e.preventDefault()
          e.stopPropagation()
          removeSelected()
        }
      }
    }

    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [open, onClose, handleUndo, handleRedo, removeSelected, isTypingTarget, isEditingFabricText])

  // Tool wiring
  useEffect(() => {
    if (!open) return
    const fc = fabricCanvasRef.current
    if (!fc) return

    fc.isDrawingMode = false
    fc.defaultCursor = 'default'

    // Remove previous handlers
    fc.off('mouse:down')
    fc.off('mouse:move')
    fc.off('mouse:up')

    // Default selection mode
    fc.selection = tool === 'select'
    fc.forEachObject((obj) => {
      if (obj === baseImageObjRef.current?.obj) return
      // Keep text editable if currently editing
      if (obj?.isEditing) {
        obj.selectable = true
        obj.evented = true
        return
      }
      obj.selectable = tool === 'select'
      obj.evented = tool === 'select'
    })

    if (tool === 'draw') {
      fc.isDrawingMode = true
      const brush = new fabric.PencilBrush(fc)
      brush.color = strokeColor
      brush.width = strokeWidth
      fc.freeDrawingBrush = brush
      fc.selection = false
    }
    // Commit history on free-draw and object transforms (only when selection is enabled)
    const onPath = () => pushHistory()
    const onModified = () => pushHistory()
    try {
      fc.on('path:created', onPath)
      fc.on('object:modified', onModified)
    } catch {
      // ignore
    }

    return () => {
      try {
        fc.off('path:created', onPath)
        fc.off('object:modified', onModified)
      } catch {
        // ignore
      }
    }
  }, [open, tool, strokeColor, strokeWidth, pushHistory])

  const handleStagePointerDown = useCallback((e) => {
    const fc = fabricCanvasRef.current
    if (!fc) return

    if (cropPending) return
    if (!['arrow', 'crop', 'rect', 'circle', 'text'].includes(tool)) return
    e.preventDefault()
    e.stopPropagation()
    try { e.currentTarget.setPointerCapture?.(e.pointerId) } catch {}
    try { fc.calcOffset() } catch {}

    let p
    try { p = fc.getPointer(e) } catch { p = { x: 0, y: 0 } }

    if (tool === 'text') {
      // Click-drag to size a textbox (guide rect). On release we create an empty Textbox.
      isDrawingTextBoxRef.current = true
      textBoxStartRef.current = { x: p.x, y: p.y }
      const guide = new fabric.Rect({
        left: p.x,
        top: p.y,
        width: 1,
        height: 1,
        fill: 'rgba(96,165,250,0.10)',
        stroke: '#60a5fa',
        strokeWidth: 2,
        strokeDashArray: [6, 4],
        selectable: false,
        evented: false,
        originX: 'left',
        originY: 'top',
      })
      textGuideRectRef.current = guide
      fc.add(guide)
      fc.requestRenderAll()
      return
    }

    if (tool === 'arrow') {
      const st = arrowStateRef.current
      st.drawing = true
      st.x0 = p.x
      st.y0 = p.y
      const line = new fabric.Line([p.x, p.y, p.x, p.y], { stroke: strokeColor, strokeWidth, selectable: false, evented: false })
      const head = new fabric.Triangle({
        left: p.x,
        top: p.y,
        width: 18,
        height: 24,
        fill: strokeColor,
        originX: 'center',
        originY: 'center',
        selectable: false,
        evented: false,
        angle: 0,
      })
      st.line = line
      st.head = head
      fc.add(line)
      fc.add(head)
      fc.requestRenderAll()
      return
    }

    if (tool === 'circle') {
      isDrawingCircleRef.current = true
      dragStartRef.current = { x: p.x, y: p.y }
      const c = new fabric.Ellipse({
        left: p.x,
        top: p.y,
        rx: 1,
        ry: 1,
        fill: 'rgba(0,0,0,0)',
        stroke: strokeColor,
        strokeWidth,
        selectable: false,
        evented: false,
        originX: 'center',
        originY: 'center',
      })
      circleObjRef.current = c
      fc.add(c)
      fc.requestRenderAll()
      return
    }

    // rect/crop
    isDrawingRectRef.current = true
    dragStartRef.current = { x: p.x, y: p.y }
    const r = new fabric.Rect({
      left: p.x,
      top: p.y,
      width: 1,
      height: 1,
      fill: tool === 'crop' ? 'rgba(16,185,129,0.08)' : 'rgba(0,0,0,0)',
      stroke: tool === 'crop' ? '#10b981' : strokeColor,
      strokeWidth,
      strokeDashArray: tool === 'crop' ? [6, 4] : undefined,
      selectable: false,
      evented: false,
      originX: 'left',
      originY: 'top',
    })
    rectObjRef.current = r
    fc.add(r)
    fc.requestRenderAll()
  }, [tool, strokeColor, strokeWidth, cropPending, pushHistory])

  const handleStagePointerMove = useCallback((e) => {
    const fc = fabricCanvasRef.current
    if (!fc) return
    if (cropPending) return
    if (!['arrow', 'crop', 'rect', 'circle', 'text'].includes(tool)) return
    e.preventDefault()
    e.stopPropagation()

    let p
    try { p = fc.getPointer(e) } catch { p = { x: 0, y: 0 } }

    if (tool === 'arrow') {
      const st = arrowStateRef.current
      if (!st.drawing || !st.line || !st.head) return
      st.line.set({ x2: p.x, y2: p.y })
      const dx = p.x - st.x0
      const dy = p.y - st.y0
      const angle = (Math.atan2(dy, dx) * 180) / Math.PI + 90
      st.head.set({ left: p.x, top: p.y, angle })
      fc.requestRenderAll()
      return
    }

    if (tool === 'circle') {
      if (!isDrawingCircleRef.current) return
      const c = circleObjRef.current
      if (!c) return
      const { x: x0, y: y0 } = dragStartRef.current
      const cx = (x0 + p.x) / 2
      const cy = (y0 + p.y) / 2
      const rx = Math.max(1, Math.abs(p.x - x0) / 2)
      const ry = Math.max(1, Math.abs(p.y - y0) / 2)
      c.set({ left: cx, top: cy, rx, ry })
      c.setCoords()
      fc.requestRenderAll()
      return
    }

    if (tool === 'text') {
      if (!isDrawingTextBoxRef.current) return
      const guide = textGuideRectRef.current
      if (!guide) return
      const x0 = textBoxStartRef.current.x
      const y0 = textBoxStartRef.current.y
      guide.set({
        left: Math.min(x0, p.x),
        top: Math.min(y0, p.y),
        width: Math.abs(p.x - x0),
        height: Math.abs(p.y - y0),
      })
      guide.setCoords()
      fc.requestRenderAll()
      return
    }

    if ((tool === 'rect' || tool === 'crop') && isDrawingRectRef.current && rectObjRef.current) {
      const x0 = dragStartRef.current.x
      const y0 = dragStartRef.current.y
      rectObjRef.current.set({
        left: Math.min(x0, p.x),
        top: Math.min(y0, p.y),
        width: Math.abs(p.x - x0),
        height: Math.abs(p.y - y0),
      })
      fc.requestRenderAll()
    }
  }, [tool, cropPending])

  const handleStagePointerUp = useCallback(async (e) => {
    const fc = fabricCanvasRef.current
    if (!fc) return
    if (cropPending) return
    if (!['arrow', 'crop', 'rect', 'circle', 'text'].includes(tool)) return
    e.preventDefault()
    e.stopPropagation()
    try { e.currentTarget.releasePointerCapture?.(e.pointerId) } catch {}

    if (tool === 'arrow') {
      const st = arrowStateRef.current
      if (st.line) st.line.set({ selectable: true, evented: true })
      if (st.head) st.head.set({ selectable: true, evented: true })
      st.drawing = false
      st.line = null
      st.head = null
      pushHistory()
      setTool('none')
      fc.requestRenderAll()
      return
    }

    if (tool === 'rect') {
      if (rectObjRef.current) rectObjRef.current.set({ selectable: true, evented: true })
      rectObjRef.current = null
      isDrawingRectRef.current = false
      pushHistory()
      setTool('none')
      fc.requestRenderAll()
      return
    }

    if (tool === 'circle') {
      const c = circleObjRef.current
      circleObjRef.current = null
      isDrawingCircleRef.current = false

      if (c) c.set({ selectable: true, evented: true })
      pushHistory()
      setTool('none')
      fc.requestRenderAll()
      return
    }

    if (tool === 'text') {
      const guide = textGuideRectRef.current
      textGuideRectRef.current = null
      isDrawingTextBoxRef.current = false

      if (!guide) {
        setTool('none')
        return
      }

      const left = Math.round(guide.left ?? 0)
      const top = Math.round(guide.top ?? 0)
      const w = Math.round(guide.width ?? 0)
      const h = Math.round(guide.height ?? 0)

      try { fc.remove(guide) } catch {}

      // If user just clicked (tiny drag), default to a reasonable textbox width
      const width = Math.max(160, w)
      // Use drag height to pick a font size (clamped)
      const fontSize = clamp(Math.round((h > 6 ? h : 28)), 14, 120)

      const tb = new fabric.Textbox('', {
        left,
        top,
        width,
        fill: strokeColor,
        fontSize,
        editable: true,
        selectable: true,
        evented: true,
      })

      try {
        tb.on('editing:exited', () => pushHistory())
      } catch {
        // ignore
      }

      fc.add(tb)
      fc.setActiveObject(tb)
      fc.requestRenderAll()

      // Enter editing right away
      setTimeout(() => {
        try { tb.enterEditing() } catch {}
        try { tb.selectAll() } catch {}
      }, 0)

      pushHistory()
      setTool('none')
      return
    }

    if (tool === 'crop') {
      const rect = rectObjRef.current
      rectObjRef.current = null
      isDrawingRectRef.current = false
      if (!rect) {
        setTool('none')
        return
      }

      // Keep selection visible until user applies/cancels
      const x0 = Math.round(rect.left ?? 0)
      const y0 = Math.round(rect.top ?? 0)
      const w0 = Math.round(rect.width ?? 0)
      const h0 = Math.round(rect.height ?? 0)
      if (w0 < 5 || h0 < 5) {
        try { fc.remove(rect) } catch {}
        fc.requestRenderAll()
        setTool('none')
        return
      }
      cropPendingRectRef.current = rect
      setCropPending({ x: x0, y: y0, width: w0, height: h0 })
      setTool('none')
      fc.requestRenderAll()
    }
  }, [tool, cropPending, pushHistory])

  const handleCancelCrop = useCallback(() => {
    const fc = fabricCanvasRef.current
    const rect = cropPendingRectRef.current
    cropPendingRectRef.current = null
    setCropPending(null)
    if (fc && rect) {
      try { fc.remove(rect) } catch {}
      try { fc.requestRenderAll() } catch {}
    }
  }, [])

  const handleApplyCrop = useCallback(async () => {
    const fc = fabricCanvasRef.current
    const pending = cropPending
    const rect = cropPendingRectRef.current
    if (!fc || !pending || !rect) return

    try {
      // Remove selection overlay before export
      fc.remove(rect)
      cropPendingRectRef.current = null
      setCropPending(null)
      fc.requestRenderAll()

      const cw = Math.round(fc.width ?? 0)
      const ch = Math.round(fc.height ?? 0)
      const clampedX = clamp(Math.round(pending.x), 0, Math.max(0, cw - 1))
      const clampedY = clamp(Math.round(pending.y), 0, Math.max(0, ch - 1))
      const clampedW = clamp(Math.round(pending.width), 1, Math.max(1, cw - clampedX))
      const clampedH = clamp(Math.round(pending.height), 1, Math.max(1, ch - clampedY))

      const src = fc.toDataURL({ format: 'png', multiplier: 1 })
      setAnnotateMediaLoaded(false)
      const blob = await cropImageToBlob(src, { x: clampedX, y: clampedY, width: clampedW, height: clampedH })
      const url = URL.createObjectURL(blob)
      createdObjectUrlsRef.current.add(url)
      setWorkingUrlSafe(url)
      setTool('none')
    } catch {
      // Best-effort restore selection if something went wrong
      try {
        if (rect) fc.add(rect)
        cropPendingRectRef.current = rect
        setCropPending(pending)
        fc.requestRenderAll()
      } catch {
        // ignore
      }
    }
  }, [cropPending])

  function removeSelected() {
    const fc = fabricCanvasRef.current
    if (!fc) return
    const active = fc.getActiveObjects() || []
    active.forEach((obj) => {
      if (obj === baseImageObjRef.current?.obj) return
      fc.remove(obj)
    })
    fc.discardActiveObject()
    fc.requestRenderAll()
    pushHistory()
  }

  function clearAll() {
    const fc = fabricCanvasRef.current
    if (!fc) return
    const base = baseImageObjRef.current?.obj
    fc.getObjects().forEach((obj) => {
      if (obj !== base) fc.remove(obj)
    })
    fc.discardActiveObject()
    fc.requestRenderAll()
    pushHistory()
  }

  async function handleSave() {
    if (!step) return

    const fc = fabricCanvasRef.current
    if (!fc) return

    const base = baseImageObjRef.current
    const exportOpts = base
      ? {
          left: Math.round(base.offsetX ?? 0),
          top: Math.round(base.offsetY ?? 0),
          width: Math.round((base.imgW ?? 1) * (base.scale ?? 1)),
          height: Math.round((base.imgH ?? 1) * (base.scale ?? 1)),
        }
      : {}

    // Export at canvas resolution (scaled). Good enough for tutorial usage.
    const dataUrl = fc.toDataURL({ format: 'png', multiplier: 1, ...exportOpts })
    const res = await fetch(dataUrl)
    const blob = await res.blob()
    await onSave?.(blob)
    onClose?.()
  }

  if (!open || !step) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: 'var(--modal-overlay)' }}>
      <div className="w-full max-w-7xl h-[92vh] overflow-hidden cb-modal flex flex-col">
        <div className="cb-modal-header shrink-0">
          <div className="flex items-center justify-between">
            <h2 className="cb-modal-title">Editar imagem</h2>
            <button onClick={onClose} className="cb-btn p-2" aria-label="Fechar">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border p-3" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--card-border)' }}>
            <ToolButton active={tool === 'select'} onClick={() => setTool('select')} icon={Icons.select} label="Selecionar" />
            <ToolButton active={tool === 'crop'} onClick={() => { handleCancelCrop(); setTool('crop') }} icon={Icons.crop} label="Recortar" />
            <ToolButton active={tool === 'arrow'} onClick={() => setTool('arrow')} icon={Icons.arrow} label="Seta" />
            <ToolButton active={tool === 'draw'} onClick={() => setTool('draw')} icon={Icons.pen} label="Caneta" />
            <ToolButton active={tool === 'text'} onClick={() => setTool('text')} icon={Icons.text} label="Texto" />
            <ToolButton active={tool === 'rect'} onClick={() => setTool('rect')} icon={Icons.rect} label="Retângulo" />
            <ToolButton active={tool === 'circle'} onClick={() => setTool('circle')} icon={Icons.circle} label="Círculo" />

            <div className="mx-1 h-6 w-px" style={{ backgroundColor: 'var(--card-border)' }} />

            <ToolButton onClick={handleUndo} disabled={!canUndo} icon={Icons.undo} label="Desfazer" />
            <ToolButton onClick={handleRedo} disabled={!canRedo} icon={Icons.redo} label="Refazer" />

            <div className="flex-1" />

            <ToolButton
              active={showAdvanced}
              onClick={() => setShowAdvanced((v) => !v)}
              icon={Icons.options}
              label={showAdvanced ? 'Ocultar opções' : 'Opções'}
            />

            <ToolButton onClick={onClose} icon={Icons.cancel} label="Cancelar" />
            <ToolButton onClick={handleSave} disabled={!canSave} icon={Icons.save} label="Salvar" />
          </div>

          <section className="flex-1 min-h-0 flex flex-col">
            {showAdvanced ? (
              <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border p-3" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--card-border)' }}>
                <div className="flex items-center gap-2">
                  <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Cor</label>
                  <input type="color" value={strokeColor} onChange={(e) => setStrokeColor(e.target.value)} className="h-8 w-12 rounded border cursor-pointer" style={{ borderColor: 'var(--card-border)' }} />
                </div>

                <div className="flex items-center gap-2 min-w-[180px]">
                  <label className="text-xs font-medium whitespace-nowrap" style={{ color: 'var(--text-secondary)' }}>Espessura</label>
                  <input
                    type="range"
                    min={2}
                    max={24}
                    value={strokeWidth}
                    onChange={(e) => setStrokeWidth(clamp(Number(e.target.value) || 6, 2, 24))}
                    className="flex-1"
                    style={{ accentColor: 'var(--accent)' }}
                  />
                </div>

                <div className="flex items-center gap-2">
                  <ToolButton onClick={removeSelected} icon={Icons.trash} label="Remover selecionado" />
                  <ToolButton onClick={clearAll} icon={Icons.clear} label="Limpar anotações" />
                </div>
              </div>
            ) : null}

            {imageLoadError ? (
              <div className="rounded-lg border p-4 text-sm" style={{ backgroundColor: 'var(--danger-bg)', borderColor: 'var(--danger)', color: 'var(--danger)' }}>
                {imageLoadError}
              </div>
            ) : (
              <div
                ref={annotateStageRef}
                className="relative rounded-lg border p-3 flex-1 min-h-0 overflow-hidden"
                style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--card-border)', touchAction: 'none' }}
                onPointerDown={handleStagePointerDown}
                onPointerMove={handleStagePointerMove}
                onPointerUp={handleStagePointerUp}
              >
                <div ref={annotateWrapperRef} className="relative w-full h-full overflow-hidden">
                  <canvas ref={canvasElRef} style={{ display: 'block' }} />

                  {cropPending ? (
                    <div className="absolute left-2 top-2 flex items-center gap-2 rounded-md border px-2 py-1" style={{ background: 'rgba(0,0,0,0.55)', borderColor: 'rgba(255,255,255,0.18)', color: '#fff' }}>
                      <span className="text-xs">Recorte pronto</span>
                      <button type="button" className="rounded-md border px-2 py-1 text-xs" style={{ borderColor: 'rgba(255,255,255,0.25)' }} onClick={handleApplyCrop}>
                        Aplicar
                      </button>
                      <button type="button" className="rounded-md border px-2 py-1 text-xs" style={{ borderColor: 'rgba(255,255,255,0.25)' }} onClick={handleCancelCrop}>
                        Cancelar
                      </button>
                    </div>
                  ) : null}

                  {!annotateMediaLoaded ? (
                    <div className="absolute inset-0 flex items-center justify-center text-sm pointer-events-none" style={{ color: 'var(--muted-text)', background: 'rgba(0,0,0,0.25)' }}>
                      Carregando imagem…
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            <div className="text-xs mt-3 shrink-0" style={{ color: 'var(--muted-text)' }}>
              Dica: para editar objetos, clique em “Selecionar”.
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
