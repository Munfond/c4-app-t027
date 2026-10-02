export function BevLegend() {
  return <div className="pointer-events-none absolute bottom-3 left-3 max-w-[50%] rounded-lg border border-white/10 bg-[#0b2028]/95 px-3 py-2 text-[10px] text-slate-300 shadow-lg">
    <p className="mb-1 font-semibold text-slate-100">Khoảng cách đến tâm vật cản</p>
    <div className="flex flex-wrap gap-2">
      {[['#fb7185', '< 10 m'], ['#fbbf24', '10–25 m'], ['#2dd4bf', '≥ 25 m']].map(([color, label]) => <span key={label} className="flex items-center gap-1"><i className="h-2 w-2 rounded-sm" style={{backgroundColor:color}} />{label}</span>)}
    </div>
    <p className="mt-1">Nền sáng: bề mặt cao · nền tối: sát mặt đất</p>
    <p>Vòng: 10 / 25 / 50 m · vùng trống chưa chắc thông thoáng</p>
  </div>;
}
