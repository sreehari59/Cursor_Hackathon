type AudioFormat = "mulaw" | "pcm_s16le"

export class LiveAudioPlayer {
  private ctx: AudioContext | null = null
  private ws: WebSocket | null = null
  private nextPlayTime = 0
  private readonly format: AudioFormat
  private readonly sampleRate: number
  private readonly onStatus?: (status: string) => void
  private readonly onError?: (message: string) => void

  constructor(params?: {
    format?: AudioFormat
    sampleRate?: number
    onStatus?: (status: string) => void
    onError?: (message: string) => void
  }) {
    this.format = params?.format ?? "mulaw"
    this.sampleRate = params?.sampleRate ?? 8000
    this.onStatus = params?.onStatus
    this.onError = params?.onError
  }

  async start(listenUrl: string) {
    this.stop()
    const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) {
      throw new Error("Web Audio API is not available in this browser.")
    }

    this.ctx = new AudioCtx({ sampleRate: this.sampleRate })
    await this.ctx.resume()
    this.nextPlayTime = this.ctx.currentTime + 0.1

    this.ws = new WebSocket(listenUrl)
    this.ws.binaryType = "arraybuffer"

    this.ws.onopen = () => {
      this.onStatus?.("live-audio-connected")
    }

    this.ws.onmessage = (event) => {
      if (!(event.data instanceof ArrayBuffer) || !this.ctx) {
        return
      }
      const pcm = this.decodeAudio(new Uint8Array(event.data))
      if (pcm.length === 0) {
        return
      }

      const buffer = this.ctx.createBuffer(1, pcm.length, this.sampleRate)
      buffer.copyToChannel(pcm, 0)
      const source = this.ctx.createBufferSource()
      source.buffer = buffer
      source.connect(this.ctx.destination)

      const startAt = Math.max(this.nextPlayTime, this.ctx.currentTime + 0.02)
      source.start(startAt)
      this.nextPlayTime = startAt + buffer.duration
    }

    this.ws.onerror = () => {
      this.onError?.("Live audio monitor connection failed.")
    }

    this.ws.onclose = () => {
      this.onStatus?.("live-audio-stopped")
    }
  }

  stop() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    if (this.ctx) {
      void this.ctx.close()
      this.ctx = null
    }
    this.nextPlayTime = 0
  }

  private decodeAudio(bytes: Uint8Array): Float32Array {
    if (this.format === "pcm_s16le") {
      return decodePcm16(bytes)
    }
    return decodeMuLaw(bytes)
  }
}

function decodePcm16(bytes: Uint8Array): Float32Array {
  const samples = new Float32Array(Math.floor(bytes.length / 2))
  for (let i = 0; i < samples.length; i++) {
    const lo = bytes[i * 2] ?? 0
    const hi = bytes[i * 2 + 1] ?? 0
    let value = (hi << 8) | lo
    if (value & 0x8000) {
      value = value - 0x10000
    }
    samples[i] = value / 32768
  }
  return samples
}

function decodeMuLaw(bytes: Uint8Array): Float32Array {
  const samples = new Float32Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) {
    const pcm = muLawToLinear(bytes[i])
    samples[i] = pcm / 32768
  }
  return samples
}

function muLawToLinear(value: number): number {
  const ulaw = (~value) & 0xff
  const sign = ulaw & 0x80
  const exponent = (ulaw >> 4) & 0x07
  const mantissa = ulaw & 0x0f
  let sample = ((mantissa << 3) + 0x84) << exponent
  sample -= 0x84
  return sign ? -sample : sample
}
