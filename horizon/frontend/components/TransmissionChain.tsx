// TransmissionChain（08 §4）：竖向箭头列表，每步可挂证据
export default function TransmissionChain({ steps }: { steps: string[] }) {
  if (!steps.length) return <div className="text-[12px] text-[var(--text-3)]">暂无传导链</div>;
  return (
    <ol className="space-y-1">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-2 text-[12px] leading-5">
          <span className="mt-0.5 shrink-0 text-[var(--text-3)]">
            {i === steps.length - 1 ? "└→" : "├→"}
          </span>
          <span className="text-[var(--text-2)]">{step}</span>
        </li>
      ))}
    </ol>
  );
}
