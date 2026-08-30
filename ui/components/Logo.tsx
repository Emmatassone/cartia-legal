export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-baseline gap-1.5 ${className}`}>
      <span className="font-serif text-[1.05em] font-semibold tracking-tight text-ink-50">
        Cart
        <span className="text-brass-400">IA</span>
      </span>
      <span className="text-[0.7em] font-medium uppercase tracking-[0.22em] text-ink-400">
        Legal
      </span>
    </span>
  );
}
