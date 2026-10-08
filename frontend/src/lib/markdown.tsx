import type { ReactNode } from "react";

// Minimal renderer for the digest Markdown the backend produces (headings, emphasis line,
// paragraphs, link lines). It never injects raw HTML and only renders http(s) links.

function unescape(text: string): string {
  return text.replace(/\\([\\[\]*_`#])/g, "$1");
}

const LINK_RE = /\[((?:\\.|[^\]])+)\]\(([^)\s]+)\)/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let index = 0;
  for (const match of text.matchAll(LINK_RE)) {
    const [whole, label, url] = match;
    const start = match.index ?? 0;
    if (start > last) nodes.push(unescape(text.slice(last, start)));
    if (/^https?:\/\//i.test(url)) {
      nodes.push(
        <a key={`${keyPrefix}-${index++}`} href={url} target="_blank" rel="noopener noreferrer">
          {unescape(label)}
        </a>,
      );
    } else {
      nodes.push(unescape(label));
    }
    last = start + whole.length;
  }
  if (last < text.length) nodes.push(unescape(text.slice(last)));
  return nodes;
}

export function DigestMarkdown({ source }: { source: string }) {
  const blocks: ReactNode[] = [];
  source.split("\n").forEach((raw, i) => {
    const line = raw.trimEnd();
    if (!line) return;
    if (line.startsWith("# ")) return; // topic title is shown by the page itself
    if (line.startsWith("### ")) {
      blocks.push(<h3 key={i}>{renderInline(line.slice(4), `h${i}`)}</h3>);
    } else if (/^_.*_$/.test(line)) {
      blocks.push(
        <p key={i} className="font-mono text-xs text-faint">
          {unescape(line.slice(1, -1))}
        </p>,
      );
    } else {
      blocks.push(<p key={i}>{renderInline(line, `p${i}`)}</p>);
    }
  });
  return <div className="digest-body">{blocks}</div>;
}
