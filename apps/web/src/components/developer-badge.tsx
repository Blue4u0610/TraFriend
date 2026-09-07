import Image from "next/image";

export function DeveloperBadge() {
  return (
    <aside
      data-testid="developer-badge"
      aria-label="Developer attribution"
      className="pointer-events-none fixed bottom-3 right-3 z-30 flex items-center gap-2 rounded-full border border-white/[0.12] bg-card/85 py-1.5 pl-3 pr-1.5 text-xs font-medium text-foreground shadow-lg shadow-black/15 backdrop-blur-md sm:bottom-5 sm:right-5"
    >
      <span>Created by Blue</span>
      <Image
        src="/blue-avatar.png"
        width={32}
        height={32}
        sizes="32px"
        alt="Blue"
        unoptimized
        className="size-8 rounded-full object-cover ring-1 ring-white/15"
      />
    </aside>
  );
}
