import type { ReactNode } from "react";

/** 데스크톱에서 가운데 모바일 폰 목업 안에 앱을 렌더한다. */
export default function PhoneFrame({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-full w-full flex items-center justify-center bg-gradient-to-br from-sand to-cream p-0 sm:p-8">
      <div className="relative w-full h-[100dvh] sm:h-[812px] sm:w-[390px] sm:rounded-[44px] sm:shadow-phone sm:border-[10px] sm:border-bark bg-cream overflow-hidden flex flex-col">
        {/* 노치 */}
        <div className="hidden sm:block absolute top-0 left-1/2 -translate-x-1/2 w-32 h-6 bg-bark rounded-b-2xl z-30" />
        {children}
      </div>
    </div>
  );
}
