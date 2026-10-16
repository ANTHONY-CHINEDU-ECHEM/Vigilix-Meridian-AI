// Dictionaries with the same longest match linker as vigilix/kb/dictionaries.py.
// The Python exporter ships the precomputed name index and the set of names
// that may be linked inside prose, so linking rules live in one place.
import { applySpelling, rawTokens } from "./text";

export interface DictData {
  kind: string;
  entries: Record<string, any>;
  index: Record<string, string>;
  linkable: Record<string, string>;
  max_len: number;
}

export class Dictionary {
  entries: Record<string, any>;
  index: Map<string, string>;
  linkable: Map<string, string>;
  maxLen: number;
  kind: string;
  constructor(d: DictData) {
    this.kind = d.kind;
    this.entries = d.entries;
    this.index = new Map(Object.entries(d.index));
    this.linkable = new Map(Object.entries(d.linkable));
    this.maxLen = d.max_len;
  }
  static key(name: string): string {
    return rawTokens(name).map(applySpelling).join(" ");
  }
  lookup(name: string): any | null {
    const c = this.index.get(Dictionary.key(name));
    return c ? { canonical: c, ...this.entries[c] } : null;
  }
  link(text: string): [string, number, number][] {
    const toks = rawTokens(text).map(applySpelling);
    const out: [string, number, number][] = [];
    let i = 0;
    while (i < toks.length) {
      let hit: [string, number, number] | null = null;
      for (let span = Math.min(this.maxLen, toks.length - i); span > 0; span--) {
        const c = this.linkable.get(toks.slice(i, i + span).join(" "));
        if (c) {
          hit = [c, i, i + span];
          break;
        }
      }
      if (hit) {
        out.push(hit);
        i = hit[2];
      } else i++;
    }
    return out;
  }
  mentions(text: string): string[] {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const [c] of this.link(text)) {
      if (!seen.has(c)) {
        seen.add(c);
        out.push(c);
      }
    }
    return out;
  }
  /** exact n gram lookup used by query understanding */
  lookupNgrams(text: string, maxN = 6): string[] {
    const toks = rawTokens(text).map(applySpelling);
    const found: string[] = [];
    const covered = new Set<number>();
    for (let n = Math.min(maxN, toks.length); n > 0; n--) {
      for (let i = 0; i + n <= toks.length; i++) {
        let skip = false;
        for (let j = i; j < i + n; j++) if (covered.has(j)) skip = true;
        if (skip) continue;
        const c = this.index.get(toks.slice(i, i + n).join(" "));
        if (c && (n > 1 || toks[i].length >= 4)) {
          found.push(c);
          for (let j = i; j < i + n; j++) covered.add(j);
        }
      }
    }
    return found;
  }
  suggest(q: string, limit = 12, inGraph?: (c: string) => boolean) {
    q = q.trim().toLowerCase();
    if (q.length < 2) return [];
    const hits: [number, number, number, string][] = [];
    for (const [c, e] of Object.entries(this.entries)) {
      const names: string[] = [c, ...(e.synonyms || []).filter((s: string) => s !== c)];
      let best: [number, number] | null = null;
      for (const n of names) {
        if (n.startsWith(q)) {
          best = [n === c ? 0 : 1, n.length];
          break;
        }
        if (n.includes(q) && !best) best = [2, n.length];
      }
      if (best) hits.push([best[0], inGraph && inGraph(c) ? -1 : 0, best[1], c]);
    }
    hits.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
    return hits.slice(0, limit).map(([, , , c]) => {
      const e = this.entries[c];
      return { name: c, display: e.display || c, match: (e.synonyms || []).filter((s: string) => s.includes(q)).slice(0, 2), atc: e.atc?.[0] || null, soc: e.soc || null };
    });
  }
}
