"use client"

export function VoiceWaveform({ active }: { active: boolean }) {
  const bars = 28

  return (
    <div className="flex items-center justify-center gap-[2px] h-10" aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => (
        <div
          key={i}
          className={`w-[3px] rounded-full transition-all duration-300 ${
            active ? "bg-primary animate-waveform-bar" : "bg-muted-foreground/20 h-1"
          }`}
          style={
            active
              ? {
                  height: `${10 + Math.sin(i * 0.65) * 18}px`,
                  animationDelay: `${i * 0.04}s`,
                  animationDuration: `${0.4 + Math.random() * 0.4}s`,
                }
              : { height: "4px" }
          }
        />
      ))}
    </div>
  )
}
