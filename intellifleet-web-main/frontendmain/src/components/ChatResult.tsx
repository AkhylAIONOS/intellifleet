const SECTION_LABELS = /^(Recommendation|Reason|Route|Route legs|Vehicles|Cost|Cost breakdown|Time|Risk|SLA|Feasible alternatives|Ranked alternatives|Baseline comparison|Recommended allocation|Replacement vehicles|Remaining route|Repositioning route)(:|$)/i;

export const ChatResult = ({ content }: { content: string }) => {
  const blocks = content.split(/\n\s*\n/).map(value => value.trim()).filter(Boolean);
  if (blocks.length < 2) return <div className="message-content">{content}</div>;

  return <div className="assistant-result">
    {blocks.map((block, index) => {
      const lines = block.split('\n');
      const isSection = SECTION_LABELS.test(lines[0]);
      return <section className={index === 0 ? 'answer-lead' : isSection ? 'answer-card' : 'answer-copy'} key={`${index}-${lines[0]}`}>
        {isSection && <strong>{lines.shift()?.replace(/:$/, '')}</strong>}
        <div>{lines.join('\n') || (isSection ? '' : block)}</div>
      </section>;
    })}
  </div>;
};
